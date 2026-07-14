import JobqRefinement
open Aeneas Aeneas.Std Result jobq jobq.refinement

/-- Non-vacuity: a concrete run new -> submit -> start -> complete is
    RustReach-able and completes one job, so the transfer theorems do not
    quantify over an empty set. -/
theorem rustreach_nonvacuous :
    ∃ r, RustReach r ∧ r.done.val = 1 := by
  have h0 : queue.JobQueue.new 2#u32 =
      ok { capacity := 2#u32, queued := 0#u32, running := false,
           attempts := 0#u32, done := 0#u32, failed := 0#u32,
           submitted := 0#u32 } := by
    rw [queue.JobQueue.new]
  have r0 := RustReach.init h0
  have h1 : queue.JobQueue.submit
      { capacity := 2#u32, queued := 0#u32, running := false,
        attempts := 0#u32, done := 0#u32, failed := 0#u32,
        submitted := 0#u32 } =
      ok (core.result.Result.Ok (),
        { capacity := 2#u32, queued := 1#u32, running := false,
          attempts := 0#u32, done := 0#u32, failed := 0#u32,
          submitted := 1#u32 }) := by
    rfl
  have r1 := RustReach.submit r0 h1
  have h2 : queue.JobQueue.start
      { capacity := 2#u32, queued := 1#u32, running := false,
        attempts := 0#u32, done := 0#u32, failed := 0#u32,
        submitted := 1#u32 } =
      ok (core.result.Result.Ok (),
        { capacity := 2#u32, queued := 0#u32, running := true,
          attempts := 1#u32, done := 0#u32, failed := 0#u32,
          submitted := 1#u32 }) := by
    rfl
  have r2 := RustReach.start r1 h2
  have h3 : queue.JobQueue.complete
      { capacity := 2#u32, queued := 0#u32, running := true,
        attempts := 1#u32, done := 0#u32, failed := 0#u32,
        submitted := 1#u32 } =
      ok (core.result.Result.Ok (),
        { capacity := 2#u32, queued := 0#u32, running := false,
          attempts := 0#u32, done := 1#u32, failed := 0#u32,
          submitted := 1#u32 }) := by
    rfl
  have r3 := RustReach.complete r2 h3
  exact ⟨_, r3, rfl⟩

#print axioms rustreach_nonvacuous
