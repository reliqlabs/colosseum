// R9/R19 fixture (E3): a small flow with deliberate obligation defects.
//   inv_positive        real invariant (holds, references state)
//   inv_vacuous         literally true — vacuity fixture
//   witness_reach_16    reachable (1 -> 2 -> 4 -> 8 -> 16 via dbl)
//   witness_unreachable denies a state that cannot occur — unreachable fixture
//   never               guard is false — disabled-transition fixture
module flow {
  var x: int
  var steps: int

  action init = all { x' = 1, steps' = 0 }

  action inc = all {
    steps < 10,
    steps' = steps + 1,
    x' = x + 1,
  }

  action dbl = all {
    steps < 10,
    steps' = steps + 1,
    x' = 2 * x,
  }

  action never = all {
    false,
    steps' = steps,
    x' = x,
  }

  action stay = all {
    steps >= 10,
    steps' = steps,
    x' = x,
  }

  action step = any { inc, dbl, never, stay }

  val inv_positive = x >= 1
  val inv_vacuous = true
  val witness_reach_16 = not(x == 16)
  val witness_unreachable = not(x < 0)
}
