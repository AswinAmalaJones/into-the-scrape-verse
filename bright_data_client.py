"""
bright_data_client.py

Thin orchestration layer around Bright Data Scraper Studio's NATIVE
self-healing (AI Code Fixes / `scraper heal` / refactor_template).

IMPORTANT: We do not implement healing logic ourselves. This module's only
job is to:
  1. Trigger the existing self-heal mechanism when detect_failure() fires.
  2. Fetch the re-scraped/repaired record back.
  3. Hand it to verification_gate.verify_repair().

TODO (blocked on seeing the actual "Self-Healing" button flow):
  - Confirm whether heal is triggered via:
      a) Scraper Studio REST API endpoint (e.g. POST /collectors/{id}/heal), or
      b) `scraper heal` CLI subprocess call, or
      c) manual dashboard button only (no programmatic trigger) -> in that
         case this layer should call the SNAPSHOT/RESULTS API to poll for
         the re-healed data instead of triggering it directly.
  - Confirm response shape of a healed run (same schema as normal run?
    extra metadata like `healed: true`, `fix_applied: "..."`?)
  - Confirm auth: API token location (env var BRIGHT_DATA_API_TOKEN expected below)

Once the screenshot/API docs confirm the flow, fill in trigger_self_heal()
and fetch_latest_snapshot() below. Everything else in the app already
calls these two functions, so the rest of the pipeline won't need to change.
"""

"""
bright_data_client.py

Orchestration layer around Bright Data Scraper Studio's NATIVE self-healing
("Refactor collector"). We do not implement healing logic ourselves --
Bright Data's AI does the actual code fix. This module documents/structures
the flow our layer drives, based on what we verified live in Scraper Studio.

CONFIRMED REAL FLOW (screenshots on file, see demo video):
  1. detect_failure() (verification_gate.py) finds a broken/empty field.
  2. We open the collector's "Refactor collector" panel and submit a plain-
     English request describing the failure (build_heal_request() below).
  3. Bright Data runs this ASYNCHRONOUSLY in 3 visible stages:
       "Starting automation..." -> "Planning..." -> "Refactoring code..."
     (confirmed: "You can safely leave this page, we'll email you when
     ready" -- this is NOT a synchronous call.)
  4. Result is a side-by-side DIFF ("View refactor changes") which must be
     explicitly Accepted or Declined -- self-heal is reviewable, not silently
     auto-applied.
  5. Accepted changes land in DRAFT, not production. A separate explicit
     "Save to production" step (with an optional changelog comment) is
     required before the fix is live.
  6. Only after that does a real "Initiate manually" / production run pick
     up the healed code.

We found no documented public REST endpoint for triggering/polling this
programmatically, and did not want to guess/fabricate one. So instead of a
fake API wrapper, this module's job is to make the REQUEST TEXT and the
STATE MACHINE explicit and testable, while the actual trigger/accept/
publish happens through Scraper Studio's UI (an "operator-in-the-loop"
orchestration -- which is honest about what we're actually automating vs.
what still needs a human click, and is what we explain in the README /
demo video).

If Bright Data exposes a documented API for this later, only
trigger_self_heal() / poll_heal_status() below need to change -- the rest
of the pipeline (detect -> heal -> verify -> dashboard) is unaffected.
"""

from enum import Enum


class HealStage(str, Enum):
    """Mirrors the actual stages shown in the 'Generating your code' modal."""
    STARTING = "Starting automation..."
    PLANNING = "Planning..."
    REFACTORING = "Refactoring code..."
    AWAITING_REVIEW = "Awaiting diff review (Accept/Decline)"
    DRAFT_SAVED = "Changes saved to draft"
    PUBLISHED = "Saved to production"


def build_heal_request(failure_reasons: list[str], field_context: str = "") -> str:
    """
    Turn our structured failure reasons (from verification_gate.detect_failure)
    into the plain-English request Scraper Studio's 'Refactor collector' box
    expects. Keep it short and specific -- this is exactly the pattern that
    worked live: naming the broken selector/field and what should happen.

    Example:
        build_heal_request(["missing_or_empty:product_name"], "product card selector")
        -> "The product card selector is returning missing/empty product_name.
            Fix it so product_name is extracted correctly for every product
            on the collection page."
    """
    reasons_str = ", ".join(failure_reasons)
    context = field_context or "the collector"
    return (
        f"{context} is broken: {reasons_str}. "
        f"Fix it so all required fields are extracted correctly on the collection page."
    )


def trigger_self_heal(request_text: str) -> dict:
    """
    Represents submitting `request_text` into Scraper Studio's
    'Refactor collector' panel and starting the run.

    NOTE: This is currently a *manual, operator-driven* step (we type/paste
    the request built by build_heal_request() into the UI ourselves) --
    there is no confirmed public API to call this programmatically yet.
    This function exists so the rest of the pipeline has a single, stable
    call site to swap in a real API call if/when Bright Data documents one.
    """
    raise NotImplementedError(
        "No confirmed public API for triggering Refactor collector. "
        "In this project, this step is operator-driven via the Scraper "
        "Studio UI using the request text from build_heal_request(). "
        "See README 'How Scraper Studio is used' for the verified flow."
    )


def poll_heal_status(heal_run_id: str = None) -> HealStage:
    """
    PLACEHOLDER for polling stage progress (Starting -> Planning ->
    Refactoring -> Awaiting review -> Draft -> Production), matching the
    stages we confirmed live. Swap in a real call once an API exists.
    """
    raise NotImplementedError(
        "No confirmed public API for polling heal status. See HealStage "
        "for the real stage names observed in the Scraper Studio UI."
    )


def fetch_latest_snapshot() -> list[dict]:
    """
    Fetch the most recent (post-heal, production) run's results.

    For this project: after 'Save to production' + a manual/production run,
    download the run's JSON export from the Runs tab and drop it at
    data/scraped_export.json -- seed_data.py's normalize_bright_data_record()
    already handles Scraper Studio's raw export shape.
    """
    raise NotImplementedError(
        "Use the Runs tab 'Download file options' -> JSON, save to "
        "data/scraped_export.json, then run seed_data.py."
    )

