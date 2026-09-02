import * as path from "node:path";
import type {
	CustomToolFactory,
	PanelRole,
	ResolvedPanelLineup,
} from "@oh-my-pi/pi-coding-agent";

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
			// Taken from the injected `pi-coding-agent` exports at call time, not at
			// factory time: an extension package sits outside OMP's module graph, so
			// a bare value import would not resolve, and constructing the tool must
			// stay side-effect free for loaders that probe it.
			const resolveLineup = pi.pi?.resolvePanelLineup;
			if (typeof resolveLineup !== "function") {
				throw new Error(
					"this OMP build does not expose resolvePanelLineup; " +
						"`omp --agent-bridge-contract` must report panelLineupFreeze",
				);
			}
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
			if (new Set(profile.seats.map(seat => seat.seat_id)).size !== profile.seats.length) {
				throw new Error(`profile ${params.profile} has duplicate seat_id`);
			}
			const declared = new Set(profile.seats.map(seat => seat.declared_family));
			if (declared.size < minFamilies) {
				throw new Error(`profile ${params.profile}: ${declared.size} declared families; min_families=${minFamilies}`);
			}

			// Candidate priority, availability, real served-family distinctness, and
			// the lineup hash are OMP's; FV keeps the registry semantics on top —
			// declared families, calibration references, and per-seat effort.
			type ProfileSeat = (typeof profile.seats)[number];
			// Both lineups are `independent`, which carries served-family
			// distinctness by default; only the panel proper takes the floor. The
			// one-seat synthesizer lineup makes no diversity claim.
			const seatRole = (seats: ProfileSeat[], floor: boolean, where: string): PanelRole => ({
				strategy: "independent",
				members: seats.map((seat, index) => {
					const [primary, ...fallbacks] = seat.candidates;
					if (primary === undefined) {
						throw new Error(`${where}[${index}]: candidates must not be empty`);
					}
					return { model: primary, fallbacks };
				}),
				...(floor ? { minFamilies } : {}),
			});
			const context = { modelRegistry: ctx.modelRegistry, settings: ctx.settings };
			const resolveSeats = (seats: ProfileSeat[], floor: boolean, where: string): ResolvedPanelLineup => {
				try {
					return resolveLineup({
						context,
						roleId: `${params.profile}.${where}`,
						role: seatRole(seats, floor, where),
						taskMode: "plan",
					});
				} catch (error) {
					throw new Error(`${where}: ${error instanceof Error ? error.message : String(error)}`);
				}
			};

			const resolvedSeats = resolveSeats(profile.seats, true, "seats");
			const resolvedSynthesizer = resolveSeats([profile.synthesizer], false, "synthesizer");
			const toSeat = (seat: ProfileSeat, index: number, lineup: ResolvedPanelLineup): ResolvedSeat => {
				const member = lineup.members[index];
				if (!member) throw new Error(`seat ${seat.seat_id} has no resolved member at index ${index}`);
				const [provider] = member.selector.split("/");
				if (provider === undefined || provider.length === 0) {
					throw new Error(`seat ${seat.seat_id} resolved an unqualified selector "${member.selector}"`);
				}
				return {
					seat_id: seat.seat_id,
					declared_family: seat.declared_family,
					requested_selector: member.requestedSelector,
					resolved_provider: provider,
					resolved_model: member.selector,
					resolved_family: member.family,
					thinking_level: seat.thinking_level ?? "",
					calibration: seat.calibration ?? "pending",
				};
			};

			const roster = {
				profile: params.profile,
				mode: profile.mode,
				min_families: minFamilies,
				seat_timeout_seconds: seatTimeoutSeconds,
				lineup_hash: resolvedSeats.lineupHash,
				seats: profile.seats.map((seat, index) => toSeat(seat, index, resolvedSeats)),
				synthesizer: toSeat(profile.synthesizer, 0, resolvedSynthesizer),
			};
			return {
				content: [{ type: "text", text: JSON.stringify(roster) }],
				details: roster,
			};
		},
	};
};

export default factory;
