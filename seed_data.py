"""
seed_data.py

Loads scraped output into the DB and runs it through:
  detect_failure -> (if broken) mark Failed -> [heal happens externally in
  Scraper Studio] -> verify_repair -> Verified/Trusted or Failed_Verification

USAGE:
  1. Export your Scraper Studio run as JSON (16 products from
     thejaipurclothing.com) to data/scraped_export.json, matching SAMPLE
     shape below. If you don't have the export handy yet, this script will
     fall back to the built-in SAMPLE_DATA (with the known duplicate-name
     bug + one deliberately-broken row) so you can build/demo the rest of
     the pipeline right now.

  2. Run: python seed_data.py
"""

import json
import os
from db import init_db, upsert_product_from_scrape, set_status, set_clean_name, log_event, get_conn
from verification_gate import detect_failure, verify_repair, simple_risk_signals

EXPORT_PATH = "data/scraped_export.json"

# Fallback sample reflecting the real schema + the known dedup bug,
# plus one intentionally broken row to demo detect -> heal -> verify live.
SAMPLE_DATA = [
    {
        "source_url": "https://thejaipurclothing.com/products/aqua-glow-ombre-suit",
        "product_name": "Aqua Glow Ombre Suit Aqua Glow Ombre Suit",
        "price": {"value": 2499, "currency": "INR", "symbol": "₹"},
        "availability_status": "Sale",
    },
    {
        "source_url": "https://thejaipurclothing.com/products/royal-blue-kurta",
        "product_name": "Royal Blue Kurta Royal Blue Kurta",
        "price": {"value": 1899, "currency": "INR", "symbol": "₹"},
        "availability_status": "Sale",
    },
    {
        "source_url": "https://thejaipurclothing.com/products/broken-example",
        "product_name": "",  # simulate extraction failure -> should trigger heal
        "price": {"value": None, "currency": "INR", "symbol": "₹"},
        "availability_status": "",
    },
]


def normalize_bright_data_record(raw: dict) -> dict:
    """
    Bright Data's raw export for this collector looks like:
    {
        "product_name": "Aqua Glow Ombre Suit Aqua Glow Ombre Suit",
        "price": {"value": 1999, "currency": "INR", "symbol": "₹"},
        "availability_status": "Sale",   # <-- often ABSENT, that's normal (see verification_gate.py)
        "input": {"url": "https://thejaipurclothing.com/collections/all"}
    }
    Note: "input.url" is the same collection-page URL for every row (the site
    doesn't give per-product URLs in this schema) -- so we keep it just as
    context, and use a name-derived slug (in db.py) as the real unique key.
    """
    return {
        "source_url": (raw.get("input") or {}).get("url"),
        "product_name": raw.get("product_name"),
        "price": raw.get("price") or {},
        "availability_status": raw.get("availability_status"),  # may be None -- fine
    }


def load_export():
    if os.path.exists(EXPORT_PATH):
        with open(EXPORT_PATH, encoding="utf-8") as f:
            raw_records = json.load(f)
        return [normalize_bright_data_record(r) for r in raw_records]
    print(f"[seed_data] {EXPORT_PATH} not found — using built-in SAMPLE_DATA "
          f"({len(SAMPLE_DATA)} rows) so the pipeline is demo-able now.")
    return SAMPLE_DATA


def run_pipeline(records):
    for record in records:
        pid = upsert_product_from_scrape(record)

        is_failure, reasons = detect_failure(record)
        if is_failure:
            with get_conn() as conn:
                log_event(conn, pid, "failure_detected", {"reasons": reasons})
            set_status(pid, "Failed", issues=reasons)
            print(f"[FAILED] id={pid} url={record.get('source_url')} reasons={reasons}")
            # --> in the live demo: bright_data_client.trigger_self_heal() goes here,
            #     then you'd re-fetch the healed record and call verify_repair() on THAT.
            continue

        result = verify_repair(record)
        risk = simple_risk_signals(record)
        set_clean_name(pid, result["clean_product_name"])

        if result["passed"]:
            status = "Trusted" if not risk else "Verified"
            set_status(pid, status, issues=[], risk_flags=risk)
            with get_conn() as conn:
                log_event(conn, pid, "verified", result)
            tag = "deduped" if result["was_deduped"] else "clean"
            print(f"[{status}] id={pid} name='{result['clean_product_name']}' ({tag}) risk={risk}")
        else:
            set_status(pid, "Failed_Verification", issues=result["issues"], risk_flags=risk)
            with get_conn() as conn:
                log_event(conn, pid, "verification_failed", result)
            print(f"[FAILED_VERIFICATION] id={pid} issues={result['issues']}")


if __name__ == "__main__":
    init_db()
    records = load_export()
    run_pipeline(records)
    print("\nDone. Run `streamlit run dashboard.py` to view the pipeline.")
