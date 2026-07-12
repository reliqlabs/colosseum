// R8 fixture — rare-path defect (E1, contract G3).
//
// From x=1, each of 20 steps doubles x and nondeterministically adds a bit.
// Exactly one of the 2^20 paths reaches TARGET, so `quint run` with 100
// random samples misses the violation (probability ~1e-4, pinned by seed in
// the test) while `quint verify` finds it exhaustively at depth 20. The two
// results are different evidence classes: simulation vs bounded checking.
module rare {
  var x: int
  var steps: int

  action init = all {
    x' = 1,
    steps' = 0,
  }

  action grow = all {
    steps < 20,
    steps' = steps + 1,
    any {
      x' = 2 * x,
      x' = 2 * x + 1,
    },
  }

  action stay = all {
    steps >= 20,
    steps' = steps,
    x' = x,
  }

  action step = any {
    grow,
    stay,
  }

  val safety = x != 1445717
}
