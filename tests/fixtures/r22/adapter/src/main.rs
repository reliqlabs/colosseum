//! R22 conformance adapter: drives the REAL `jobq` library (path
//! dependency, not a re-implementation) over the itf-replay v1 line
//! protocol (see scripts/itf_replay.py). Transition selection is delta
//! inference: from the expected post-state, pick the one jobq operation
//! whose contract produces that delta, apply it, and report the library's
//! actual state. Any drift between spec and code surfaces as a STATE
//! mismatch at the exact step.

use std::io::{self, BufRead, Write};

use jobq::JobQueue;

// Mirrors CAPACITY in specs/jobq.qnt.
const CAPACITY: u32 = 3;

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
struct Snap {
    queued: i64,
    running: bool,
    attempts: i64,
    done: i64,
    failed: i64,
    submitted: i64,
}

fn snap(q: &JobQueue) -> Snap {
    Snap {
        queued: q.queued() as i64,
        running: q.is_running(),
        attempts: q.attempts() as i64,
        done: q.done() as i64,
        failed: q.failed() as i64,
        submitted: q.submitted() as i64,
    }
}

fn apply_toward(q: &mut JobQueue, exp: Snap) -> Result<(), String> {
    let cur = snap(q);
    if exp == cur {
        return Ok(()); // stutter
    }
    let outcome = if exp.submitted == cur.submitted + 1 && exp.queued == cur.queued + 1 {
        q.submit().map(|_| ()).map_err(|e| format!("{e:?}"))
    } else if exp.queued == cur.queued - 1 && exp.running && !cur.running {
        q.start().map(|_| ()).map_err(|e| format!("{e:?}"))
    } else if exp.done == cur.done + 1 && !exp.running && cur.running {
        q.complete().map(|_| ()).map_err(|e| format!("{e:?}"))
    } else if exp.attempts == cur.attempts + 1 && exp.running && cur.running {
        q.fail().map(|_| ()).map_err(|e| format!("{e:?}"))
    } else if exp.failed == cur.failed + 1 && !exp.running && cur.running {
        q.fail().map(|_| ()).map_err(|e| format!("{e:?}"))
    } else {
        Err(format!("unknown-transition toward {exp:?} from {cur:?}"))
    };
    outcome
}

fn parse_bindings(rest: &str) -> Result<Snap, String> {
    let (mut queued, mut running, mut attempts) = (None, None, None);
    let (mut done, mut failed, mut submitted) = (None, None, None);
    for tok in rest.split_whitespace() {
        let (name, val) = tok
            .split_once('=')
            .ok_or_else(|| format!("bad binding {tok:?}"))?;
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
    })
}

fn emit_state(out: &mut impl Write, s: Snap) -> io::Result<()> {
    writeln!(
        out,
        "STATE queued={} running={} attempts={} done={} failed={} submitted={}",
        s.queued, s.running, s.attempts, s.done, s.failed, s.submitted
    )
}

fn main() -> io::Result<()> {
    let stdin = io::stdin();
    let mut stdout = io::stdout();
    let mut queue: Option<JobQueue> = None;

    for line in stdin.lock().lines() {
        let line = line?;
        let line = line.trim();
        if line.is_empty() {
            continue;
        }
        let (cmd, rest) = line.split_once(' ').unwrap_or((line, ""));
        match cmd {
            "VARS" => { /* declared upstream; no reply */ }
            "INIT" => {
                let exp = match parse_bindings(rest) {
                    Ok(s) => s,
                    Err(e) => {
                        writeln!(stdout, "ERR {e}")?;
                        stdout.flush()?;
                        continue;
                    }
                };
                let q = JobQueue::new(CAPACITY);
                let cur = snap(&q);
                if cur != exp {
                    writeln!(stdout, "ERR init-mismatch expected {exp:?} got {cur:?}")?;
                } else {
                    emit_state(&mut stdout, cur)?;
                }
                queue = Some(q);
                stdout.flush()?;
            }
            "EXPECT" => {
                let Some(q) = queue.as_mut() else {
                    writeln!(stdout, "ERR EXPECT before INIT")?;
                    stdout.flush()?;
                    continue;
                };
                match parse_bindings(rest).and_then(|exp| apply_toward(q, exp)) {
                    Ok(()) => emit_state(&mut stdout, snap(q))?,
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
