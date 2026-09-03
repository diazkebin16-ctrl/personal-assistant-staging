"""Execute the production Room 1→2 SQL against SQLite, without duplicating its statements."""

import json
import re
import sqlite3
from pathlib import Path

ROOT = Path(__file__).parents[2]
MIGRATION = ROOT / (
    "mobile/androidApp/src/main/java/com/personalassistant/android/data/local/DatabaseMigrations.kt"
)


def migration_statements() -> list[str]:
    source = MIGRATION.read_text(encoding="utf-8")
    marker = "database.execSQL("
    statements: list[str] = []
    cursor = 0
    while (start := source.find(marker, cursor)) >= 0:
        index = start + len(marker)
        depth = 1
        in_string = False
        escaped = False
        while depth:
            char = source[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
            elif char == '"':
                in_string = True
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
            index += 1
        argument = source[start + len(marker) : index - 1]
        pieces = re.findall(r'"(?:[^"\\]|\\.)*"', argument)
        statements.append("".join(json.loads(piece) for piece in pieces))
        cursor = index
    return statements


def migrated_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.execute(
        "CREATE TABLE pending_operations ("
        "operationId TEXT NOT NULL PRIMARY KEY, conversationId TEXT NOT NULL, "
        "idempotencyKey TEXT NOT NULL, encryptedPayload BLOB NOT NULL, "
        "expectedVersion INTEGER NOT NULL, createdAtEpochMillis INTEGER NOT NULL, "
        "attemptCount INTEGER NOT NULL, lastAttemptAtEpochMillis INTEGER, status TEXT NOT NULL)"
    )
    rows = (
        ("pending", "PENDING"),
        ("waiting", "WAITING_CONNECTION"),
        ("syncing", "IN_FLIGHT"),
        ("ack", "SUCCEEDED"),
        ("failure", "FAILED"),
        ("cancelled", "CANCELLED"),
    )
    connection.executemany(
        "INSERT INTO pending_operations VALUES (?, 'conversation', ?, X'01', 1, 100, 0, NULL, ?)",
        [(operation_id, f"android:{operation_id}", status) for operation_id, status in rows],
    )
    for statement in migration_statements():
        connection.execute(statement)
    return connection


def test_production_migration_statements_are_executable() -> None:
    connection = migrated_connection()
    assert connection.execute("PRAGMA user_version").fetchone() is not None


def test_migration_adds_phase11_columns() -> None:
    columns = {
        row[1] for row in migrated_connection().execute("PRAGMA table_info(pending_operations)")
    }
    assert {
        "operationType",
        "payloadFingerprint",
        "payloadVersion",
        "ownerId",
        "deviceId",
        "updatedAtEpochMillis",
        "nextAttemptAtEpochMillis",
        "serverAcknowledgedAtEpochMillis",
        "lastFailureCategory",
        "lastFailureCode",
    } <= columns


def test_unbound_active_legacy_rows_are_rejected() -> None:
    states = dict(
        migrated_connection().execute("SELECT operationId, status FROM pending_operations")
    )
    assert states["pending"] == "REJECTED"
    assert states["waiting"] == "REJECTED"
    assert states["syncing"] == "REJECTED"


def test_terminal_legacy_rows_preserve_truth() -> None:
    states = dict(
        migrated_connection().execute("SELECT operationId, status FROM pending_operations")
    )
    assert states["ack"] == "ACKNOWLEDGED"
    assert states["failure"] == "TERMINAL_FAILURE"
    assert states["cancelled"] == "CANCELLED"


def test_migration_creates_owner_device_state_index() -> None:
    indexes = {
        row[1] for row in migrated_connection().execute("PRAGMA index_list(pending_operations)")
    }
    assert "index_pending_operations_ownerId_deviceId_status" in indexes
