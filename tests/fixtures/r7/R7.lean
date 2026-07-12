-- R7 fixture (E2, contract G2): one proven theorem, one sorry-admitted.
-- `lake build` exits 0 on both (warning only) — the false-green this
-- fixture exists to demonstrate. Only the axiom audit separates them.

theorem complete_thm : 1 + 1 = 2 := rfl

theorem incomplete_thm : ∀ n : Nat, n + 0 = n := by sorry
