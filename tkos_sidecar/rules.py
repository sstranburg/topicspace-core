"""TKOS write-path rule dispatch.

Step 4 implements only RULES_SPEC v0.3.2 §3.2:

- validation_pending_born
- validation_pending_retired_by_success

No other belief derivation rules are implemented here.
"""
from __future__ import annotations

import hashlib
import re
import sqlite3
from dataclasses import dataclass


VALIDATION_TOOLS = {
    "pytest", "npm_test", "cargo_test", "go_test", "jest", "mocha",
    "lint", "typecheck", "mypy", "tsc", "eslint", "rubocop",
    "build", "make", "cargo_build", "go_build",
}

VALIDATION_COMMAND_PATTERNS = [
    re.compile(r"^pytest\b"),
    re.compile(r"^npm (run )?test\b"),
    re.compile(r"^cargo test\b"),
    re.compile(r"^go test\b"),
    re.compile(r"^npx jest\b"),
    re.compile(r"^mypy\b"),
    re.compile(r"^npx tsc\b"),
    re.compile(r"^eslint\b"),
    re.compile(r"^npm (run )?build\b"),
    re.compile(r"^make\b"),
    re.compile(r"^cargo build\b"),
    re.compile(r"^go build\b"),
]


@dataclass(frozen=True)
class RuleEvent:
    event_id: int
    source_event_id: str
    session_id: str
    turn_idx: int
    event_type: str
    tool_name: str | None = None
    command: str | None = None
    exit_code: int | None = None
    parent_event_id: str | None = None


class RuleApplicationError(Exception):
    """Wraps a rule exception with the rule name for durable failure logging."""

    def __init__(self, rule_name: str, original: Exception):
        super().__init__(str(original))
        self.rule_name = rule_name
        self.original = original


def dispatch(conn: sqlite3.Connection, event: RuleEvent) -> list[str]:
    """Run applicable rules inside the caller's open transaction."""
    fired: list[str] = []
    for rule_name, fn in _rules_for(event):
        try:
            if fn(conn, event):
                fired.append(rule_name)
        except Exception as exc:  # pragma: no cover - exercised by integration failures
            raise RuleApplicationError(rule_name, exc) from exc
    return fired


def _rules_for(event: RuleEvent):
    if event.event_type == "tool_call":
        yield "validation_pending_born", validation_pending_born
    elif event.event_type == "tool_result":
        yield "validation_pending_retired_by_success", validation_pending_retired_by_success


def is_validation_call(tool_name: str | None, command: str | None) -> bool:
    if tool_name in VALIDATION_TOOLS:
        return True
    command = command or ""
    return any(pattern.search(command) for pattern in VALIDATION_COMMAND_PATTERNS)


def validation_pending_born(conn: sqlite3.Connection, event: RuleEvent) -> bool:
    if not is_validation_call(event.tool_name, event.command):
        return False

    claim = (
        f"validation pending — {event.tool_name or ''} "
        f"{event.command or ''} initiated at turn {event.turn_idx}"
    )
    belief_id = _belief_id(
        event.session_id,
        "validation_pending",
        event.source_event_id,
    )

    conn.execute(
        """
        INSERT INTO belief_instances
            (belief_id, session_id, belief_type, claim, created_turn, created_by_event_id)
        VALUES (?, ?, 'validation_pending', ?, ?, ?)
        """,
        (belief_id, event.session_id, claim, event.turn_idx, event.event_id),
    )
    conn.execute(
        """
        INSERT INTO belief_events
            (belief_id, event_id, kind, at_turn, effective_turn, authority, note)
        VALUES (?, ?, 'born', ?, ?, 'asserted_by_assistant', ?)
        """,
        (
            belief_id,
            event.event_id,
            event.turn_idx,
            event.turn_idx,
            claim,
        ),
    )
    return True


def validation_pending_retired_by_success(conn: sqlite3.Connection, event: RuleEvent) -> bool:
    if event.exit_code != 0:
        return False

    matches = _active_validation_pending_matches(conn, event)
    fired = False
    for belief_id in matches:
        note = f"validation pending retired — succeeded at turn {event.turn_idx}"
        conn.execute(
            """
            INSERT INTO belief_events
                (belief_id, event_id, kind, at_turn, effective_turn, authority, note)
            VALUES (?, ?, 'retired', ?, ?, 'confirmed_by_tool', ?)
            """,
            (
                belief_id,
                event.event_id,
                event.turn_idx,
                event.turn_idx,
                note,
            ),
        )
        fired = True
    return fired


def _active_validation_pending_matches(
    conn: sqlite3.Connection,
    event: RuleEvent,
) -> list[str]:
    params: list[object] = [event.session_id]
    where = []

    if event.parent_event_id:
        where.append("C.source_event_id = ?")
        params.append(event.parent_event_id)

    if event.tool_name or event.command:
        where.append("(C.tool_name = ? AND C.command = ?)")
        params.extend([event.tool_name, event.command])

    if not where:
        return []

    sql = f"""
        SELECT B.belief_id
        FROM belief_instances B
        JOIN events C ON C.event_id = B.created_by_event_id
        JOIN belief_events E ON E.belief_id = B.belief_id
        WHERE B.session_id = ?
          AND B.belief_type = 'validation_pending'
          AND ({' OR '.join(where)})
          AND E.belief_event_id = (
              SELECT E2.belief_event_id
              FROM belief_events E2
              WHERE E2.belief_id = B.belief_id
              ORDER BY E2.at_turn DESC, E2.belief_event_id DESC
              LIMIT 1
          )
          AND E.kind IN ('born', 'refreshed', 'confirmed', 'weakened')
        ORDER BY B.created_turn ASC, B.belief_id ASC
    """
    return [row[0] for row in conn.execute(sql, params).fetchall()]


def _belief_id(session_id: str, belief_type: str, source_event_id: str) -> str:
    raw = f"{session_id}\n{belief_type}\n{source_event_id}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"belief:{belief_type}:{digest}"
