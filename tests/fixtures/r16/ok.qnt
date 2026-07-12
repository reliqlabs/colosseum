// Minimal always-satisfied spec for the quint smoke half of the MCP suite.
// `inv_nonneg` holds on every reachable state, so `quint run` reports [ok].
module ok {
  var counter: int

  action init = counter' = 0
  action step = counter' = counter + 1

  val inv_nonneg = counter >= 0
}
