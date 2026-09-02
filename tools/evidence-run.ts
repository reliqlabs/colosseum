import * as fs from "node:fs/promises";
import * as path from "node:path";
import type { CustomToolFactory } from "@oh-my-pi/pi-coding-agent";

const PASS_MARKERS: Record<string, RegExp> = {
	"code-enforced": /--- fv-evidence: exit=0 ---/,
	"proof-discharged": /(?:VERIFICATION:- SUCCESSFUL|Build completed successfully|--- fv-evidence: exit=0 ---)/,
	"bounded-checked": /(?:\[ok\]|VERIFICATION:- SUCCESSFUL|No violation found)/,
	"test-witnessed": /test result: ok\./,
	"conformance-tested": /(?:CONFORMANCE(?:_TESTED)?: PASS|test result: ok\.|--- fv-evidence: exit=0 ---)/,
	"externally-assumed": /--- fv-evidence: exit=0 ---/,
	unverified: /--- fv-evidence: exit=0 ---/,
};

async function sha256File(filePath: string): Promise<string> {
	const bytes = await Bun.file(filePath).arrayBuffer();
	return new Bun.CryptoHasher("sha256").update(bytes).digest("hex");
}

async function requiredFileHash(filePath: string, label: string): Promise<string> {
	const file = Bun.file(filePath);
	if (!(await file.exists())) throw new Error(`${label} is missing: ${filePath}`);
	return sha256File(filePath);
}

function hasSourceChanges(status: string): boolean {
	return status.split(/\r?\n/).filter(Boolean).some(line => {
		const changedPaths = line.slice(3).split(" -> ");
		return changedPaths.some(value => {
			const changedPath = value.replace(/^"|"$/g, "");
			return changedPath !== ".fv" && !changedPath.startsWith(".fv/");
		});
	});
}

const factory: CustomToolFactory = pi => ({
	name: "fv_evidence_run",
	label: "FV Evidence Run",
	description: "Run one argv command and persist a hash-bound FV evidence record.",
	approval: "exec",
	parameters: pi.zod.object({
		claim_id: pi.zod.string(),
		command: pi.zod.array(pi.zod.string()),
		cwd: pi.zod.string().optional(),
		evidence_class: pi.zod.string(),
		scope: pi.zod.string(),
		required: pi.zod.boolean().optional(),
		pass_marker: pi.zod.string().optional(),
	}),

	async execute(_toolCallId, params, _onUpdate, _ctx, signal) {
		if (!/^[A-Za-z0-9][A-Za-z0-9._-]*$/.test(params.claim_id)) {
			throw new Error("claim_id must be a filesystem-safe identifier");
		}
		if (params.command.length === 0 || params.command.some(part => part.length === 0)) {
			throw new Error("command must contain non-empty argv elements");
		}
		const classMarker = PASS_MARKERS[params.evidence_class];
		if (!classMarker) throw new Error(`unknown evidence_class: ${params.evidence_class}`);
		const projectRoot = await fs.realpath(path.resolve(pi.cwd));
		const commandCwd = await fs.realpath(path.resolve(projectRoot, params.cwd ?? "."));
		if (commandCwd !== projectRoot && !commandCwd.startsWith(projectRoot + path.sep)) {
			throw new Error("cwd must resolve inside the project root");
		}
		const timestamp = new Date().toISOString().replace(/[:.]/g, "-");
		const rawRelative = path.join(".fv", "evidence", "raw", `${params.claim_id}-${timestamp}.log`);
		const rawPath = path.join(projectRoot, rawRelative);
		const recordPath = path.join(projectRoot, ".fv", "evidence", "records", `${params.claim_id}.json`);

		const intentPath = path.join(projectRoot, ".fv", "intent.md");
		const manifestPath = path.join(projectRoot, ".fv", "obligations.json");
		const intentHash = await requiredFileHash(intentPath, "intent");
		const manifestHash = await requiredFileHash(manifestPath, "obligation manifest");
		const manifest = await Bun.file(manifestPath).json();
		const requestedExecutable = params.command[0]!;
		const executableLookup = requestedExecutable.includes("/") || requestedExecutable.includes("\\")
			? path.resolve(commandCwd, requestedExecutable)
			: Bun.which(requestedExecutable);
		if (!executableLookup) throw new Error(`command executable not found: ${requestedExecutable}`);
		const executable = await fs.realpath(executableLookup);
		const executableHash = await sha256File(executable);
		const versionProbe = await pi.exec(executable, ["--version"], { cwd: commandCwd, signal });

		const source = await pi.exec("git", ["rev-parse", "HEAD"], { cwd: projectRoot, signal });
		if (source.code !== 0 || !source.stdout.trim()) throw new Error("git rev-parse HEAD failed");
		const beforeStatus = await pi.exec("git", ["status", "--porcelain", "--untracked-files=all"],
			{ cwd: projectRoot, signal });
		if (beforeStatus.code !== 0) throw new Error("git status failed before evidence command");

		const execution = await pi.exec(executable, params.command.slice(1), {
			cwd: commandCwd,
			signal,
		});
		const sourceAfter = await pi.exec("git", ["rev-parse", "HEAD"], { cwd: projectRoot, signal });
		if (sourceAfter.code !== 0 || !sourceAfter.stdout.trim()) throw new Error("git rev-parse HEAD failed after evidence command");
		const intentHashAfter = await requiredFileHash(intentPath, "intent");
		const manifestHashAfter = await requiredFileHash(manifestPath, "obligation manifest");
		const afterStatus = await pi.exec("git", ["status", "--porcelain", "--untracked-files=all"],
			{ cwd: projectRoot, signal });
		if (afterStatus.code !== 0) throw new Error("git status failed after evidence command");
		const bindingDrift = source.stdout.trim() !== sourceAfter.stdout.trim()
			|| intentHash !== intentHashAfter || manifestHash !== manifestHashAfter;
		const dirty = hasSourceChanges(beforeStatus.stdout) || hasSourceChanges(afterStatus.stdout) || bindingDrift;
		const trailer = `--- fv-evidence: exit=${execution.code} ---`;
		const streams = [execution.stdout, execution.stderr]
			.filter(stream => stream.length > 0)
			.map(stream => (stream.endsWith("\n") ? stream : stream + "\n"));
		const rawOutput = streams.join("") + trailer + "\n";
		await Bun.write(rawPath, rawOutput);
		const rawOutputHash = await sha256File(rawPath);
		const markerMatched = params.pass_marker ? rawOutput.includes(params.pass_marker) : classMarker.test(rawOutput);
		let result = execution.code === 0 && markerMatched ? "PASS" : "FAIL";
		if (dirty && result === "PASS") result = "FAIL";

		const requiredTargets = [
			...(Array.isArray(manifest.invariants) ? manifest.invariants : []),
			...(Array.isArray(manifest.witnesses) ? manifest.witnesses : []),
		]
			.map(item => item?.id)
			.filter((id): id is string => typeof id === "string" && id.length > 0);
		if (requiredTargets.length === 0) throw new Error(`obligation manifest has no targets: ${manifestPath}`);

		const record = {
			claim_id: params.claim_id,
			required: params.required ?? true,
			evidence_class: params.evidence_class,
			result,
			scope: params.scope,
			bindings: {
				source_snapshot: source.stdout.trim() + (dirty ? "+dirty" : ""),
				intent_hash: intentHash,
				obligation_manifest_hash: manifestHash,
				profile: "producer-trusted-execution",
				required_targets: requiredTargets,
				environment_policy: "omp-extension-tool",
				toolchain_digests: {
					executable,
					sha256: executableHash,
					version: (versionProbe.stdout + versionProbe.stderr).trim(),
					version_exit_code: versionProbe.code,
				},
				command: JSON.stringify(params.command),
				configuration: {
					cwd: path.relative(projectRoot, commandCwd) || ".",
					...(params.pass_marker ? { pass_marker: params.pass_marker } : {}),
				},
				seeds: null,
				raw_output_hash: rawOutputHash,
				raw_output_path: rawRelative,
				parser_schema_version: "fv-evidence-run/v2",
				run_id: timestamp,
			},
			waiver: null,
		};
		await Bun.write(recordPath, `${JSON.stringify(record, null, 2)}\n`);
		return {
			content: [{ type: "text", text: `${result}: ${params.claim_id}\n${path.relative(projectRoot, recordPath)}` }],
			details: { record, recordPath, rawPath, exitCode: execution.code },
		};
	},
});

export default factory;
