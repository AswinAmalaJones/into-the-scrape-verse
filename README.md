# Into the Scrape-Verse — Self-Heal Verification Pipeline

**Hackathon:** WeMakeDevs × Bright Data — "Into the Scrape-Verse"
**Target site:** [thejaipurclothing.com/collections/all](https://thejaipurclothing.com/collections/all) (public, no login)

## What this is

Bright Data's Scraper Studio already has native self-healing (AI Code Fixes /
one-click `scraper heal`). We do **not** reinvent that. This project is a thin
orchestration + trust layer on top of it:

1. **Detect** — flag extraction failures (missing/empty required fields).
2. **Trigger** — kick off Bright Data's native self-heal for the failing collector.
3. **Verify** — a "Repair Verification Gate" checks the *repaired* data is
   actually correct: required fields present, price is a valid positive
   number with matching currency/symbol, product name isn't duplicated
   (`"Aqua Glow Ombre Suit Aqua Glow Ombre Suit"` → `"Aqua Glow Ombre Suit"`),
   availability status is a recognized value.
4. **Risk signals (bonus)** — simple regex-based flags (e.g. spammy repeated
   characters in a name, zero-price) surfaced alongside verified data — not a
   trust score, just transparent flags.
5. **Dashboard** — single Streamlit UI showing every product's journey:
   `Extracting → Failed → Healing → Verified → Trusted`

## Architecture

```
Bright Data Scraper Studio  ──scrape──▶  our DB (SQLite)
        ▲                                     │
        │                              detect_failure()
        │ trigger self-heal                   │
        └──────────────────────────── failure found
                     │
              (Bright Data heals)
                     │
                     ▼
              verify_repair()  ──▶  Verified / Trusted / Failed_Verification
                     │
                     ▼
              Streamlit dashboard
```

- `db.py` — SQLite schema (`products`, `scrape_runs` audit log) + helpers
- `verification_gate.py` — failure detection, dedup logic, price validation,
  the verification gate, and the bonus risk signals
- `bright_data_client.py` — orchestration layer that triggers/polls Bright
  Data's native self-heal (see file for current status — being wired against
  the live Self-Healing button/API)
- `seed_data.py` — loads a Scraper Studio export (or built-in sample data)
  through the full pipeline
- `dashboard.py` — Streamlit UI

## Running it

```bash
pip install -r requirements.txt
python seed_data.py           # loads data/scraped_export.json (or sample data) through the pipeline
streamlit run dashboard.py
```

## Bright Data Scraper Studio usage

- Collector built with "Create with AI" against `thejaipurclothing.com/collections/all`.
- Schema: `product_name` (Text), `price` (Price object: value/currency/symbol),
  `availability_status` (Text, **optional** — the site only renders this
  badge for Sale/Sold out items; a normal in-stock product has no badge, so
  its absence is not a failure).
- Baseline verified run: 16 products, 0 failed crawls.

### How self-healing actually works (verified live, not assumed)

We deliberately broke the collector (changed the wait selector to a
nonexistent one) to observe the real flow end-to-end:

1. **Detect** — our `verification_gate.detect_failure()` flags the broken/
   missing field (mirrors the crawler timeout error Scraper Studio itself
   showed us: `waiting for selector "..." failed: timeout 30000ms exceeded`).
2. **Request the heal** — Scraper Studio's self-heal is the **"Refactor
   collector"** panel: you describe the problem in plain English (our
   `bright_data_client.build_heal_request()` generates this text from the
   structured failure reasons) and submit it.
3. **Async generation** — this runs in the background through 3 visible
   stages: *Starting automation… → Planning… → Refactoring code…* (Bright
   Data explicitly says "you can safely leave this page, we'll email you
   when ready" — it is not a synchronous call).
4. **Review the diff** — result is a side-by-side code diff ("View refactor
   changes") that must be explicitly **Accepted** or **Declined**. In our
   test it correctly replaced the broken selector
   (`#product-grid li.wrong__item`) with a working one
   (`.card__heading a, .card__information`).
5. **Draft, not live** — accepting lands the fix in **Draft**. A separate
   **"Save to production"** step (with an optional changelog comment) is
   required before the fix actually takes effect.
6. **Verified in production** — we ran the healed collector manually:
   **16/16 records, 0 failed crawls, 100% success rate.**

**Why `bright_data_client.py` doesn't call a REST API:** we found no
documented public endpoint for triggering/polling this self-heal flow, and
didn't want to fabricate one. Instead, our layer makes the *request text*
and the *state machine* (`HealStage`) explicit and testable, while the
actual trigger/accept/publish is an operator action in the Scraper Studio
UI — an honest "orchestrate, don't reinvent" boundary. If Bright Data
documents an API later, only `trigger_self_heal()` / `poll_heal_status()`
need to change.

## AI tool usage disclosure

This project was built with assistance from **Claude (Anthropic)** for:
- scaffolding the SQLite schema and Streamlit dashboard boilerplate
- structuring the verification gate logic (field checks, dedup, price validation)

All core architectural decisions (what to detect, what "verified" means, why
we don't reimplement self-healing, the pipeline state machine) were made by
[your name] and are understood/explainable — see commit history for
incremental development rather than a single dump commit.

## Known limitations

- `bright_data_client.py` heal-triggering is currently a stub pending
  confirmation of the exact self-heal API/CLI behavior.
- Risk signals are intentionally simple regex checks, not ML — by design,
  for transparency and explainability within hackathon scope.
