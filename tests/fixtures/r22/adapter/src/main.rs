//! R22 conformance adapter: drives the REAL `jobq` library (path
//! dependency, not a re-implementation) over the itf-replay v1 line
//! protocol (see scripts/itf_replay.py). Transition selection is delta
//! inference: from the expected post-state, pick the one jobq operation
//! whose contract produces that delta, apply it, and report the library's
//! actual state. Any drift between spec and code surfaces as a STATE
//! mismatch at the exact step.
//!
//! The spec carries two ghost variables (prev_done, prev_failed: the
//! previous state's terminal counts, backing the B5 monotonicity
//! invariant). The library has no such fields; the adapter tracks them
//! itself, snapshotting the pre-transition counts whenever it applies an
//! operation. A spec whose ghost discipline drifts from "previous state's
//! value" therefore also surfaces as a STATE mismatch.

use std::io::{self, BufRead, Write};

use jobq::JobQueue;

// Mirrors the default instance in specs/jobq.qnt (module jobq: CAPACITY = 2,
// deliberately distinct from MAX_ATTEMPTS = 3).
const CAPACITY: u32 = 2;

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
struct Snap {
    queued: i64,
    running: bool,
    attempts: i64,
    done: i64,
    failed: i64,
    submitted: i64,
    prev_done: i64,
    prev_failed: i64,
}

struct Machine {
    q: JobQueue,
    prev_done: i64,
    prev_failed: i64,
}

impl Machine {
    fn new() -> Self {
        Machine { q: JobQueue::new(CAPACITY), prev_done: 0, prev_failed: 0 }
    }

    fn snap(&self) -> Snap {
        Snap {
            queued: self.q.queued() as i64,
            running: self.q.is_running(),
            attempts: self.q.attempts() as i64,
            done: self.q.done() as i64,
            failed: self.q.failed() as i64,
            submitted: self.q.submitted() as i64,
            prev_done: self.prev_done,
            prev_failed: self.prev_failed,
        }
    }

    fn apply_toward(&mut self, exp: Snap) -> Result<(), String> {
        let cur = self.snap();
        if exp == cur {
            return Ok(()); // stutter
        }
        // Ghost update: every real transition snapshots the pre-state
        // terminal counts, exactly as the spec's actions do.
        let (pd, pf) = (cur.done, cur.failed);
        let outcome = if exp.submitted == cur.submitted + 1 && exp.queued == cur.queued + 1 {
            self.q.submit().map(|_| ()).map_err(|e| format!("{e:?}"))
        } else if exp.queued == cur.queued - 1 && exp.running && !cur.running {
            self.q.start().map(|_| ()).map_err(|e| format!("{e:?}"))
        } else if exp.done == cur.done + 1 && !exp.running && cur.running {
            self.q.complete().map(|_| ()).map_err(|e| format!("{e:?}"))
        } else if exp.attempts == cur.attempts + 1 && exp.running && cur.running {
            self.q.fail().map(|_| ()).map_err(|e| format!("{e:?}"))
        } else if exp.failed == cur.failed + 1 && !exp.running && cur.running {
            self.q.fail().map(|_| ()).map_err(|e| format!("{e:?}"))
        } else {
            Err(format!("unknown-transition toward {exp:?} from {cur:?}"))
        };
        if outcome.is_ok() {
            self.prev_done = pd;
            self.prev_failed = pf;
        }
        outcome
    }
}

fn parse_bindings(rest: &str) -> Result<Snap, String> {
    let (mut queued, mut running, mut attempts) = (None, None, None);
    let (mut done, mut failed, mut submitted) = (None, None, None);
    let (mut prev_done, mut prev_failed) = (None, None);
    for tok in rest.split_whitespace() {
        let (name, val) = tok
            .split_once('=')
            .ok_or_else(|| format!("bad binding {tok:?}"))?;
        // Instanced Quint modules qualify trace var names
        // (jobq::jobqP::attempts); the state vocabulary is the last segment.
        let name = name.rsplit("::").next().unwrap_or(name);
        match name {
            "running" => {
                running = Some(val.parse::<bool>().map_err(|_| format!("bad bool {val:?}"))?)
            }
            _ => {
                let v: i64 = val.parse().map_err(|_| format!("bad int {val:?}"))?;
                match name {
                    "queued" => queued = Some(v),
                    "attempts" => attempts = Some(v),
                    "done" => done = Some(v),
                    "failed" => failed = Some(v),
                    "submitted" => submitted = Some(v),
                    "prev_done" => prev_done = Some(v),
                    "prev_failed" => prev_failed = Some(v),
                    other => return Err(format!("unknown var {other:?}")),
                }
            }
        }
    }
    Ok(Snap {
        queued: queued.ok_or("missing queued")?,
        running: running.ok_or("missing running")?,
        attempts: attempts.ok_or("missing attempts")?,
        done: done.ok_or("missing done")?,
        failed: failed.ok_or("missing failed")?,
        submitted: submitted.ok_or("missing submitted")?,
        prev_done: prev_done.ok_or("missing prev_done")?,
        prev_failed: prev_failed.ok_or("missing prev_failed")?,
    })
}

fn emit_state(out: &mut impl Write, s: Snap, names: &Names) -> io::Result<()> {
    writeln!(
        out,
        "STATE {}={} {}={} {}={} {}={} {}={} {}={} {}={} {}={}",
        names.get("queued"), s.queued,
        names.get("running"), s.running,
        names.get("attempts"), s.attempts,
        names.get("done"), s.done,
        names.get("failed"), s.failed,
        names.get("submitted"), s.submitted,
        names.get("prev_done"), s.prev_done,
        names.get("prev_failed"), s.prev_failed,
    )
}

/// The driver compares STATE bindings by the trace's own (possibly
/// module-qualified) var names; echo whatever the VARS line declared.
struct Names {
    full: Vec<String>,
}

impl Names {
    fn new() -> Self {
        Names { full: Vec::new() }
    }

    fn declare(&mut self, rest: &str) {
        self.full = rest.split_whitespace().map(str::to_string).collect();
    }

    fn get<'a>(&'a self, short: &'a str) -> &'a str {
        self.full
            .iter()
            .find(|f| f.rsplit("::").next() == Some(short))
            .map(String::as_str)
            .unwrap_or(short)
    }
}

fn main() -> io::Result<()> {
    let stdin = io::stdin();
    let mut stdout = io::stdout();
    let mut machine: Option<Machine> = None;
    let mut names = Names::new();

    for line in stdin.lock().lines() {
        let line = line?;
        let line = line.trim();
        if line.is_empty() {
            continue;
        }
        let (cmd, rest) = line.split_once(' ').unwrap_or((line, ""));
        match cmd {
            "VARS" => names.declare(rest), // no reply
            "INIT" => {
                let exp = match parse_bindings(rest) {
                    Ok(s) => s,
                    Err(e) => {
                        writeln!(stdout, "ERR {e}")?;
                        stdout.flush()?;
                        continue;
                    }
                };
                let m = Machine::new();
                let cur = m.snap();
                if cur != exp {
                    writeln!(stdout, "ERR init-mismatch expected {exp:?} got {cur:?}")?;
                } else {
                    emit_state(&mut stdout, cur, &names)?;
                }
                machine = Some(m);
                stdout.flush()?;
            }
            "EXPECT" => {
                let Some(m) = machine.as_mut() else {
                    writeln!(stdout, "ERR EXPECT before INIT")?;
                    stdout.flush()?;
                    continue;
                };
                match parse_bindings(rest).and_then(|exp| m.apply_toward(exp)) {
                    Ok(()) => emit_state(&mut stdout, m.snap(), &names)?,
                    Err(e) => writeln!(stdout, "ERR {e}")?,
                }
                stdout.flush()?;
            }
            "END" => break,
            other => {
                writeln!(stdout, "ERR unknown command {other:?}")?;
                stdout.flush()?;
            }
        }
    }
    Ok(())
}
