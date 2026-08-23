"""
verification_gate.py

This is the heart of "namma layer" -- NOT scraping, NOT self-healing.
Two jobs:
  1. detect_failure()  -> did Scraper Studio give us broken/empty data?
  2. verify_repair()   -> after Bright Data's self-heal ran, is the NEW data
                          actually correct? (field presence, format, price valid,
                          name dedup). This is the "Verification Gate".

Also: simple_risk_signals() -> optional bonus, regex-based trust/risk flags.
Not AI, not ML. Deliberately simple/explainable so you can defend it live.
"""

import re

REQUIRED_FIELDS = ["product_name", "price"]
# NOTE: availability_status is intentionally NOT required. On thejaipurclothing.com
# the site only renders a status badge for "Sale" / "Sold out" items -- a regular,
# normally-priced/in-stock product simply has no badge, so the field is absent.
# Treating it as required would falsely flag most normal products as failures.
ALLOWED_AVAILABILITY = {"Sale", "Sold out", "In stock", "Available"}  # extend as needed


# ---------- 1. FAILURE DETECTION (before healing) ----------

def detect_failure(record: dict) -> tuple[bool, list[str]]:
    """
    Look at a freshly scraped record and decide if it counts as a failure
    that should trigger Bright Data's self-heal.
    Returns (is_failure, reasons)
    """
    reasons = []

    for field in REQUIRED_FIELDS:
        val = record.get(field)
        if val is None or val == "" or val == {}:
            reasons.append(f"missing_or_empty:{field}")

    price = record.get("price") or {}
    if isinstance(price, dict):
        if price.get("value") in (None, "", 0):
            reasons.append("price_value_missing_or_zero")
        if not price.get("currency"):
            reasons.append("price_currency_missing")

    name = record.get("product_name")
    if name and _is_exact_duplicate(name):
        # NOTE: this is a data-quality bug (dedupe-able), not necessarily a
        # scrape *failure* worth a full self-heal trigger. We still flag it
        # separately -- see verify_repair / clean_duplicate_name.
        pass

    return (len(reasons) > 0, reasons)


# ---------- 2. NAME DEDUP ----------

def _is_exact_duplicate(name: str) -> bool:
    n = name.strip()
    half = len(n) // 2
    if len(n) % 2 == 0 and n[:half].strip() == n[half:].strip():
        return True
    return False


def clean_duplicate_name(name: str) -> tuple[str, bool]:
    """
    Handles the known bug: "Aqua Glow Ombre Suit Aqua Glow Ombre Suit"
    -> "Aqua Glow Ombre Suit"
    Returns (cleaned_name, was_duplicated)
    Strategy: if the string is literally two identical halves (with a
    single space joiner), collapse it. Falls back to a regex pass for
    repeated word-sequences of length >=2 in case of uneven spacing.
    """
    if not name:
        return name, False

    n = " ".join(name.split())  # normalize whitespace

    if _is_exact_duplicate(n):
        half = len(n) // 2
        return n[:half].strip(), True

    # fallback: token-level duplicate detection, e.g.
    # "Aqua Glow Ombre Suit Aqua Glow Ombre Suit" with odd spacing
    tokens = n.split(" ")
    L = len(tokens)
    if L % 2 == 0:
        first, second = tokens[: L // 2], tokens[L // 2 :]
        if first == second:
            return " ".join(first), True

    return n, False


# ---------- 3. PRICE VALIDATION ----------

_CURRENCY_SYMBOL_MAP = {"INR": "₹", "USD": "$", "EUR": "€", "GBP": "£"}


def validate_price(price: dict) -> tuple[bool, list[str]]:
    issues = []
    if not isinstance(price, dict):
        return False, ["price_not_object"]

    value = price.get("value")
    currency = price.get("currency")
    symbol = price.get("symbol")

    if value is None:
        issues.append("price_value_missing")
    else:
        try:
            v = float(value)
            if v <= 0:
                issues.append("price_value_not_positive")
        except (TypeError, ValueError):
            issues.append("price_value_not_numeric")

    if not currency:
        issues.append("price_currency_missing")

    expected_symbol = _CURRENCY_SYMBOL_MAP.get(currency)
    if expected_symbol and symbol and symbol != expected_symbol:
        issues.append(f"price_symbol_mismatch: expected {expected_symbol} got {symbol}")

    return (len(issues) == 0, issues)


# ---------- 4. FULL VERIFICATION GATE (after healing) ----------

def verify_repair(record: dict) -> dict:
    """
    Run the full gate on a (post-heal) record.
    Returns:
    {
        "passed": bool,
        "issues": [...],
        "clean_product_name": "...",
        "was_deduped": bool
    }
    """
    issues = []

    for field in REQUIRED_FIELDS:
        val = record.get(field)
        if val is None or val == "" or val == {}:
            issues.append(f"missing_or_empty:{field}")

    name = record.get("product_name", "") or ""
    clean_name, was_deduped = clean_duplicate_name(name)
    if not clean_name:
        issues.append("product_name_empty_after_clean")

    price_ok, price_issues = validate_price(record.get("price") or {})
    issues.extend(price_issues)

    # availability_status is optional (see REQUIRED_FIELDS note above).
    # We only flag it if it's PRESENT but not a value we recognize.
    avail = record.get("availability_status")
    if avail and avail not in ALLOWED_AVAILABILITY:
        issues.append(f"availability_status_unrecognized:{avail}")

    return {
        "passed": len(issues) == 0,
        "issues": issues,
        "clean_product_name": clean_name,
        "was_deduped": was_deduped,
    }


# ---------- 5. RISK / TRUST SIGNALS (bonus, regex-based, optional) ----------

_SUSPICIOUS_PRICE_PATTERNS = [
    (re.compile(r"^0+(\.0+)?$"), "zero_price"),
]
_SUSPICIOUS_NAME_PATTERNS = [
    (re.compile(r"(.)\1{4,}"), "repeated_char_spam"),      # aaaaaa
    (re.compile(r"^[^a-zA-Z0-9]+$"), "no_alphanumeric"),   # symbols only
]


def simple_risk_signals(record: dict) -> list[str]:
    flags = []
    name = record.get("product_name", "") or ""
    for pattern, label in _SUSPICIOUS_NAME_PATTERNS:
        if pattern.search(name):
            flags.append(label)

    price = record.get("price") or {}
    val_str = str(price.get("value", ""))
    for pattern, label in _SUSPICIOUS_PRICE_PATTERNS:
        if pattern.match(val_str):
            flags.append(label)

    return flags
