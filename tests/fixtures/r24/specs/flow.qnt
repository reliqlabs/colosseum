// R24 fixture (C2): the counter machine the Rust adapter mirrors.
// Traces are generated seeded (quint run --out-itf) and replayed through
// the adapter by scripts/itf_replay.py.
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

  action stay = all {
    steps >= 10,
    steps' = steps,
    x' = x,
  }

  action step = any { inc, dbl, stay }
}
