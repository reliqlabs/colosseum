# Intent: flow fixture (conformance)

A counter starts at 1 and, for ten steps, either increments or doubles;
after ten steps it holds. The Rust adapter implements the same machine.

- CONF1: the implementation's step-by-step behavior conforms to the
  flow.qnt model on seeded replayed traces.
