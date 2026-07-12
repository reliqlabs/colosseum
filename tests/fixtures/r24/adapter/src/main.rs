//! R24 fixture adapter: the Rust implementation of the flow.qnt counter
//! machine, speaking the itf-replay v1 line protocol (see
//! scripts/itf_replay.py). std-only by design so replay adapters need no
//! dependencies.
//!
//! Seeded divergence: with COLOSSEUM_R24_BUG=1 the dbl implementation
//! saturates at 64, a bound the spec does not have. Replay must catch the
//! first step where a doubling crosses it.

use std::io::{self, BufRead, Write};

const BUG_SATURATION: i64 = 64;

struct Machine {
    x: i64,
    steps: i64,
    bug: bool,
}

impl Machine {
    // Applies this implementation's transition corresponding to the
    // expected post-state (inference by delta: stay / inc / dbl).
    fn apply_toward(&mut self, exp_x: i64, exp_steps: i64) -> Result<(), String> {
        if exp_steps == self.steps && exp_x == self.x {
            // stay
            Ok(())
        } else if exp_steps == self.steps + 1 && exp_x == self.x + 1 {
            self.x += 1;
            self.steps += 1;
            Ok(())
        } else if exp_steps == self.steps + 1 && exp_x == 2 * self.x {
            let doubled = 2 * self.x;
            self.x = if self.bug && doubled > BUG_SATURATION {
                BUG_SATURATION
            } else {
                doubled
            };
            self.steps += 1;
            Ok(())
        } else {
            Err(format!(
                "unknown-transition from x={} steps={} toward x={} steps={}",
                self.x, self.steps, exp_x, exp_steps
            ))
        }
    }
}

fn parse_bindings(rest: &str) -> Result<(i64, i64), String> {
    let (mut x, mut steps) = (None, None);
    for tok in rest.split_whitespace() {
        let (name, val) = tok
            .split_once('=')
            .ok_or_else(|| format!("bad binding {tok:?}"))?;
        let v: i64 = val.parse().map_err(|_| format!("bad int {val:?}"))?;
        match name {
            "x" => x = Some(v),
            "steps" => steps = Some(v),
            other => return Err(format!("unknown var {other:?}")),
        }
    }
    match (x, steps) {
        (Some(x), Some(s)) => Ok((x, s)),
        _ => Err("missing x or steps binding".into()),
    }
}

fn main() {
    let bug = std::env::var("COLOSSEUM_R24_BUG").as_deref() == Ok("1");
    let stdin = io::stdin();
    let mut out = io::stdout();
    let mut machine: Option<Machine> = None;

    for line in stdin.lock().lines() {
        let line = line.expect("stdin read");
        let line = line.trim();
        let reply = if let Some(rest) = line.strip_prefix("VARS ") {
            let mut vars: Vec<&str> = rest.split_whitespace().collect();
            vars.sort_unstable();
            if vars == ["steps", "x"] {
                None // acknowledged silently; INIT carries the values
            } else {
                Some(format!("ERR unsupported vars {vars:?}"))
            }
        } else if let Some(rest) = line.strip_prefix("INIT ") {
            match parse_bindings(rest) {
                Ok((x, steps)) => {
                    // The implementation initializes ITSELF; INIT bindings
                    // are only checked against the implementation's init.
                    let m = Machine { x: 1, steps: 0, bug };
                    let reply = if m.x == x && m.steps == steps {
                        format!("STATE x={} steps={}", m.x, m.steps)
                    } else {
                        format!("ERR init-mismatch impl x={} steps={}", m.x, m.steps)
                    };
                    machine = Some(m);
                    Some(reply)
                }
                Err(e) => Some(format!("ERR {e}")),
            }
        } else if let Some(rest) = line.strip_prefix("EXPECT ") {
            match (machine.as_mut(), parse_bindings(rest)) {
                (Some(m), Ok((x, steps))) => Some(match m.apply_toward(x, steps) {
                    Ok(()) => format!("STATE x={} steps={}", m.x, m.steps),
                    Err(e) => format!("ERR {e}"),
                }),
                (None, _) => Some("ERR EXPECT before INIT".into()),
                (_, Err(e)) => Some(format!("ERR {e}")),
            }
        } else if line == "END" {
            break;
        } else {
            Some(format!("ERR unknown-command {line:?}"))
        };
        if let Some(reply) = reply {
            writeln!(out, "{reply}").expect("stdout write");
            out.flush().expect("stdout flush");
        }
    }
}
