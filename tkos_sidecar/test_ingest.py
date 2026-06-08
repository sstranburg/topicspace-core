"""Tests for the Step 1 ingestion skeleton (per Sue's 2026-06-06 directive).

Covers the five locked behaviors:

  1. Raw-line HTTP envelope (`handle_ingest_envelope`).
  2. Session initialization / finalized-session rejection.
  3. Read-path tuple shape + synthetic action_blocked count.
  4. Non-shell tool-result success/failure inference.
  5. Ordered source-line ingestion.

Plus replay idempotency and source-mutation detection.

Run with: python -m pytest tkos_sidecar/test_ingest.py -v
"""
from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path

import pytest

import sys as _sys
_sys.path.insert(0, str(Path(__file__).parent))

import rules as rules_module  # noqa: E402
from tkos import init_db, reconstruct_state  # noqa: E402
from ingest import (  # noqa: E402
    IngestError,
    IngestResult,
    OutOfOrderError,
    RuleDispatchError,
    SessionAlreadyFinalizedError,
    SourceMutationError,
    classify_line,
    classify_tool_outcome,
    finalize_session,
    handle_ingest_envelope,
    ingest_source_line,
    init_extended_db,
)


# ─── Fixtures ───────────────────────────────────────────────────────────


@pytest.fixture
def conn():
    """In-memory SQLite with both tkos.py and ingest.py DDL applied."""
    c = sqlite3.connect(":memory:")
    init_db(c)
    init_extended_db(c)
    yield c
    c.close()


SESSION = "test-session-uuid-0001"


def make_user_message(turn_id: str, content: str = "hi") -> str:
    return json.dumps({
        "timestamp": "2026-06-06T00:00:00Z",
        "type": "event_msg",
        "payload": {
            "type": "user_message",
            "turn_id": turn_id,
            "message": content,
            "images": [],
            "local_images": [],
            "text_elements": [],
        },
    })


def make_session_meta() -> str:
    return json.dumps({
        "timestamp": "2026-06-06T00:00:00Z",
        "type": "session_meta",
        "payload": {"id": "abc", "cwd": "/tmp"},
    })


def make_token_count() -> str:
    return json.dumps({
        "timestamp": "2026-06-06T00:00:00Z",
        "type": "event_msg",
        "payload": {"type": "token_count", "info": {}, "rate_limits": []},
    })


def make_unrecognized() -> str:
    return json.dumps({
        "timestamp": "2026-06-06T00:00:00Z",
        "type": "totally_unknown_kind",
        "payload": {},
    })


def make_tool_call(turn_id: str, cmd: str = "ls /tmp", call_id: str = "call_x") -> str:
    return json.dumps({
        "timestamp": "2026-06-06T00:00:00Z",
        "type": "response_item",
        "payload": {
            "type": "function_call",
            "name": "exec_command",
            "arguments": json.dumps({"cmd": cmd, "workdir": "/tmp"}),
            "call_id": call_id,
            "turn_id": turn_id,
        },
    })


def make_tool_result(turn_id: str, output: str, call_id: str = "call_x") -> str:
    return json.dumps({
        "timestamp": "2026-06-06T00:00:00Z",
        "type": "response_item",
        "payload": {
            "type": "function_call_output",
            "call_id": call_id,
            "output": output,
            "turn_id": turn_id,
        },
    })


# ─── Behavior 1: HTTP envelope ──────────────────────────────────────────


def test_envelope_dispatches_to_ingest(conn):
    envelope = {
        "session_id": SESSION,
        "source_line_number": 1,
        "raw_line": make_user_message("t1"),
    }
    result = handle_ingest_envelope(conn, envelope)
    assert isinstance(result, IngestResult)
    assert result.status == "committed"
    assert result.category == "mapped"
    assert result.event_type == "user_message"


def test_envelope_missing_keys_raises(conn):
    with pytest.raises(IngestError):
        handle_ingest_envelope(conn, {"session_id": SESSION, "source_line_number": 1})


@pytest.mark.parametrize(
    "envelope",
    [
        {"session_id": SESSION, "source_line_number": "1", "raw_line": "{}"},
        {"session_id": "", "source_line_number": 1, "raw_line": "{}"},
        {"session_id": SESSION, "source_line_number": 0, "raw_line": "{}"},
        {"session_id": SESSION, "source_line_number": True, "raw_line": "{}"},
        {"session_id": SESSION, "source_line_number": 1, "raw_line": {}},
    ],
)
def test_envelope_rejects_invalid_source_line_metadata(conn, envelope):
    with pytest.raises(IngestError):
        handle_ingest_envelope(conn, envelope)


# ─── Behavior 2: Session init + finalized rejection ─────────────────────


def test_first_ingest_creates_session_status(conn):
    assert _session_row(conn, SESSION) is None
    ingest_source_line(conn, SESSION, 1, make_user_message("t1"))
    row = _session_row(conn, SESSION)
    assert row is not None
    assert row["capture_started_at"] is not None
    assert row["capture_ended_at"] is None
    assert row["raw_rollout_sha256"] is None  # nullable until finalize
    assert row["total_line_count"] is None
    assert row["admissibility_eligible"] == 1


def test_finalized_session_rejects_further_ingest(conn, tmp_path):
    # Ingest one line, write a rollout file, finalize, then try another ingest.
    ingest_source_line(conn, SESSION, 1, make_user_message("t1"))
    rollout = tmp_path / "rollout.jsonl"
    rollout.write_text(make_user_message("t1") + "\n")
    finalize_session(conn, SESSION, str(rollout))

    with pytest.raises(SessionAlreadyFinalizedError):
        ingest_source_line(conn, SESSION, 2, make_user_message("t1"))


def test_finalized_session_rejects_replay_of_existing_line(conn, tmp_path):
    line = make_user_message("t1")
    ingest_source_line(conn, SESSION, 1, line)
    rollout = tmp_path / "rollout.jsonl"
    rollout.write_text(line + "\n")
    finalize_session(conn, SESSION, str(rollout))

    with pytest.raises(SessionAlreadyFinalizedError):
        ingest_source_line(conn, SESSION, 1, line)


def test_hash_chain_initialized_to_empty_then_extended(conn):
    # Before any ingest, no row exists.
    assert _session_row(conn, SESSION) is None
    # First ingest creates the row and extends the chain.
    ingest_source_line(conn, SESSION, 1, make_user_message("t1"))
    row = _session_row(conn, SESSION)
    assert row["line_hash_chain"] != ""
    first_chain = row["line_hash_chain"]
    # Second ingest extends further.
    ingest_source_line(conn, SESSION, 2, make_token_count())
    row = _session_row(conn, SESSION)
    assert row["line_hash_chain"] != first_chain


# ─── Behavior 3: Read-path tuple shape + synthetic action_blocked ───────


def test_reconstruct_state_returns_tuple_when_empty(conn):
    result = reconstruct_state(conn, SESSION, turn=0)
    assert isinstance(result, tuple)
    assert len(result) == 2
    beliefs, counts = result
    assert beliefs == []
    assert counts == {"active": 0, "retired": 0, "contradicted": 0}


def test_synthetic_action_blocked_appended_and_counted(conn):
    """Insert a blocker belief by hand; verify reconstruct_state appends a
    synthetic action_blocked, preserves the tuple shape, and increments
    counts['active'].
    """
    _insert_blocker(conn, SESSION, btype="validation_pending", at_turn=5)

    beliefs, counts = reconstruct_state(conn, SESSION, turn=10)

    # Two beliefs total: the persisted blocker + the synthetic action_blocked.
    assert len(beliefs) == 2
    persisted = [b for b in beliefs if not b.get("is_synthetic")]
    synthetic = [b for b in beliefs if b.get("is_synthetic")]
    assert len(persisted) == 1
    assert len(synthetic) == 1
    assert synthetic[0]["belief_type"] == "action_blocked"
    # belief_id is a deterministic string, not None (fix 4)
    assert isinstance(synthetic[0]["belief_id"], str)
    assert synthetic[0]["belief_id"].startswith("synthetic:action_blocked:")
    # counts["active"] incremented for the synthetic (fix VI)
    assert counts["active"] == 2


def test_no_synthetic_when_no_blockers(conn):
    _insert_non_blocker(conn, SESSION, btype="validation_complete", at_turn=5)
    beliefs, counts = reconstruct_state(conn, SESSION, turn=10)
    synthetic = [b for b in beliefs if b.get("is_synthetic")]
    assert synthetic == []
    # counts["active"] = 1 for the validation_complete only
    assert counts["active"] == 1


# ─── Behavior 4: Non-shell success/failure inference ────────────────────


def test_shell_tool_success_marker():
    assert classify_tool_outcome("exec_command", "Output:\nfoo\nProcess exited with code 0") == "success"


def test_shell_tool_failure_marker():
    assert classify_tool_outcome("exec_command", "Process exited with code 1") == "failure"


def test_shell_tool_no_marker_is_unknown():
    assert classify_tool_outcome("exec_command", "ambiguous output without exit line") == "unknown"


def test_nonshell_with_no_marker_is_unknown():
    # Failed apply_patch typically does not emit "Process exited" — under v0.3.1
    # rules this would have falsely succeeded; under fix δ, unknown.
    assert classify_tool_outcome("apply_patch", "Error: malformed patch hunk at line 3") == "unknown"


def test_nonshell_with_explicit_success_marker():
    assert classify_tool_outcome("apply_patch", "Patch applied to foo.py") == "success"
    assert classify_tool_outcome("write_file", "Wrote file foo.py") == "success"


# ─── Behavior 5: Ordered ingestion ──────────────────────────────────────


def test_ordered_ingestion_accepts_contiguous(conn):
    ingest_source_line(conn, SESSION, 1, make_user_message("t1"))
    ingest_source_line(conn, SESSION, 2, make_token_count())
    ingest_source_line(conn, SESSION, 3, make_session_meta())
    # No exception → contiguous ordering accepted.


def test_ordered_ingestion_rejects_gap(conn):
    ingest_source_line(conn, SESSION, 1, make_user_message("t1"))
    with pytest.raises(OutOfOrderError):
        ingest_source_line(conn, SESSION, 3, make_token_count())  # gap at 2


def test_ordered_ingestion_rejects_first_not_1(conn):
    with pytest.raises(OutOfOrderError):
        ingest_source_line(conn, SESSION, 5, make_user_message("t1"))


# ─── Replay idempotency + source-mutation ───────────────────────────────


def test_replay_idempotent_when_hash_matches(conn):
    line = make_user_message("t1")
    r1 = ingest_source_line(conn, SESSION, 1, line)
    assert r1.status == "committed"
    r2 = ingest_source_line(conn, SESSION, 1, line)
    assert r2.status == "idempotent_replay"
    assert r2.category == "mapped"
    # No second row in raw_lines.
    n = conn.execute(
        "SELECT COUNT(*) FROM raw_lines WHERE session_id=? AND source_line_number=1",
        (SESSION,),
    ).fetchone()[0]
    assert n == 1


def test_source_mutation_raises_on_hash_mismatch(conn):
    ingest_source_line(conn, SESSION, 1, make_user_message("t1", content="original"))
    with pytest.raises(SourceMutationError):
        ingest_source_line(conn, SESSION, 1, make_user_message("t1", content="MUTATED"))


# ─── Misc: ignored-known + unrecognized classification ──────────────────


def test_session_meta_classified_ignored_known(conn):
    r = ingest_source_line(conn, SESSION, 1, make_session_meta())
    assert r.category == "ignored-known"
    n = conn.execute(
        "SELECT COUNT(*) FROM raw_lines WHERE session_id=? AND category='ignored-known'",
        (SESSION,),
    ).fetchone()[0]
    assert n == 1
    # No event written.
    ev = conn.execute("SELECT COUNT(*) FROM events WHERE session_id=?", (SESSION,)).fetchone()[0]
    assert ev == 0


def test_unrecognized_flips_admissibility(conn):
    ingest_source_line(conn, SESSION, 1, make_unrecognized())
    row = _session_row(conn, SESSION)
    assert row["admissibility_eligible"] == 0
    assert "unrecognized_line:1" in (row["failure_reasons"] or "")


def test_mapped_event_idx_increments_per_turn(conn):
    ingest_source_line(conn, SESSION, 1, make_user_message("t1"))
    ingest_source_line(conn, SESSION, 2, make_tool_call("t1", call_id="c1"))
    ingest_source_line(conn, SESSION, 3, make_tool_result("t1", "ok\nProcess exited with code 0",
                                                          call_id="c1"))
    cur = conn.execute(
        "SELECT event_type, event_idx FROM events WHERE session_id=? ORDER BY event_id",
        (SESSION,),
    )
    rows = cur.fetchall()
    assert len(rows) == 3
    # event_idx is monotonic within the turn, starting at 0 (fix C).
    assert [r[1] for r in rows] == [0, 1, 2]


# ─── Step 4: validation_pending rule pair ───────────────────────────────


def test_validation_tool_call_mints_validation_pending(conn):
    ingest_source_line(conn, SESSION, 1, make_tool_call("t1", cmd="pytest -q", call_id="v1"))

    instance = conn.execute(
        """
        SELECT belief_type, claim, created_turn
        FROM belief_instances
        WHERE session_id=? AND belief_type='validation_pending'
        """,
        (SESSION,),
    ).fetchone()
    assert instance is not None
    assert instance[0] == "validation_pending"
    assert "pytest" in instance[1]
    assert instance[2] == 0

    lifecycle = conn.execute(
        """
        SELECT kind, at_turn, effective_turn, authority, note
        FROM belief_events
        WHERE belief_id = (
            SELECT belief_id FROM belief_instances
            WHERE session_id=? AND belief_type='validation_pending'
        )
        """,
        (SESSION,),
    ).fetchone()
    assert lifecycle == (
        "born",
        0,
        0,
        "asserted_by_assistant",
        "validation pending — pytest pytest -q initiated at turn 0",
    )


def test_successful_validation_result_retires_matching_pending(conn):
    ingest_source_line(conn, SESSION, 1, make_tool_call("t1", cmd="pytest -q", call_id="v1"))
    ingest_source_line(
        conn,
        SESSION,
        2,
        make_tool_result("t1", "tests passed\nProcess exited with code 0", call_id="v1"),
    )

    rows = conn.execute(
        """
        SELECT kind, at_turn, effective_turn, authority
        FROM belief_events
        WHERE belief_id = (
            SELECT belief_id FROM belief_instances
            WHERE session_id=? AND belief_type='validation_pending'
        )
        ORDER BY belief_event_id
        """,
        (SESSION,),
    ).fetchall()
    assert rows == [
        ("born", 0, 0, "asserted_by_assistant"),
        ("retired", 0, 0, "confirmed_by_tool"),
    ]

    beliefs, counts = reconstruct_state(conn, SESSION, turn=0)
    assert not any(b["belief_type"] == "validation_pending" for b in beliefs)
    assert counts["retired"] == 1


def test_non_validation_tool_call_does_not_mint_validation_pending(conn):
    ingest_source_line(conn, SESSION, 1, make_tool_call("t1", cmd="ls /tmp", call_id="ls1"))
    count = conn.execute(
        "SELECT COUNT(*) FROM belief_instances WHERE belief_type='validation_pending'"
    ).fetchone()[0]
    assert count == 0


def test_failed_validation_result_does_not_retire_pending(conn):
    ingest_source_line(conn, SESSION, 1, make_tool_call("t1", cmd="pytest -q", call_id="v1"))
    ingest_source_line(
        conn,
        SESSION,
        2,
        make_tool_result("t1", "failed\nProcess exited with code 1", call_id="v1"),
    )

    kinds = conn.execute(
        """
        SELECT kind
        FROM belief_events
        WHERE belief_id = (
            SELECT belief_id FROM belief_instances
            WHERE session_id=? AND belief_type='validation_pending'
        )
        ORDER BY belief_event_id
        """,
        (SESSION,),
    ).fetchall()
    assert kinds == [("born",)]

    beliefs, _ = reconstruct_state(conn, SESSION, turn=0)
    assert any(b["belief_type"] == "validation_pending" for b in beliefs)


def test_validation_rules_record_effective_and_observed_turns(conn):
    ingest_source_line(conn, SESSION, 1, make_tool_call("t1", cmd="pytest -q", call_id="v1"))
    ingest_source_line(conn, SESSION, 2, make_user_message("t2"))
    ingest_source_line(
        conn,
        SESSION,
        3,
        make_tool_result("t2", "passed\nProcess exited with code 0", call_id="v1"),
    )

    rows = conn.execute(
        """
        SELECT kind, effective_turn, at_turn
        FROM belief_events
        WHERE belief_id = (
            SELECT belief_id FROM belief_instances
            WHERE session_id=? AND belief_type='validation_pending'
        )
        ORDER BY belief_event_id
        """,
        (SESSION,),
    ).fetchall()
    assert rows == [("born", 0, 0), ("retired", 1, 1)]


def test_rule_failure_rolls_back_ingest_and_logs_failure(conn, monkeypatch):
    def fail_rule(_conn, _event):
        raise RuntimeError("forced rule failure")

    monkeypatch.setattr(rules_module, "validation_pending_born", fail_rule)

    with pytest.raises(RuleDispatchError):
        ingest_source_line(conn, SESSION, 1, make_tool_call("t1", cmd="pytest -q"))

    assert conn.execute("SELECT COUNT(*) FROM raw_lines").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM belief_instances").fetchone()[0] == 0
    failure = conn.execute(
        "SELECT rule_name, exception_class, exception_message FROM rule_failures"
    ).fetchone()
    assert failure == (
        "validation_pending_born",
        "RuntimeError",
        "forced rule failure",
    )


# ─── Helpers ────────────────────────────────────────────────────────────


def _session_row(conn, session_id):
    cur = conn.execute(
        "SELECT capture_started_at, capture_ended_at, raw_rollout_sha256, "
        "total_line_count, admissibility_eligible, failure_reasons, line_hash_chain "
        "FROM session_status WHERE session_id=?",
        (session_id,),
    )
    r = cur.fetchone()
    if r is None:
        return None
    return {
        "capture_started_at": r[0],
        "capture_ended_at": r[1],
        "raw_rollout_sha256": r[2],
        "total_line_count": r[3],
        "admissibility_eligible": r[4],
        "failure_reasons": r[5],
        "line_hash_chain": r[6],
    }


def _insert_blocker(conn, session_id, btype, at_turn):
    """Insert a persisted blocker belief directly (bypassing the rule engine,
    which is a stub in Step 1)."""
    conn.execute(
        "INSERT INTO belief_instances (belief_id, session_id, belief_type, claim, created_turn) "
        "VALUES (?, ?, ?, ?, ?)",
        (f"b-{btype}-1", session_id, btype, f"{btype} test claim", at_turn),
    )
    conn.execute(
        "INSERT INTO belief_events (belief_id, kind, at_turn, authority, note) "
        "VALUES (?, 'born', ?, 'confirmed_by_tool', 'test')",
        (f"b-{btype}-1", at_turn),
    )
    conn.commit()


def _insert_non_blocker(conn, session_id, btype, at_turn):
    """Same as _insert_blocker but for a belief type that is NOT in the blocker set."""
    conn.execute(
        "INSERT INTO belief_instances (belief_id, session_id, belief_type, claim, created_turn) "
        "VALUES (?, ?, ?, ?, ?)",
        (f"b-{btype}-1", session_id, btype, f"{btype} test claim", at_turn),
    )
    conn.execute(
        "INSERT INTO belief_events (belief_id, kind, at_turn, authority, note) "
        "VALUES (?, 'born', ?, 'confirmed_by_tool', 'test')",
        (f"b-{btype}-1", at_turn),
    )
    conn.commit()
