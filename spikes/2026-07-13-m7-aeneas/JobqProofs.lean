import Jobq
open Aeneas Aeneas.Std Result

namespace jobq

/-- B1 over the extracted `fail`: if a `fail` call succeeds, the resulting
    `attempts` field never exceeds `MAX_ATTEMPTS = 3`, given a well-formed
    input (`attempts ≤ 3`). Quantifies over successful results only, since
    `fail` can itself overflow on the `failed + 1` path. -/
theorem fail_preserves_b1
    (self : queue.JobQueue)
    (o : core.result.Result queue.FailOutcome queue.QueueError)
    (self' : queue.JobQueue)
    (hwf : self.attempts.val ≤ 3)
    (h : queue.JobQueue.fail self = ok (o, self')) :
    self'.attempts.val ≤ 3 := by
  rw [queue.JobQueue.fail] at h
  split at h
  · -- self.running = true
    split at h
    · -- self.attempts < MAX_ATTEMPTS : retry path, attempts' = attempts + 1
      rename_i hlt
      cases hi : self.attempts + 1#u32 with
      | ok i =>
        rw [hi] at h
        simp only [bind_tc_ok, ok.injEq, Prod.mk.injEq] at h
        obtain ⟨_, rfl⟩ := h
        have hspec := UScalar.add_spec (x := self.attempts) (y := 1#u32) (by scalar_tac)
        rw [hi] at hspec
        simp only [WP.spec_ok] at hspec
        simp only [queue.MAX_ATTEMPTS] at hlt
        scalar_tac
      | fail e => rw [hi] at h; simp at h
      | div => rw [hi] at h; simp at h
    · -- attempts >= MAX_ATTEMPTS : exhausted path, attempts' = 0
      cases hi : self.failed + 1#u32 with
      | ok i =>
        rw [hi] at h
        simp only [bind_tc_ok, ok.injEq, Prod.mk.injEq] at h
        obtain ⟨_, rfl⟩ := h
        scalar_tac
      | fail e => rw [hi] at h; simp at h
      | div => rw [hi] at h; simp at h
  · -- self.running = false : NotRunning, state unchanged
    simp only [ok.injEq, Prod.mk.injEq] at h
    obtain ⟨_, rfl⟩ := h
    exact hwf

end jobq
