/- M7 refinement: the Aeneas-extracted jobq model refines the Quint
   transition relation of specs/jobq.qnt (module jobq = jobqP(CAPACITY=2)).

   Shape of the claim (code refines spec): every state reachable by
   successful extracted operations from `JobQueue.new 2` is R-related to a
   spec state reachable by QStep from QInit. The Quint invariants are ALSO
   proved inductive over QStep here in Lean, so their transfer to the code
   does not rest on the bounded model check; Apalache's depth-12 run is
   corroborating design-time evidence, the induction is the proof.

   Ghost variables: the spec's prev_done/prev_failed exist only to state
   monotonicity (B5) as a state invariant for the model checker. They are
   derived history (every action sets prev_x' = x), not machine state, so R
   does not relate them; B5 transfers instead as the step-monotonicity
   theorems over the extracted operations at the end of this file.

   Arithmetic bridging: QState carries Int (Quint's type); the extracted
   struct carries U32. Simulation lemmas condition on the extracted
   operation returning `ok` (via UScalar.add_equiv/sub_equiv), so no
   boundedness hypothesis is needed for this direction: a successful return
   means no overflow occurred. Totality (the operation succeeds whenever
   the spec guard holds) is NOT claimed for submit/complete/fail, whose
   counter increments can overflow at u32::MAX; that gap is the
   adjudication's OPEN finding F2 and is deliberately out of scope. -/
import Jobq
open Aeneas Aeneas.Std Result

namespace jobq.refinement

/-! ## Quint transcription (jobqP at CAPACITY = 2) -/

def CAPACITY : Int := 2
def MAX_ATTEMPTS : Int := 3

structure QState where
  queued : Int
  running : Bool
  attempts : Int
  done : Int
  failed : Int
  submitted : Int
deriving Repr, DecidableEq

def QInit : QState :=
  { queued := 0, running := false, attempts := 0,
    done := 0, failed := 0, submitted := 0 }

def submitStep (s s' : QState) : Prop :=
  s.queued < CAPACITY ∧
  s' = { s with queued := s.queued + 1, submitted := s.submitted + 1 }

def startStep (s s' : QState) : Prop :=
  s.queued > 0 ∧ s.running = false ∧
  s' = { s with queued := s.queued - 1, running := true, attempts := 1 }

def completeStep (s s' : QState) : Prop :=
  s.running = true ∧
  s' = { s with running := false, attempts := 0, done := s.done + 1 }

def failRetryStep (s s' : QState) : Prop :=
  s.running = true ∧ s.attempts < MAX_ATTEMPTS ∧
  s' = { s with attempts := s.attempts + 1 }

def failFinalStep (s s' : QState) : Prop :=
  s.running = true ∧ s.attempts = MAX_ATTEMPTS ∧
  s' = { s with running := false, attempts := 0, failed := s.failed + 1 }

def QStep (s s' : QState) : Prop :=
  submitStep s s' ∨ startStep s s' ∨ completeStep s s' ∨
  failRetryStep s s' ∨ failFinalStep s s'

/-- Spec reachability: QInit closed under QStep. -/
inductive QReach : QState → Prop where
  | init : QReach QInit
  | step {s s'} (hr : QReach s) (h : QStep s s') : QReach s'

/-! ## The spec invariants (inv_all of jobq.qnt), proved inductive -/

def QInv (s : QState) : Prop :=
  -- inv_b1
  s.attempts ≤ MAX_ATTEMPTS ∧
  -- inv_b2 (conservation)
  s.queued + (if s.running then 1 else 0) + s.done + s.failed = s.submitted ∧
  -- inv_b3 (biconditional)
  ((s.running = false → s.attempts = 0) ∧
   (s.running = true → 1 ≤ s.attempts ∧ s.attempts ≤ MAX_ATTEMPTS)) ∧
  -- inv_b4
  s.queued ≤ CAPACITY ∧
  -- inv_nonneg
  (0 ≤ s.queued ∧ 0 ≤ s.attempts ∧ 0 ≤ s.done ∧ 0 ≤ s.failed ∧
   0 ≤ s.submitted)

theorem QInv_init : QInv QInit := by
  simp [QInv, QInit, MAX_ATTEMPTS, CAPACITY]

theorem QInv_step {s s' : QState} (hinv : QInv s) (h : QStep s s') :
    QInv s' := by
  obtain ⟨hb1, hb2, ⟨hb3i, hb3r⟩, hb4, hnn⟩ := hinv
  rcases h with ⟨hg, rfl⟩ | ⟨hg, hrun, rfl⟩ | ⟨hrun, rfl⟩ |
    ⟨hrun, hg, rfl⟩ | ⟨hrun, hg, rfl⟩ <;>
    simp_all [QInv, CAPACITY, MAX_ATTEMPTS] <;> omega

theorem QReach_inv {s : QState} (h : QReach s) : QInv s := by
  induction h with
  | init => exact QInv_init
  | step _ hstep ih => exact QInv_step ih hstep

/-! ## Refinement relation -/

/-- Field-wise value equality plus the pinned capacity. Ghosts excluded. -/
def R (s : QState) (r : queue.JobQueue) : Prop :=
  r.capacity.val = 2 ∧
  (r.queued.val : Int) = s.queued ∧
  r.running = s.running ∧
  (r.attempts.val : Int) = s.attempts ∧
  (r.done.val : Int) = s.done ∧
  (r.failed.val : Int) = s.failed ∧
  (r.submitted.val : Int) = s.submitted

/-! ## Code reachability: new(2) closed under extracted operations.
    Err-returning calls leave the state unchanged in the extracted model,
    so including them only adds stutter. -/

inductive RustReach : queue.JobQueue → Prop where
  | init {r} (h : queue.JobQueue.new 2#u32 = ok r) : RustReach r
  | submit {r o r'} (hr : RustReach r)
      (h : queue.JobQueue.submit r = ok (o, r')) : RustReach r'
  | start {r o r'} (hr : RustReach r)
      (h : queue.JobQueue.start r = ok (o, r')) : RustReach r'
  | complete {r o r'} (hr : RustReach r)
      (h : queue.JobQueue.complete r = ok (o, r')) : RustReach r'
  | fail {r o r'} (hr : RustReach r)
      (h : queue.JobQueue.fail r = ok (o, r')) : RustReach r'

/-! ## Init lemma -/

theorem init_sim {r : queue.JobQueue}
    (h : queue.JobQueue.new 2#u32 = ok r) : R QInit r := by
  rw [queue.JobQueue.new] at h
  simp only [ok.injEq] at h
  subst h
  simp [R, QInit]

/-! ## Per-operation simulation lemmas (ok-conditioned). -/

theorem submit_sim {s r o r'}
    (hR : R s r) (h : queue.JobQueue.submit r = ok (o, r')) :
    r' = r ∨ ∃ s', submitStep s s' ∧ R s' r' := by
  obtain ⟨hcap, hq, hrun, hat, hd, hf, hs⟩ := hR
  rw [queue.JobQueue.submit] at h
  split at h
  · left
    simp only [ok.injEq, Prod.mk.injEq] at h
    exact h.2.symm
  · rename_i hlt
    right
    cases h1 : r.queued + 1#u32 with
    | ok i =>
      rw [h1] at h
      cases h2 : r.submitted + 1#u32 with
      | ok i1 =>
        rw [h2] at h
        simp only [bind_tc_ok, ok.injEq, Prod.mk.injEq] at h
        obtain ⟨-, rfl⟩ := h
        have e1 := UScalar.add_equiv r.queued 1#u32
        rw [h1] at e1
        obtain ⟨-, hv1, -⟩ := e1
        have e2 := UScalar.add_equiv r.submitted 1#u32
        rw [h2] at e2
        obtain ⟨-, hv2, -⟩ := e2
        refine ⟨{ s with queued := s.queued + 1,
                         submitted := s.submitted + 1 },
                ⟨by simp only [CAPACITY]; scalar_tac, rfl⟩, ?_⟩
        simp only [R]
        refine ⟨by simp_all, by scalar_tac, by simp_all, by simp_all,
                by simp_all, by simp_all, by scalar_tac⟩
      | fail e => rw [h2] at h; simp at h
      | div => rw [h2] at h; simp at h
    | fail e => rw [h1] at h; simp at h
    | div => rw [h1] at h; simp at h

theorem start_sim {s r o r'}
    (hR : R s r) (h : queue.JobQueue.start r = ok (o, r')) :
    r' = r ∨ ∃ s', startStep s s' ∧ R s' r' := by
  obtain ⟨hcap, hq, hrun, hat, hd, hf, hs⟩ := hR
  rw [queue.JobQueue.start] at h
  split at h
  · left
    simp only [ok.injEq, Prod.mk.injEq] at h
    exact h.2.symm
  · rename_i hne
    split at h
    · left
      simp only [ok.injEq, Prod.mk.injEq] at h
      exact h.2.symm
    · rename_i hnrun
      right
      cases h1 : r.queued - 1#u32 with
      | ok i =>
        rw [h1] at h
        simp only [bind_tc_ok, ok.injEq, Prod.mk.injEq] at h
        obtain ⟨-, rfl⟩ := h
        have e1 := UScalar.sub_equiv r.queued 1#u32
        rw [h1] at e1
        obtain ⟨hle, hv1, -⟩ := e1
        refine ⟨{ s with queued := s.queued - 1, running := true,
                         attempts := 1 },
                ⟨by scalar_tac, by simp_all, rfl⟩, ?_⟩
        simp only [R]
        refine ⟨by simp_all, by scalar_tac, by simp_all, by simp_all,
                by simp_all, by simp_all, by simp_all⟩
      | fail e => rw [h1] at h; simp at h
      | div => rw [h1] at h; simp at h

theorem complete_sim {s r o r'}
    (hR : R s r) (h : queue.JobQueue.complete r = ok (o, r')) :
    r' = r ∨ ∃ s', completeStep s s' ∧ R s' r' := by
  obtain ⟨hcap, hq, hrun, hat, hd, hf, hs⟩ := hR
  rw [queue.JobQueue.complete] at h
  split at h
  · rename_i hrun'
    right
    cases h1 : r.done + 1#u32 with
    | ok i =>
      rw [h1] at h
      simp only [bind_tc_ok, ok.injEq, Prod.mk.injEq] at h
      obtain ⟨-, rfl⟩ := h
      have e1 := UScalar.add_equiv r.done 1#u32
      rw [h1] at e1
      obtain ⟨-, hv1, -⟩ := e1
      refine ⟨{ s with running := false, attempts := 0,
                       done := s.done + 1 },
              ⟨by simp_all, rfl⟩, ?_⟩
      simp only [R]
      refine ⟨by simp_all, by simp_all, by simp_all, by simp_all,
              by scalar_tac, by simp_all, by simp_all⟩
    | fail e => rw [h1] at h; simp at h
    | div => rw [h1] at h; simp at h
  · left
    simp only [ok.injEq, Prod.mk.injEq] at h
    exact h.2.symm

theorem fail_sim {s r o r'}
    (hR : R s r) (hb1 : s.attempts ≤ MAX_ATTEMPTS)
    (h : queue.JobQueue.fail r = ok (o, r')) :
    r' = r ∨ (∃ s', failRetryStep s s' ∧ R s' r') ∨
    (∃ s', failFinalStep s s' ∧ R s' r') := by
  obtain ⟨hcap, hq, hrun, hat, hd, hf, hs⟩ := hR
  rw [queue.JobQueue.fail] at h
  split at h
  · rename_i hrun'
    split at h
    · rename_i hlt
      right; left
      cases h1 : r.attempts + 1#u32 with
      | ok i =>
        rw [h1] at h
        simp only [bind_tc_ok, ok.injEq, Prod.mk.injEq] at h
        obtain ⟨-, rfl⟩ := h
        have e1 := UScalar.add_equiv r.attempts 1#u32
        rw [h1] at e1
        obtain ⟨-, hv1, -⟩ := e1
        refine ⟨{ s with attempts := s.attempts + 1 },
                ⟨by simp_all,
                 by simp only [MAX_ATTEMPTS]
                    simp only [queue.MAX_ATTEMPTS] at hlt
                    scalar_tac,
                 rfl⟩, ?_⟩
        simp only [R]
        refine ⟨by simp_all, by simp_all, by simp_all, by scalar_tac,
                by simp_all, by simp_all, by simp_all⟩
      | fail e => rw [h1] at h; simp at h
      | div => rw [h1] at h; simp at h
    · rename_i hge
      right; right
      cases h1 : r.failed + 1#u32 with
      | ok i =>
        rw [h1] at h
        simp only [bind_tc_ok, ok.injEq, Prod.mk.injEq] at h
        obtain ⟨-, rfl⟩ := h
        have e1 := UScalar.add_equiv r.failed 1#u32
        rw [h1] at e1
        obtain ⟨-, hv1, -⟩ := e1
        refine ⟨{ s with running := false, attempts := 0,
                         failed := s.failed + 1 },
                ⟨by simp_all,
                 by simp only [MAX_ATTEMPTS] at *
                    simp only [queue.MAX_ATTEMPTS] at hge
                    scalar_tac,
                 rfl⟩, ?_⟩
        simp only [R]
        refine ⟨by simp_all, by simp_all, by simp_all, by simp_all,
                by simp_all, by scalar_tac, by simp_all⟩
      | fail e => rw [h1] at h; simp at h
      | div => rw [h1] at h; simp at h
  · left
    simp only [ok.injEq, Prod.mk.injEq] at h
    exact h.2.symm

/-! ## Main refinement theorem -/

/-- Every reachable extracted state is R-related to a reachable spec
    state: the code refines the spec. -/
theorem rust_refines_spec {r : queue.JobQueue} (h : RustReach r) :
    ∃ s, QReach s ∧ R s r := by
  induction h with
  | init h => exact ⟨QInit, QReach.init, init_sim h⟩
  | submit _ h ih =>
    obtain ⟨s, hreach, hR⟩ := ih
    rcases submit_sim hR h with rfl | ⟨s', hstep, hR'⟩
    · exact ⟨s, hreach, hR⟩
    · exact ⟨s', QReach.step hreach (Or.inl hstep), hR'⟩
  | start _ h ih =>
    obtain ⟨s, hreach, hR⟩ := ih
    rcases start_sim hR h with rfl | ⟨s', hstep, hR'⟩
    · exact ⟨s, hreach, hR⟩
    · exact ⟨s', QReach.step hreach (Or.inr (Or.inl hstep)), hR'⟩
  | complete _ h ih =>
    obtain ⟨s, hreach, hR⟩ := ih
    rcases complete_sim hR h with rfl | ⟨s', hstep, hR'⟩
    · exact ⟨s, hreach, hR⟩
    · exact ⟨s', QReach.step hreach (Or.inr (Or.inr (Or.inl hstep))), hR'⟩
  | fail _ h ih =>
    obtain ⟨s, hreach, hR⟩ := ih
    have hb1 := (QReach_inv hreach).1
    rcases fail_sim hR hb1 h with rfl | ⟨s', hstep, hR'⟩ | ⟨s', hstep, hR'⟩
    · exact ⟨s, hreach, hR⟩
    · exact ⟨s', QReach.step hreach
        (Or.inr (Or.inr (Or.inr (Or.inl hstep)))), hR'⟩
    · exact ⟨s', QReach.step hreach
        (Or.inr (Or.inr (Or.inr (Or.inr hstep)))), hR'⟩

/-! ## Invariant transfer: the payoff corollaries -/

/-- B1 transfers: no reachable extracted state exceeds the attempt budget. -/
theorem rust_b1 {r : queue.JobQueue} (h : RustReach r) :
    r.attempts.val ≤ 3 := by
  obtain ⟨s, hreach, hR⟩ := rust_refines_spec h
  have hinv := QReach_inv hreach
  have := hinv.1
  have := hR.2.2.2.1
  simp only [MAX_ATTEMPTS] at *
  omega

/-- B4 transfers: no reachable extracted state exceeds capacity 2. -/
theorem rust_b4 {r : queue.JobQueue} (h : RustReach r) :
    r.queued.val ≤ 2 := by
  obtain ⟨s, hreach, hR⟩ := rust_refines_spec h
  have hinv := QReach_inv hreach
  have := hinv.2.2.2.1
  have := hR.2.1
  simp only [CAPACITY] at *
  omega

/-- B2 transfers: conservation holds of every reachable extracted state. -/
theorem rust_b2 {r : queue.JobQueue} (h : RustReach r) :
    (r.queued.val : Int) + (if r.running then 1 else 0) + r.done.val
      + r.failed.val = r.submitted.val := by
  obtain ⟨s, hreach, hR⟩ := rust_refines_spec h
  have hinv := QReach_inv hreach
  obtain ⟨-, hq, hrun, -, hd, hf, hs⟩ := hR
  have hb2 := hinv.2.1
  rw [hq, hrun, hd, hf, hs]
  exact hb2

/-- B3 transfers (biconditional). -/
theorem rust_b3 {r : queue.JobQueue} (h : RustReach r) :
    (r.running = false → r.attempts.val = 0) ∧
    (r.running = true → 1 ≤ r.attempts.val ∧ r.attempts.val ≤ 3) := by
  obtain ⟨s, hreach, hR⟩ := rust_refines_spec h
  have hinv := QReach_inv hreach
  obtain ⟨-, -, hrun, hat, -, -, -⟩ := hR
  obtain ⟨-, -, ⟨h3i, h3r⟩, -, -⟩ := hinv
  constructor
  · intro hf
    have := h3i (hrun ▸ hf)
    omega
  · intro ht
    have := h3r (hrun ▸ ht)
    simp only [MAX_ATTEMPTS] at this
    omega

/-! ## B5 (terminal monotonicity), transferred as step monotonicity over
    the extracted operations (the ghost encoding's meaning). -/

theorem submit_mono {r o r'} (h : queue.JobQueue.submit r = ok (o, r')) :
    r.done.val ≤ r'.done.val ∧ r.failed.val ≤ r'.failed.val := by
  rw [queue.JobQueue.submit] at h
  split at h
  · simp only [ok.injEq, Prod.mk.injEq] at h
    obtain ⟨-, rfl⟩ := h
    exact ⟨le_refl _, le_refl _⟩
  · cases h1 : r.queued + 1#u32 with
    | ok i =>
      rw [h1] at h
      cases h2 : r.submitted + 1#u32 with
      | ok i1 =>
        rw [h2] at h
        simp only [bind_tc_ok, ok.injEq, Prod.mk.injEq] at h
        obtain ⟨-, rfl⟩ := h
        exact ⟨le_refl _, le_refl _⟩
      | fail e => rw [h2] at h; simp at h
      | div => rw [h2] at h; simp at h
    | fail e => rw [h1] at h; simp at h
    | div => rw [h1] at h; simp at h

theorem start_mono {r o r'} (h : queue.JobQueue.start r = ok (o, r')) :
    r.done.val ≤ r'.done.val ∧ r.failed.val ≤ r'.failed.val := by
  rw [queue.JobQueue.start] at h
  split at h
  · simp only [ok.injEq, Prod.mk.injEq] at h
    obtain ⟨-, rfl⟩ := h
    exact ⟨le_refl _, le_refl _⟩
  · split at h
    · simp only [ok.injEq, Prod.mk.injEq] at h
      obtain ⟨-, rfl⟩ := h
      exact ⟨le_refl _, le_refl _⟩
    · cases h1 : r.queued - 1#u32 with
      | ok i =>
        rw [h1] at h
        simp only [bind_tc_ok, ok.injEq, Prod.mk.injEq] at h
        obtain ⟨-, rfl⟩ := h
        exact ⟨le_refl _, le_refl _⟩
      | fail e => rw [h1] at h; simp at h
      | div => rw [h1] at h; simp at h

theorem complete_mono {r o r'} (h : queue.JobQueue.complete r = ok (o, r')) :
    r.done.val ≤ r'.done.val ∧ r.failed.val ≤ r'.failed.val := by
  rw [queue.JobQueue.complete] at h
  split at h
  · cases h1 : r.done + 1#u32 with
    | ok i =>
      rw [h1] at h
      simp only [bind_tc_ok, ok.injEq, Prod.mk.injEq] at h
      obtain ⟨-, rfl⟩ := h
      have e1 := UScalar.add_equiv r.done 1#u32
      rw [h1] at e1
      obtain ⟨-, hv1, -⟩ := e1
      constructor
      · simp only [hv1]; omega
      · exact le_refl _
    | fail e => rw [h1] at h; simp at h
    | div => rw [h1] at h; simp at h
  · simp only [ok.injEq, Prod.mk.injEq] at h
    obtain ⟨-, rfl⟩ := h
    exact ⟨le_refl _, le_refl _⟩

theorem fail_mono {r o r'} (h : queue.JobQueue.fail r = ok (o, r')) :
    r.done.val ≤ r'.done.val ∧ r.failed.val ≤ r'.failed.val := by
  rw [queue.JobQueue.fail] at h
  split at h
  · split at h
    · cases h1 : r.attempts + 1#u32 with
      | ok i =>
        rw [h1] at h
        simp only [bind_tc_ok, ok.injEq, Prod.mk.injEq] at h
        obtain ⟨-, rfl⟩ := h
        exact ⟨le_refl _, le_refl _⟩
      | fail e => rw [h1] at h; simp at h
      | div => rw [h1] at h; simp at h
    · cases h1 : r.failed + 1#u32 with
      | ok i =>
        rw [h1] at h
        simp only [bind_tc_ok, ok.injEq, Prod.mk.injEq] at h
        obtain ⟨-, rfl⟩ := h
        have e1 := UScalar.add_equiv r.failed 1#u32
        rw [h1] at e1
        obtain ⟨-, hv1, -⟩ := e1
        constructor
        · exact le_refl _
        · simp only [hv1]; omega
      | fail e => rw [h1] at h; simp at h
      | div => rw [h1] at h; simp at h
  · simp only [ok.injEq, Prod.mk.injEq] at h
    obtain ⟨-, rfl⟩ := h
    exact ⟨le_refl _, le_refl _⟩

end jobq.refinement
