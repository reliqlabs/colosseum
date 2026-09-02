import * as path from "node:path";
import type { CustomToolFactory } from "@oh-my-pi/pi-coding-agent";
import type { Model } from "@oh-my-pi/pi-ai";

interface ResolvedSeat {
	seat_id: string;
	declared_family: string;
	requested_selector: string;
	resolved_provider: string;
	resolved_model: string;
	thinking_level: string;
	calibration: string;
	resolved_family: string;
}

function selector(model: Model): string {
	return `${model.provider}/${model.id}`;
}

function familyToken(model: Model): string {
	if (!model.identity) throw new Error(`model identity unavailable for ${selector(model)}`);
	return model.identity.class === "unknown" ? model.provider.toLowerCase() : model.identity.class;
}

const factory: CustomToolFactory = pi => {
	const seatSchema = pi.zod.object({
		seat_id: pi.zod.string(),
		declared_family: pi.zod.string(),
		thinking_level: pi.zod.string().optional(),
		calibration: pi.zod.string().optional(),
		candidates: pi.zod.array(pi.zod.string()),
	});
	const profileSchema = pi.zod.object({
		mode: pi.zod.enum(["project-plan", "milestone-review"]),
		min_families: pi.zod.number().optional(),
		seat_timeout_seconds: pi.zod.number().optional(),
		seats: pi.zod.array(seatSchema),
		synthesizer: seatSchema,
	});
	const documentSchema = pi.zod.object({ profiles: pi.zod.record(pi.zod.string(), profileSchema) });

	return {
		name: "fv_panel_resolve",
		label: "Resolve FV panel roster",
		description: "Resolve an available, family-distinct FV panel roster.",
		parameters: pi.zod.object({
			profile: pi.zod.string(),
			project_root: pi.zod.string().optional(),
		}),

		async execute(_toolCallId, params, _onUpdate, ctx) {
			const root = path.resolve(pi.cwd, params.project_root ?? ".");
			const profilePath = path.join(root, ".fv", "panel-profiles.json");
			const document = documentSchema.parse(await Bun.file(profilePath).json());
			const profile = document.profiles[params.profile];
			if (!profile) throw new Error(`profile ${params.profile} not found in ${profilePath}`);
			const minFamilies = profile.min_families ?? 3;
			const seatTimeoutSeconds = profile.seat_timeout_seconds ?? 1800;
			if (!Number.isFinite(seatTimeoutSeconds) || seatTimeoutSeconds <= 0) {
				throw new Error(`profile ${params.profile}: seat_timeout_seconds must be positive`);
			}
			const available = ctx.modelRegistry.getAvailable();
			const resolveCandidate = (candidate: string): Model | undefined => {
				const exact = available.find(model => selector(model) === candidate);
				if (exact) return exact;
				return available.find(model => model.id === candidate);
			};
			const tokens = new Map<string, string>();
			const resolveSeat = (seat: typeof profile.synthesizer, where: string): ResolvedSeat => {
				if (!seat.candidates.length) throw new Error(where + ": candidates must not be empty");
				for (const candidate of seat.candidates) {
					const model = resolveCandidate(candidate);
					if (!model) continue;
					const resolvedFamily = familyToken(model);
					tokens.set(seat.seat_id, resolvedFamily);
					return {
						seat_id: seat.seat_id,
						declared_family: seat.declared_family,
						requested_selector: candidate,
						resolved_provider: model.provider,
						resolved_model: selector(model),
						resolved_family: resolvedFamily,
						thinking_level: seat.thinking_level ?? "",
						calibration: seat.calibration ?? "pending",
					};
				}
				throw new Error(where + ": no available model for seat " + seat.seat_id);
			};
			const seats = profile.seats.map((seat, index) => resolveSeat(seat, `${params.profile}.seats[${index}]`));
			if (new Set(seats.map(seat => seat.seat_id)).size !== seats.length) {
				throw new Error(`profile ${params.profile} has duplicate seat_id`);
			}
			const declared = new Set(seats.map(seat => seat.declared_family));
			if (declared.size < minFamilies) {
				throw new Error(`profile ${params.profile}: ${declared.size} declared families; min_families=${minFamilies}`);
			}
			if (new Set(seats.map(seat => tokens.get(seat.seat_id))).size !== seats.length) {
				throw new Error(`profile ${params.profile}: two seats resolved to the same model family`);
			}
			const synthesizer = resolveSeat(profile.synthesizer, `${params.profile}.synthesizer`);
			const roster = {
				profile: params.profile,
				mode: profile.mode,
				min_families: minFamilies,
				seat_timeout_seconds: seatTimeoutSeconds,
				seats,
				synthesizer,
			};
			return {
				content: [{ type: "text", text: JSON.stringify(roster) }],
				details: roster,
			};
		},
	};
};

export default factory;
