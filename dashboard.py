"""
dashboard.py
Single Streamlit UI: shows every product's journey through the pipeline
    Extracting -> Failed -> Healing -> Verified -> Trusted
                         -> Failed_Verification

Run: streamlit run dashboard.py
"""

import json
import streamlit as st
import pandas as pd
from db import init_db, all_products, product_history

STATUS_COLOR = {
    "Extracting": "#9e9e9e",
    "Failed": "#e53935",
    "Healing": "#fb8c00",
    "Verified": "#1e88e5",
    "Trusted": "#43a047",
    "Failed_Verification": "#8e24aa",
}

st.set_page_config(page_title="Into the Scrape-Verse", layout="wide")
init_db()

st.title("🕸️ Into the Scrape-Verse")
st.caption(
    "Bright Data Scraper Studio does the scraping + self-healing. "
    "This layer detects failures, triggers heal, and verifies the repair."
)

products = all_products()

if not products:
    st.warning("No products yet. Run `python seed_data.py` first.")
    st.stop()

df = pd.DataFrame(products)

# ---- KPI row ----
c1, c2, c3, c4, c5 = st.columns(5)
counts = df["status"].value_counts().to_dict()
c1.metric("Total", len(df))
c2.metric("Failed", counts.get("Failed", 0) + counts.get("Failed_Verification", 0))
c3.metric("Healing", counts.get("Healing", 0))
c4.metric("Verified", counts.get("Verified", 0))
c5.metric("Trusted", counts.get("Trusted", 0))

st.divider()

# ---- Pipeline table ----
def status_badge(status):
    color = STATUS_COLOR.get(status, "#666")
    return f'<span style="background:{color};color:white;padding:2px 8px;border-radius:10px;font-size:0.8em">{status}</span>'

st.subheader("Product Pipeline")

for p in products:
    with st.container(border=True):
        cols = st.columns([3, 2, 2, 2, 2])
        name = p["product_name_clean"] or p["product_name_raw"] or "(empty)"
        cols[0].markdown(f"**{name}**  \n<small>{p['source_url'] or ''}</small>", unsafe_allow_html=True)

        price_str = "—"
        if p["price_value"] is not None:
            price_str = f"{p['price_symbol'] or ''}{p['price_value']} {p['price_currency'] or ''}"
        cols[1].markdown(f"💰 {price_str}")

        cols[2].markdown(f"📦 {p['availability_status'] or '—'}")
        cols[3].markdown(status_badge(p["status"]), unsafe_allow_html=True)

        issues = json.loads(p["verification_issues"] or "[]")
        risk = json.loads(p["risk_flags"] or "[]")
        badge_text = []
        if issues:
            badge_text.append(f"⚠️ {len(issues)} issue(s)")
        if risk:
            badge_text.append(f"🚩 {', '.join(risk)}")
        cols[4].markdown(" ".join(badge_text) if badge_text else "✅")

        with st.expander("History / details"):
            if issues:
                st.write("**Verification issues:**", issues)
            hist = product_history(p["id"])
            for h in hist:
                st.text(f"{h['timestamp']}  —  {h['event']}")
                detail = json.loads(h["detail"] or "{}")
                if detail:
                    st.json(detail, expanded=False)

st.divider()
st.caption(
    "Status flow: Extracting → Failed → Healing (Bright Data self-heal) → "
    "Verified/Failed_Verification → Trusted"
)
