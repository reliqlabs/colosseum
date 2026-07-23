/**
 * colosseum-panel-resolver — authoritative roster resolver for the
 * colosseum-panel skill. Installed to <project>/.omp/extensions/ by
 * `colosseum_init --harness omp`.
 *
 * Registers one eval/LLM-callable tool, `colosseum_panel_resolve`, that reads
 * `.colosseum/panel-profiles.json`, resolves each seat's ranked candidates to
 * the first AVAILABLE model via OMP's model registry, and enforces distinct
 * model families using `ctx.models.family` — the OMP-native opaque lineage
 * token. That token is used only in-memory for the duplicate check and is NEVER
 * returned or persisted (OMP docs: "don't persist it"); only stable fields leave
 * this tool, so historical panel evidence never depends on a changing family
 * vocabulary.
 *
 * The colosseum-panel skill also ships a stdlib Python loader (panel_roster.py),
 * but it is DIAGNOSTICS/TESTS ONLY: it checks declared_family labels and cannot
 * verify availability or the opaque model family, so the skill requires THIS
 * extension for panel execution and fails closed when it is absent.
 */
import * as fs from "node:fs";
import * as path from "node:path";
import type { ExtensionAPI } from "@oh-my-pi/pi-coding-agent";

interface ResolvedSeat {
	seat_id: string;
	declared_family: string;
	requested_selector: string;
	resolved_provider: string;
	resolved_model: string;
	thinking_level: string;
	calibration: string;
}

/** OMP's canonical dispatch selector for a model: `provider/id`.
 *  Dispatching a bare `id` would discard the provider that `ctx.models.resolve`
 *  actually selected and family-checked, and could reroute a duplicate id to a
 *  different provider. `omp_panel.py` composes `provider/model:thinkingLevel`
 *  from this. */
function canonicalSelector(model: { provider: string; id: string }): string {
	return `${model.provider}/${model.id}`;
}

export default function colosseumPanelResolver(pi: ExtensionAPI) {
	const { z } = pi.zod;
	pi.setLabel("Colosseum panel resolver");

	const SeatSchema = z.object({
		seat_id: z.string().min(1),
		declared_family: z.string().min(1),
		thinking_level: z.string().optional(),
		calibration: z.string().optional(),
		candidates: z.array(z.string().min(1)).min(1),
	});
	const ProfileSchema = z.object({
		mode: z.enum(["project-plan", "milestone-review"]),
		min_families: z.number().optional(),
		seats: z.array(SeatSchema).min(2),
		synthesizer: SeatSchema,
	});
	const DocSchema = z.object({ profiles: z.record(z.string(), ProfileSchema) });
	type Seat = z.infer<typeof SeatSchema>;

	pi.registerTool({
		name: "colosseum_panel_resolve",
		label: "Resolve Colosseum panel roster",
		description:
			"Resolve and freeze a colosseum-panel roster from .colosseum/panel-profiles.json. " +
			"Picks the first available model per seat and enforces distinct model families. " +
			"Returns {profile, mode, min_families, seats, synthesizer} as JSON.",
		parameters: z.object({
			profile: z.string().describe("profile name in .colosseum/panel-profiles.json"),
			project_root: z.string().optional().describe("defaults to the session cwd"),
		}),
		async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
			const root = params.project_root || ctx.cwd;
			const profPath = path.join(root, ".colosseum", "panel-profiles.json");
			let raw: unknown;
			try {
				raw = JSON.parse(fs.readFileSync(profPath, "utf8"));
			} catch (err) {
				throw new Error(`cannot read ${profPath}: ${(err as Error).message}`);
			}
			const doc = DocSchema.parse(raw);
			const prof = doc.profiles[params.profile];
			if (!prof) throw new Error(`profile ${params.profile} not found in ${profPath}`);
			const minFamilies = prof.min_families ?? 3;

			// Keyed by `provider/id`, not bare id: two providers may serve the
			// same model id, and only the resolved provider is the one checked.
			const available = new Set(ctx.models.list().map(canonicalSelector));
			const familyToken = new Map<string, string>(); // seat_id -> opaque token (in-memory only)

			const resolveSeat = (spec: Seat, where: string): ResolvedSeat => {
				for (const cand of spec.candidates) {
					const model = ctx.models.resolve(cand);
					if (!model || !available.has(canonicalSelector(model))) continue;
					familyToken.set(spec.seat_id, ctx.models.family(model));
					return {
						seat_id: spec.seat_id,
						declared_family: spec.declared_family,
						requested_selector: cand,
						resolved_provider: model.provider,
						resolved_model: canonicalSelector(model),
						thinking_level: spec.thinking_level ?? "",
						calibration: spec.calibration ?? "pending",
					};
				}
				throw new Error(
					`${where}: no available model for seat ${spec.seat_id} ` +
						`(candidates: ${spec.candidates.join(", ")})`,
				);
			};

			const seats = prof.seats.map((s, i) => resolveSeat(s, `${params.profile}.seats[${i}]`));
			const ids = new Set(seats.map((s) => s.seat_id));
			if (ids.size !== seats.length) {
				throw new Error(`profile ${params.profile} has duplicate seat_id`);
			}
			// Distinct declared families (persisted) AND distinct opaque model
			// lineages (runtime): two seats resolving to the same family is a config
			// error the declared labels would hide.
			const declared = new Set(seats.map((s) => s.declared_family));
			if (declared.size < minFamilies) {
				throw new Error(
					`profile ${params.profile}: ${declared.size} declared families ` +
						`(${[...declared].join(", ")}); min_families=${minFamilies}`,
				);
			}
			const tokens = new Set(seats.map((s) => familyToken.get(s.seat_id)));
			if (tokens.size !== seats.length) {
				throw new Error(
					`profile ${params.profile}: two seats resolved to the same model family ` +
						`despite distinct declared_family labels`,
				);
			}

			const synthesizer = resolveSeat(prof.synthesizer, `${params.profile}.synthesizer`);
			const roster = {
				profile: params.profile,
				mode: prof.mode,
				min_families: minFamilies,
				seats,
				synthesizer,
				family_distinctness_checked: true,
				family_distinctness_source: "OMP ctx.models.family runtime comparison (resolver)",
			};
			return {
				content: [{ type: "text", text: JSON.stringify(roster) }],
				details: roster,
			};
		},
	});
}
