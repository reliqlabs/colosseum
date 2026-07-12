-- Tiny Aeneas-shaped extraction output for the aeneas list_extracted_definitions
-- smoke half of the MCP suite. No toolchain required to walk it.

def foo (x : Nat) : Nat := x + 1

theorem foo_pos (x : Nat) : foo x > 0 := by
  simp [foo]

structure Pair where
  a : Nat
  b : Nat
