"""
demo_heal_request.py

Shows the exact link between our detection layer and Bright Data's
self-heal: given a failed extraction (like the one we produced live by
breaking the selector), this prints the plain-English request our layer
would hand to Scraper Studio's "Refactor collector" panel.

Run: python demo_heal_request.py
Useful for the demo video / for explaining the code live.
"""

from verification_gate import detect_failure
from bright_data_client import build_heal_request

# Mirrors the real broken run: selector timeout -> empty required fields
broken_record = {
    "product_name": "",
    "price": {"value": None, "currency": "INR", "symbol": "₹"},
    "availability_status": None,
}

is_failure, reasons = detect_failure(broken_record)
print(f"Failure detected: {is_failure}")
print(f"Reasons: {reasons}")

if is_failure:
    request_text = build_heal_request(reasons, field_context="Product card selector")
    print("\nRequest we'd submit to Scraper Studio's 'Refactor collector' panel:")
    print(f"  \"{request_text}\"")
