"""
db.py
SQLite layer for Into the Scrape-Verse.

Design:
- `products` table = current state of each scraped product (one row per product_url/id).
  `status` column drives the Streamlit pipeline view:
  Extracting -> Failed -> Healing -> Verified -> Trusted   (happy path)
                       -> Failed_Verification              (heal ran but data still bad)

- `scrape_runs` table = audit log / history of every extraction + heal attempt.
  This is what you show in the demo video to prove the loop actually happened
  (detect -> trigger heal -> re-verify), not just the final state.

We deliberately do NOT store any self-healing *logic* here -- Bright Data's
Scraper Studio owns that. This layer only stores what WE detect/verify/orchestrate.
"""

import sqlite3
import json
from datetime import datetime, timezone
from contextlib import contextmanager

DB_PATH = "data/scrape_verse.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    source_url          TEXT,        -- collection page URL (NOT unique per product on this site)
    product_slug        TEXT UNIQUE, -- our own stable key, derived from deduped product name
    product_name_raw    TEXT,        -- exactly what Scraper Studio returned
    product_name_clean  TEXT,        -- after our dedup logic
    price_value         REAL,
    price_currency      TEXT,
    price_symbol        TEXT,
    availability_status TEXT,
    status              TEXT DEFAULT 'Extracting',  -- pipeline state, see module docstring
    verification_issues TEXT,        -- JSON list of issues found by the gate
    risk_flags          TEXT,        -- JSON list of regex-based trust/risk signals
    first_seen          TEXT,
    last_updated        TEXT
);

CREATE TABLE IF NOT EXISTS scrape_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id      INTEGER,
    event           TEXT,     -- 'extracted' | 'failure_detected' | 'heal_triggered' | 'heal_result' | 'verified' | 'verification_failed'
    detail          TEXT,     -- JSON blob with event-specific info
    timestamp       TEXT,
    FOREIGN KEY(product_id) REFERENCES products(id)
);
"""


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)


def _now():
    return datetime.now(timezone.utc).isoformat()


def log_event(conn, product_id, event, detail=None):
    conn.execute(
        "INSERT INTO scrape_runs (product_id, event, detail, timestamp) VALUES (?,?,?,?)",
        (product_id, event, json.dumps(detail or {}), _now()),
    )


def _slugify(name: str) -> str:
    """Stable id for a product when the site gives no per-product URL.
    Built from the DEDUPED name so 'X X' and 'X' collapse to the same slug."""
    import re as _re
    from verification_gate import clean_duplicate_name

    clean, _ = clean_duplicate_name(name or "")
    slug = _re.sub(r"[^a-z0-9]+", "-", clean.lower()).strip("-")
    return slug or "unknown-product"


def upsert_product_from_scrape(record: dict):
    """
    record shape (matches Scraper Studio schema fields):
    {
        "source_url": "...",                 # collection page URL -- NOT unique per product on this site
        "product_name": "Aqua Glow Ombre Suit Aqua Glow Ombre Suit",
        "price": {"value": 2499, "currency": "INR", "symbol": "₹"},
        "availability_status": "Sale" | "Sold out" | None   # site only emits this when on sale/sold out
    }
    Since Bright Data doesn't return a per-product URL for this site (every row
    shares the same collection URL), we match/dedupe on a slug derived from the
    (deduped) product name instead of source_url.
    Inserts a new product in 'Extracting' status, or updates an existing one
    and re-opens the pipeline at 'Extracting'. Returns the product id.
    """
    price = record.get("price") or {}
    slug = _slugify(record.get("product_name"))

    with get_conn() as conn:
        cur = conn.execute("SELECT id FROM products WHERE product_slug = ?", (slug,))
        row = cur.fetchone()
        now = _now()

        if row:
            pid = row["id"]
            conn.execute(
                """UPDATE products SET
                     source_url=?, product_name_raw=?, price_value=?, price_currency=?, price_symbol=?,
                     availability_status=?, status='Extracting', last_updated=?
                   WHERE id=?""",
                (
                    record.get("source_url"),
                    record.get("product_name"),
                    price.get("value"),
                    price.get("currency"),
                    price.get("symbol"),
                    record.get("availability_status"),
                    now,
                    pid,
                ),
            )
        else:
            cur = conn.execute(
                """INSERT INTO products
                   (source_url, product_slug, product_name_raw, price_value, price_currency, price_symbol,
                    availability_status, status, first_seen, last_updated)
                   VALUES (?,?,?,?,?,?,?,'Extracting',?,?)""",
                (
                    record.get("source_url"),
                    slug,
                    record.get("product_name"),
                    price.get("value"),
                    price.get("currency"),
                    price.get("symbol"),
                    record.get("availability_status"),
                    now,
                    now,
                ),
            )
            pid = cur.lastrowid

        log_event(conn, pid, "extracted", record)
        return pid


def set_status(product_id, status, issues=None, risk_flags=None):
    with get_conn() as conn:
        conn.execute(
            """UPDATE products SET status=?, verification_issues=?, risk_flags=?, last_updated=?
               WHERE id=?""",
            (
                status,
                json.dumps(issues or []),
                json.dumps(risk_flags or []),
                _now(),
                product_id,
            ),
        )


def set_clean_name(product_id, clean_name):
    with get_conn() as conn:
        conn.execute(
            "UPDATE products SET product_name_clean=? WHERE id=?", (clean_name, product_id)
        )


def all_products():
    with get_conn() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM products ORDER BY id")]


def product_history(product_id):
    with get_conn() as conn:
        return [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM scrape_runs WHERE product_id=? ORDER BY id", (product_id,)
            )
        ]
