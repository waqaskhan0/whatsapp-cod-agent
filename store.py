"""SQLite store for classifier decisions, so the dashboard has something real
to show and the numbers survive a restart."""
import os
import sqlite3
import threading
from datetime import datetime, timezone

DB_PATH = os.getenv("DB_PATH", "cod.db")

# What one prevented dispatch is worth. Two-way courier charge plus packaging;
# ask the seller for their real figure and set it here.
RTO_COST_PKR = float(os.getenv("RTO_COST_PKR", "300"))

_lock = threading.Lock()
_conn = sqlite3.connect(DB_PATH, check_same_thread=False)
_conn.row_factory = sqlite3.Row

def _migrate():
    """Bring an existing database up to the current schema.

    CREATE TABLE IF NOT EXISTS does nothing to a table that already exists, so
    new columns must be added explicitly. Deleting the database is not an option
    once a seller has real order history in it.
    """
    have = {r[1] for r in _conn.execute("PRAGMA table_info(decisions)")}
    if not have:
        return  # fresh database; the CREATE below builds it correctly
    if "message_id" not in have:
        _conn.execute("ALTER TABLE decisions ADD COLUMN message_id TEXT")
        _conn.commit()


_conn.executescript(
    """
    CREATE TABLE IF NOT EXISTS decisions (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        ts             TEXT    NOT NULL,
        message_id     TEXT,
        order_id       TEXT,
        customer_phone TEXT,
        text           TEXT    NOT NULL,
        intent         TEXT    NOT NULL,
        confidence     REAL    NOT NULL,
        action         TEXT    NOT NULL,
        resolved       INTEGER NOT NULL DEFAULT 0
    );
    CREATE INDEX IF NOT EXISTS idx_decisions_ts ON decisions(ts);
    """
)
_conn.commit()
_migrate()
_conn.executescript(
    """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_decisions_msgid
        ON decisions(message_id) WHERE message_id IS NOT NULL;
    """
)
_conn.commit()


def find_by_message_id(message_id):
    """Meta retries webhook delivery until it gets a 2xx, so the same message
    arrives repeatedly. Processing it twice could book a courier twice."""
    if not message_id:
        return None
    rows = _rows("SELECT * FROM decisions WHERE message_id = ?", (message_id,))
    return rows[0] if rows else None


def record(order_id, customer_phone, text, intent, confidence, action,
           message_id=None):
    with _lock:
        cur = _conn.execute(
            "INSERT INTO decisions (ts, message_id, order_id, customer_phone,"
            " text, intent, confidence, action) VALUES (?,?,?,?,?,?,?,?)",
            (datetime.now(timezone.utc).isoformat(timespec="seconds"), message_id,
             order_id, customer_phone, text, intent, float(confidence), action),
        )
        _conn.commit()
        return cur.lastrowid


def resolve(decision_id):
    with _lock:
        _conn.execute("UPDATE decisions SET resolved = 1 WHERE id = ?", (decision_id,))
        _conn.commit()


# Must mirror the n8n switch exactly: these three are the only actions the
# workflow handles without a person. Everything else hits the HUMAN fallback.
AUTOMATED = ("CONFIRM", "CANCEL", "RESCHEDULE")


def _rows(sql, args=()):
    with _lock:
        return [dict(r) for r in _conn.execute(sql, args).fetchall()]


def stats():
    total = _rows("SELECT COUNT(*) AS n FROM decisions")[0]["n"]
    by_intent = _rows(
        "SELECT intent, COUNT(*) AS n FROM decisions GROUP BY intent ORDER BY n DESC"
    )
    escalated = _rows(
        "SELECT COUNT(*) AS n FROM decisions WHERE action NOT IN (?,?,?)", AUTOMATED
    )[0]["n"]
    cancelled = _rows(
        "SELECT COUNT(*) AS n FROM decisions WHERE action = 'CANCEL'"
    )[0]["n"]
    avg_conf = _rows("SELECT AVG(confidence) AS c FROM decisions")[0]["c"] or 0.0

    daily = _rows(
        "SELECT substr(ts, 1, 10) AS day, COUNT(*) AS n,"
        " SUM(CASE WHEN action = 'CANCEL' THEN 1 ELSE 0 END) AS cancels"
        " FROM decisions GROUP BY day ORDER BY day DESC LIMIT 14"
    )

    return {
        "total": total,
        "cancelled": cancelled,
        "escalated": escalated,
        "auto_handled": total - escalated,
        "auto_rate": (total - escalated) / total if total else 0.0,
        "cancel_rate": cancelled / total if total else 0.0,
        "avg_confidence": round(avg_conf, 3),
        "rto_saved_pkr": cancelled * RTO_COST_PKR,
        "rto_cost_pkr": RTO_COST_PKR,
        "by_intent": by_intent,
        "daily": list(reversed(daily)),
    }


def inbox(limit=25):
    """Replies a human still needs to deal with."""
    return _rows(
        "SELECT id, ts, order_id, customer_phone, text, intent, confidence, action"
        " FROM decisions WHERE action NOT IN (?,?,?) AND resolved = 0"
        " ORDER BY id DESC LIMIT ?",
        (*AUTOMATED, limit),
    )


def recent(limit=50):
    return _rows(
        "SELECT id, ts, order_id, text, intent, confidence, action"
        " FROM decisions ORDER BY id DESC LIMIT ?",
        (limit,),
    )
