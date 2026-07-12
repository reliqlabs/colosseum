"""Shared subprocess helper for the CLI-backed Colosseum MCP servers.

The kani/verus/quint/aeneas wrappers all shell out to external tools that
spawn their own children (CBMC, Apalache, cargo, charon). This module gives
them one hardened `run` with:

  - process-group termination: the child is started in its own session
    (`start_new_session=True`) so a timeout can `os.killpg` the whole group.
    A per-process `proc.kill()` leaves the tool's grandchildren orphaned
    (reproduced with CBMC/Apalache/cargo holding the stdout pipe open).
  - partial-output capture on timeout: stdout/stderr are drained
    concurrently into head+tail buffers, so whatever arrived before the
    kill is returned, flagged `timed_out=True`.
  - head+tail capping with the truncation summary line FIRST, so the tail
    (where tool verdicts live) is never silently dropped.

It also provides `reconcile_status`, the contract every caller uses to make
a parsed "ok" impossible when the process timed out or exited nonzero.

Pure stdlib: importable inside each server's `uv run --script` environment
without adding an inline dependency.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
from typing import Any

# Per-stream capture budget. Real tool output is far below this, so nothing
# is truncated in practice; only pathological runaway output gets capped, and
# even then the tail (verdict lines) is preserved.
HEAD_BYTES = 256 * 1024
TAIL_BYTES = 512 * 1024

# Grace between SIGTERM and SIGKILL for a timed-out group, and the ceiling on
# how long we wait for the drained pipes to reach EOF after the group exits.
TERM_GRACE_S = 5.0
DRAIN_GRACE_S = 10.0


class _Capture:
    """Bounded head+tail byte accumulator for one output stream."""

    def __init__(self, head_max: int, tail_max: int) -> None:
        self._head = bytearray()
        self._tail = bytearray()
        self._head_max = head_max
        self._tail_max = tail_max
        self._total = 0
        self._dropped = 0

    def feed(self, chunk: bytes) -> None:
        self._total += len(chunk)
        if len(self._head) < self._head_max:
            room = self._head_max - len(self._head)
            self._head += chunk[:room]
            chunk = chunk[room:]
        if chunk:
            self._tail += chunk
            excess = len(self._tail) - self._tail_max
            if excess > 0:
                del self._tail[:excess]
                self._dropped += excess

    def text(self) -> str:
        head = self._head.decode("utf-8", "replace")
        if self._dropped == 0:
            # Everything fit: head+tail is the verbatim stream.
            return head + self._tail.decode("utf-8", "replace")
        tail = self._tail.decode("utf-8", "replace")
        summary = (
            f"[runproc: output truncated — kept first {len(self._head)} B and "
            f"last {len(self._tail)} B of {self._total} B total; "
            f"{self._dropped} B elided from the middle]\n"
        )
        return summary + head + "\n...\n" + tail


def cap_text(
    text: str, head_bytes: int = HEAD_BYTES, tail_bytes: int = TAIL_BYTES
) -> str:
    """Cap a string head+tail, prepending the truncation summary when it fires."""
    data = text.encode("utf-8", "replace")
    if len(data) <= head_bytes + tail_bytes:
        return text
    cap = _Capture(head_bytes, tail_bytes)
    cap.feed(data)
    return cap.text()


async def _drain(stream: asyncio.StreamReader, cap: _Capture) -> None:
    while True:
        try:
            chunk = await stream.read(65536)
        except Exception:  # noqa: BLE001 - keep whatever we captured
            break
        if not chunk:
            break
        cap.feed(chunk)


def _killpg(pgid: int, sig: int) -> None:
    with contextlib.suppress(ProcessLookupError, PermissionError, OSError):
        os.killpg(pgid, sig)


async def _terminate_group(proc: asyncio.subprocess.Process, pgid: int,
                           grace: float) -> None:
    _killpg(pgid, signal.SIGTERM)
    try:
        await asyncio.wait_for(proc.wait(), grace)
    except asyncio.TimeoutError:
        _killpg(pgid, signal.SIGKILL)
        with contextlib.suppress(Exception):
            await asyncio.wait_for(proc.wait(), 5.0)


async def run(
    cmd: list[str],
    cwd: str,
    timeout: float,
    *,
    term_grace: float = TERM_GRACE_S,
    head_bytes: int = HEAD_BYTES,
    tail_bytes: int = TAIL_BYTES,
) -> dict[str, Any]:
    """Run `cmd` in its own process group, capturing (possibly partial) output.

    Returns a dict with `returncode`, `timed_out`, capped `stdout`/`stderr`,
    and `pid`/`pgid` (the group probed for reaping in tests). On timeout the
    whole process group is signalled, not just the direct child.
    """
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
    )
    # start_new_session makes the child a group leader: pgid == pid. Capture it
    # while the process is alive so we can signal the group after it exits too.
    try:
        pgid = os.getpgid(proc.pid)
    except OSError:
        pgid = proc.pid

    out_cap = _Capture(head_bytes, tail_bytes)
    err_cap = _Capture(head_bytes, tail_bytes)
    drains = asyncio.gather(_drain(proc.stdout, out_cap), _drain(proc.stderr, err_cap))

    timed_out = False
    try:
        await asyncio.wait_for(proc.wait(), timeout)
    except asyncio.TimeoutError:
        timed_out = True
        await _terminate_group(proc, pgid, term_grace)

    # Pipes reach EOF once every group member (including orphaned children that
    # inherited the write end) is dead; the group kill above guarantees that.
    try:
        await asyncio.wait_for(drains, DRAIN_GRACE_S)
    except asyncio.TimeoutError:
        drains.cancel()
        with contextlib.suppress(Exception):
            await drains

    if proc.returncode is None:
        with contextlib.suppress(Exception):
            await asyncio.wait_for(proc.wait(), 5.0)

    return {
        "timed_out": timed_out,
        "returncode": proc.returncode if proc.returncode is not None else -1,
        "stdout": out_cap.text(),
        "stderr": err_cap.text(),
        "pid": proc.pid,
        "pgid": pgid,
    }


def reconcile_status(
    claimed_ok: bool, returncode: int, timed_out: bool
) -> dict[str, Any]:
    """Reconcile a parsed success claim against the process outcome.

    A parse that reports success is inconsistent whenever the process timed
    out or exited nonzero. Callers must downgrade such a verdict rather than
    surface it as ok.
    """
    if claimed_ok and timed_out:
        return {"consistent": False, "reason": "parse reported ok but the process timed out"}
    if claimed_ok and returncode != 0:
        return {
            "consistent": False,
            "reason": f"parse reported ok but returncode={returncode}",
        }
    return {"consistent": True, "reason": None}
