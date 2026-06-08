"""TKOS write-path rule dispatch.

Implements the validation lifecycle from RULES_SPEC v0.3.2 §3.2-§3.3:

- validation_pending_born
- validation_pending_retired_by_success
- validation_pending_contradicted_by_failure
- validation_complete_born
- pipeline_failed_born
- pipeline_failed_strengthened

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
    output: str | None = None
    stderr_first_line: str | None = None


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

    if event.event_type == "tool_result" and event.exit_code not in (None, 0):
        # pipeline_failed born/strengthened share a trigger and have mutually
        # exclusive preconditions. Decide once against pre-event active state;
        # evaluating born and then strengthened independently would let the
        # strengthened rule observe the belief just minted by born.
        signature = failure_signature(event)
        match = _active_pipeline_failed_match(conn, event.session_id, signature)
        rule_name, fn = (
            ("pipeline_failed_strengthened", pipeline_failed_strengthened)
            if match is not None
            else ("pipeline_failed_born", pipeline_failed_born)
        )
        try:
            if not fn(conn, event, signature=signature, belief_id=match):
                raise RuntimeError(
                    f"mutual-exclusion winner {rule_name} did not fire"
                )
            fired.append(rule_name)
        except Exception as exc:
            raise RuleApplicationError(rule_name, exc) from exc
    return fired


def _rules_for(event: RuleEvent):
    if event.event_type == "tool_call":
        yield "validation_pending_born", validation_pending_born
    elif event.event_type == "tool_result":
        yield "validation_pending_retired_by_success", validation_pending_retired_by_success
        yield "validation_pending_contradicted_by_failure", validation_pending_contradicted_by_failure
        yield "validation_complete_born", validation_complete_born


def is_validation_call(tool_name: str | None, command: str | None) -> bool:
    if tool_name in VALIDATION_TOOLS:
        return True
    command = command or ""
    return any(pattern.search(command) for pattern in VALIDATION_COMMAND_PATTERNS)


def failure_signature(event: RuleEvent) -> str:
    """Derive RULES_SPEC v0.3.2 §3.5.1's intentionally simple signature."""
    if event.exit_code is None:
        raise ValueError("failure_signature requires an exit_code")
    detail = _first_nonempty_line(event.stderr_first_line)
    if detail is None:
        detail = _first_nonempty_line(event.output)
    return f"{event.exit_code}:{detail or ''}"


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


def validation_pending_contradicted_by_failure(
    conn: sqlite3.Connection,
    event: RuleEvent,
) -> bool:
    if event.exit_code is None or event.exit_code == 0:
        return False

    matches = _active_validation_pending_matches(conn, event)
    fired = False
    for belief_id in matches:
        note = f"validation pending contradicted — failed at turn {event.turn_idx}"
        conn.execute(
            """
            INSERT INTO belief_events
                (belief_id, event_id, kind, at_turn, effective_turn, authority, note)
            VALUES (?, ?, 'contradicted', ?, ?, 'confirmed_by_tool', ?)
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


def validation_complete_born(conn: sqlite3.Connection, event: RuleEvent) -> bool:
    if event.exit_code != 0:
        return False

    parent = _matching_validation_parent(conn, event)
    if parent is None:
        return False

    parent_source_event_id, tool_name, command, parent_turn = parent
    claim = (
        f"validation complete — {tool_name or ''} {command or ''} "
        f"from turn {parent_turn}"
    )
    note = (
        f"validation complete — {tool_name or ''} {command or ''} "
        f"passed at turn {event.turn_idx}"
    )
    belief_id = _belief_id(
        event.session_id,
        "validation_complete",
        event.source_event_id,
    )

    conn.execute(
        """
        INSERT INTO belief_instances
            (belief_id, session_id, belief_type, claim, created_turn, created_by_event_id)
        VALUES (?, ?, 'validation_complete', ?, ?, ?)
        """,
        (belief_id, event.session_id, claim, event.turn_idx, event.event_id),
    )
    conn.execute(
        """
        INSERT INTO belief_events
            (belief_id, event_id, kind, at_turn, effective_turn, authority, note)
        VALUES (?, ?, 'born', ?, ?, 'confirmed_by_tool', ?)
        """,
        (
            belief_id,
            event.event_id,
            event.turn_idx,
            event.turn_idx,
            note,
        ),
    )
    return True


def pipeline_failed_born(
    conn: sqlite3.Connection,
    event: RuleEvent,
    *,
    signature: str | None = None,
    belief_id: str | None = None,
) -> bool:
    if event.exit_code is None or event.exit_code == 0:
        return False
    signature = signature or failure_signature(event)
    if belief_id is not None or _active_pipeline_failed_match(
        conn, event.session_id, signature
    ) is not None:
        return False

    note = (
        f"pipeline_failed — {event.tool_name or ''} exit {event.exit_code} "
        f"signature '{signature}' at turn {event.turn_idx}"
    )
    belief_id = _belief_id(event.session_id, "pipeline_failed", event.source_event_id)
    conn.execute(
        """
        INSERT INTO belief_instances
            (belief_id, session_id, belief_type, claim, created_turn, created_by_event_id)
        VALUES (?, ?, 'pipeline_failed', ?, ?, ?)
        """,
        (belief_id, event.session_id, note, event.turn_idx, event.event_id),
    )
    conn.execute(
        """
        INSERT INTO belief_events
            (belief_id, event_id, kind, at_turn, effective_turn, authority, note)
        VALUES (?, ?, 'born', ?, ?, 'confirmed_by_tool', ?)
        """,
        (belief_id, event.event_id, event.turn_idx, event.turn_idx, note),
    )
    return True


def pipeline_failed_strengthened(
    conn: sqlite3.Connection,
    event: RuleEvent,
    *,
    signature: str | None = None,
    belief_id: str | None = None,
) -> bool:
    if event.exit_code is None or event.exit_code == 0:
        return False
    signature = signature or failure_signature(event)
    belief_id = belief_id or _active_pipeline_failed_match(
        conn, event.session_id, signature
    )
    if belief_id is None:
        return False

    note = f"pipeline_failed refreshed — same signature recurred at turn {event.turn_idx}"
    conn.execute(
        """
        INSERT INTO belief_events
            (belief_id, event_id, kind, at_turn, effective_turn, authority, note)
        VALUES (?, ?, 'refreshed', ?, ?, 'confirmed_by_tool', ?)
        """,
        (belief_id, event.event_id, event.turn_idx, event.turn_idx, note),
    )
    return True


def _matching_validation_parent(
    conn: sqlite3.Connection,
    event: RuleEvent,
) -> tuple[str, str | None, str | None, int] | None:
    if event.parent_event_id:
        parent = conn.execute(
            """
            SELECT source_event_id, tool_name, command, turn
            FROM events
            WHERE session_id=? AND event_type='tool_call' AND source_event_id=?
            """,
            (event.session_id, event.parent_event_id),
        ).fetchone()
        if parent is not None and is_validation_call(parent[1], parent[2]):
            return parent
        return None

    if not event.tool_name and not event.command:
        return None

    parent = conn.execute(
        """
        SELECT source_event_id, tool_name, command, turn
        FROM events
        WHERE session_id=? AND event_type='tool_call'
          AND tool_name=? AND command=?
        ORDER BY event_id DESC
        LIMIT 1
        """,
        (event.session_id, event.tool_name, event.command),
    ).fetchone()
    if parent is not None and is_validation_call(parent[1], parent[2]):
        return parent
    return None


def _active_validation_pending_matches(
    conn: sqlite3.Connection,
    event: RuleEvent,
) -> list[str]:
    params: list[object] = [event.session_id]
    where = []

    if event.parent_event_id:
        where.append("C.source_event_id = ?")
        params.append(event.parent_event_id)
    elif event.tool_name or event.command:
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


def _active_pipeline_failed_match(
    conn: sqlite3.Connection,
    session_id: str,
    signature: str,
) -> str | None:
    claim_fragment = f"signature '{signature}'"
    row = conn.execute(
        """
        SELECT B.belief_id
        FROM belief_instances B
        JOIN belief_events E ON E.belief_id = B.belief_id
        WHERE B.session_id = ?
          AND B.belief_type = 'pipeline_failed'
          AND instr(B.claim, ?) > 0
          AND E.belief_event_id = (
              SELECT E2.belief_event_id
              FROM belief_events E2
              WHERE E2.belief_id = B.belief_id
              ORDER BY E2.at_turn DESC, E2.belief_event_id DESC
              LIMIT 1
          )
          AND E.kind IN ('born', 'refreshed', 'confirmed', 'weakened')
        ORDER BY B.created_turn ASC, B.belief_id ASC
        LIMIT 1
        """,
        (session_id, claim_fragment),
    ).fetchone()
    return row[0] if row is not None else None


def _first_nonempty_line(value: str | None) -> str | None:
    for line in (value or "").splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return None


def _belief_id(session_id: str, belief_type: str, source_event_id: str) -> str:
    raw = f"{session_id}\n{belief_type}\n{source_event_id}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"belief:{belief_type}:{digest}"
