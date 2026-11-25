import datetime
import json
import re
import time
from urllib.parse import urlparse

import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup
from ddgs import DDGS
from google import genai
from google.genai import types

st.set_page_config(
    page_title="Brand Intelligence & AEO Report",
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- NOVASTACKS DARK EXECUTIVE THEME CSS ---
st.markdown(
    """
<style>
.stApp {
    background-color: #0b0f14;
    background-image:
        linear-gradient(to right, rgba(255, 255, 255, 0.025) 1px, transparent 1px),
        linear-gradient(to bottom, rgba(255, 255, 255, 0.025) 1px, transparent 1px);
    background-size: 36px 36px;
    color: #e6edf3;
}
section[data-testid="stSidebar"] {
    background-color: #090c10;
    border-right: 1px solid #1e2631;
}
.section-kicker {
    font-family: monospace;
    font-size: 0.78rem;
    letter-spacing: 0.14em;
    color: #22d3ee;
    text-transform: uppercase;
    margin-bottom: 0.25rem;
}
.hero-brand {
    font-size: 3.1rem;
    font-weight: 800;
    color: #22d3ee;
    line-height: 1.1;
    margin: 0;
    text-align: center;
}
.hero-sub {
    font-size: 2.9rem;
    font-weight: 800;
    color: #f8fafc;
    line-height: 1.15;
    margin: 0 0 0.75rem 0;
    text-align: center;
}
.hero-meta {
    font-family: monospace;
    color: #94a3b8;
    font-size: 0.9rem;
    text-align: center;
    margin-bottom: 1.8rem;
}
.kpi-box {
    text-align: center;
    padding: 0.5rem 1rem;
}
.kpi-val {
    font-size: 2.1rem;
    font-weight: 800;
    color: #f8fafc;
}
.kpi-val-red {
    font-size: 2.1rem;
    font-weight: 800;
    color: #f87171;
}
.kpi-lbl {
    font-family: monospace;
    font-size: 0.78rem;
    color: #64748b;
    margin-top: 0.15rem;
}
.pill-row {
    display: flex;
    flex-wrap: wrap;
    justify-content: center;
    gap: 8px;
    margin-top: 1.2rem;
}
.plat-pill {
    font-family: monospace;
    font-size: 0.76rem;
    padding: 4px 12px;
    border-radius: 6px;
    border: 1px solid rgba(255,255,255,0.12);
}
.subscore-card {
    background: #11161f;
    border: 1px solid #1e293b;
    border-radius: 10px;
    padding: 14px 18px;
    margin-bottom: 12px;
    display: flex;
    justify-content: space-between;
    align-items: center;
}
.sent-card-pos {
    background: rgba(16, 185, 129, 0.08);
    border: 1px solid rgba(16, 185, 129, 0.25);
    border-radius: 10px;
    padding: 20px;
    text-align: center;
}
.sent-card-neg {
    background: rgba(239, 68, 68, 0.08);
    border: 1px solid rgba(239, 68, 68, 0.25);
    border-radius: 10px;
    padding: 20px;
    text-align: center;
}
.sent-card-neu {
    background: rgba(148, 163, 184, 0.08);
    border: 1px solid rgba(148, 163, 184, 0.25);
    border-radius: 10px;
    padding: 20px;
    text-align: center;
}
.thread-card {
    background: #11161f;
    border: 1px solid #1e293b;
    border-radius: 10px;
    padding: 16px;
    margin-bottom: 10px;
}
.badge {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 6px;
    font-family: monospace;
    font-size: 0.78rem;
    font-weight: 600;
}
.report-divider {
    border: 0;
    border-top: 1px solid #1e293b;
    margin: 2.5rem 0;
}
</style>
""",
    unsafe_allow_html=True,
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    )
}

MODEL_CANDIDATES = [
    "gemini-4-hydrogen",
    "gemini-3.8-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash-lite",
]

CHANNELS = [
    ("Reddit", "site:reddit.com", "#f97316"),
    ("Quora", "site:quora.com", "#eab308"),
    ("G2", "site:g2.com", "#ef4444"),
    ("Web", "", "#38bdf8"),
    ("News", "", "#10b981"),
    ("X", "site:x.com OR site:twitter.com", "#64748b"),
    ("YouTube", "site:youtube.com", "#f43f5e"),
    ("Facebook", "site:facebook.com", "#3b82f6"),
    ("Instagram", "site:instagram.com", "#a855f7"),
]


def normalize_url(raw_url: str) -> str:
    raw_url = raw_url.strip()
    if not raw_url.startswith(("http://", "https://")):
        raw_url = "https://" + raw_url
    return raw_url


def safe_json_loads(raw_text: str) -> dict:
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return json.loads(cleaned)


def render_donut_svg(score: int, subtitle: str = "Brand Health Score", size: int = 190) -> str:
    radius = 74
    circumference = 2 * 3.14159265 * radius
    pct = max(0, min(100, score)) / 100.0
    offset = circumference * (1 - pct)
    ring_color = "#22d3ee" if score >= 55 else "#f59e0b" if score >= 35 else "#ef4444"
    return (
        f'<div style="display:flex;justify-content:center;align-items:center;margin:1rem 0;">'
        f'<svg width="{size}" height="{size}" viewBox="0 0 180 180">'
        f'<circle cx="90" cy="90" r="{radius}" fill="none" stroke="#1e293b" stroke-width="13" />'
        f'<circle cx="90" cy="90" r="{radius}" fill="none" stroke="{ring_color}" stroke-width="13" '
        f'stroke-dasharray="{circumference:.1f}" stroke-dashoffset="{offset:.1f}" '
        f'stroke-linecap="round" transform="rotate(-90 90 90)" />'
        f'<text x="90" y="88" text-anchor="middle" fill="#f8fafc" font-size="34" font-weight="800" font-family="sans-serif">{score}</text>'
        f'<text x="90" y="110" text-anchor="middle" fill="#94a3b8" font-size="11" font-family="monospace">{subtitle}</text>'
        f'</svg></div>'
    )


def generate_with_resilience(
    client: genai.Client,
    primary_model: str,
    contents: str,
    config: types.GenerateContentConfig,
):
    ordered_models = [primary_model] + [m for m in MODEL_CANDIDATES if m != primary_model]
    last_err = None
    for model_id in ordered_models:
        for attempt in range(2):
            try:
                return client.models.generate_content(
                    model=model_id,
                    contents=contents,
                    config=config,
                )
            except Exception as err:
                last_err = err
                err_str = str(err).upper()
                if any(k in err_str for k in ["404", "NOT_FOUND", "429", "RESOURCE_EXHAUSTED"]):
                    break
                if "503" in err_str or "UNAVAILABLE" in err_str:
                    time.sleep(2 * (attempt + 1))
                    continue
                raise err
    raise RuntimeError(f"All fallback models hit rate/availability limits. Last error: {last_err}")


def crawl_homepage(url: str) -> dict:
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")

    title = soup.title.string.strip() if soup.title and soup.title.string else ""
    meta_tag = soup.find("meta", attrs={"name": re.compile("^description$", re.I)})
    meta_desc = meta_tag.get("content", "").strip() if meta_tag else ""
    h1s = [h.get_text(" ", strip=True) for h in soup.find_all("h1")]
    h2s = [h.get_text(" ", strip=True) for h in soup.find_all("h2")]

    schemas = []
    for s in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(s.string or "{}")
            items = data if isinstance(data, list) else [data]
            for it in items:
                if isinstance(it, dict) and "@type" in it:
                    t = it["@type"]
                    schemas.extend(t if isinstance(t, list) else [t])
        except Exception:
            pass

    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))

    return {
        "final_url": resp.url,
        "domain": urlparse(resp.url).netloc.replace("www.", ""),
        "title": title,
        "meta_description": meta_desc,
        "h1s": h1s[:5],
        "h2s": h2s[:10],
        "schemas": sorted(set(schemas)),
        "excerpt": text[:3500],
    }


def collect_live_mentions(brand: str, domain: str, category: str, market: str) -> dict:
    region_map = {
        "India": "in-en",
        "United States": "us-en",
        "United Kingdom": "uk-en",
        "Singapore": "sg-en",
        "Australia": "au-en",
        "Global": "wt-wt",
    }
    region = region_map.get(market, "wt-wt")
    evidence = {ch[0]: [] for ch in CHANNELS}

    with DDGS() as ddgs:
        try:
            evidence["Web"] = list(ddgs.text(f'"{brand}" OR "{domain}"', region=region, max_results=12))
        except Exception:
            pass

        try:
            evidence["News"] = list(ddgs.news(f'"{brand}"', region=region, max_results=8))
        except Exception:
            pass

        for name, site_filter, _ in CHANNELS:
            if name in ("Web", "News"):
                continue
            try:
                evidence[name] = list(ddgs.text(f'"{brand}" {site_filter}', region=region, max_results=6))
            except Exception:
                evidence[name] = []

    return evidence


def run_brand_intelligence_pipeline(
    client: genai.Client,
    model_name: str,
    crawl_data: dict,
    market: str,
    competitors_override: list[str],
) -> dict:
    entity_prompt = f"""
Identify the brand entity, industry category, and 3 direct competitors in {market} from this homepage:
Domain: {crawl_data['domain']}
Title: {crawl_data['title']}
Meta: {crawl_data['meta_description']}
H1s: {crawl_data['h1s']}
User competitor overrides (use if provided): {competitors_override}
Excerpt: {crawl_data['excerpt'][:2000]}

Return strict JSON:
{{
  "brand_name": "official brand name",
  "category": "concise category",
  "is_b2b_software": true or false,
  "competitors": ["Competitor 1", "Competitor 2", "Competitor 3"]
}}
"""
    ent_resp = generate_with_resilience(
        client=client,
        primary_model=model_name,
        contents=entity_prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.1),
    )
    entity = safe_json_loads(ent_resp.text)
    brand = entity["brand_name"]

    raw_evidence = collect_live_mentions(brand, crawl_data["domain"], entity["category"], market)

    compact_evidence = {}
    for ch, items in raw_evidence.items():
        compact_evidence[ch] = [
            {
                "title": it.get("title", ""),
                "snippet": (it.get("body") or it.get("snippet") or "")[:220],
                "url": it.get("href") or it.get("url") or "",
            }
            for it in items[:6]
        ]

    synthesis_prompt = f"""
You are a senior Brand Intelligence & Answer Engine Optimization (AEO) analyst generating an executive report in the style of Novastacks AI.
Brand: {brand} ({crawl_data['domain']})
Category: {entity['category']} | Target Market: {market}
Competitors: {entity['competitors']}
Detected On-Site Schemas: {crawl_data['schemas']}

Live Harvested Web, News & Social Mentions across 9 channels:
{json.dumps(compact_evidence, indent=2)}

Generate a rigorous, realistic Brand Intelligence & AI Visibility Report grounded in the harvested snippets above.
Note: Scale estimated channel mention counts realistically based on the live search density found (e.g., if 6/6 Reddit hits returned rich threads, estimate realistic indexed thread volume; if G2 is irrelevant for a consumer/local brand, mark G2 mentions 0 and note "Not applicable").

Return strict JSON with these exact keys:
{{
  "executive_summary": "3-4 sentence executive takeaway on brand perception, AI citation readiness, and category narrative.",
  "brand_health_score": integer (0-100),
  "subscores": {{
    "sentiment": {{"score": integer, "weight": "30%", "detail": "e.g. 58% positive across analyzed mentions"}},
    "volume": {{"score": integer, "weight": "20%", "detail": "e.g. 185 total indexed mentions"}},
    "reach": {{"score": integer, "weight": "20%", "detail": "e.g. Avg domain authority 410/1000"}},
    "coverage": {{"score": integer, "weight": "15%", "detail": "e.g. 7 of 9 platforms active"}},
    "freshness": {{"score": integer, "weight": "15%", "detail": "e.g. Active discussions in last 90 days"}}
  }},
  "channels": [
    {{
      "platform": "Reddit",
      "mentions": integer,
      "conversation_type": "Debate / Mixed | Question driven | Not applicable | Polarized | Mostly positive | Brand / Trade | Brand owned | Industry / Partner",
      "note": "concise note"
    }}
  ],
  "sentiment": {{
    "headline": "2-4 word punchy headline e.g. A Polarized Conversation or Strong Niche Advocacy",
    "intro": "2 sentence explanation of the sentiment split.",
    "positive_pct": integer,
    "negative_pct": integer,
    "neutral_pct": integer,
    "narrative": "2-3 sentence analytical callout explaining what drives positive vs negative perception.",
    "quora_threads": [
      {{"title": "real or realistic Quora question from evidence", "tag": "tag/topic", "url": "url if found"}}
    ],
    "reddit_threads": [
      {{"title": "real or realistic Reddit thread from evidence", "tag": "r/subreddit", "url": "url if found"}}
    ]
  }},
  "news_media": [
    {{"outlet": "Publication/Site", "headline": "Article or mention title", "tone": "Positive | Neutral | Critical", "url": "url"}}
  ],
  "competitor_landscape": [
    {{
      "brand": "Brand Name",
      "ai_visibility": "High | Medium | Low",
      "sentiment_balance": "e.g. 64% Pos / 18% Neg",
      "primary_moat": "what gives them AI/search authority"
    }}
  ],
  "top_pain_points": [
    {{"pain_point": "Specific friction/objection buyers raise online", "frequency": "High | Medium", "aeo_impact": "How this hurts LLM recommendations"}}
  ],
  "response_playbook": [
    {{"channel": "Reddit / Quora / Review Sites", "trigger": "What thread type to target", "recommended_response": "Exact positioning angle"}}
  ],
  "content_strategy": [
    {{"pillar": "Content / Schema Asset to Build", "target_queries": "Buyer prompts this captures", "execution_step": "Concrete action"}}
  ]
}}
"""
    synth_resp = generate_with_resilience(
        client=client,
        primary_model=model_name,
        contents=synthesis_prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.25),
    )
    report = safe_json_loads(synth_resp.text)
    report["entity"] = entity
    report["raw_evidence"] = compact_evidence
    return report


# --- SIDEBAR NAVIGATION & INPUTS ---
with st.sidebar:
    st.markdown("### 🧬 BRAND INTELLIGENCE")
    st.caption(f"Report Date: {datetime.date.today().strftime('%B %d, %Y')}")
    st.divider()

    api_key = st.secrets.get("GEMINI_API_KEY", "") if hasattr(st, "secrets") else ""
    if not api_key:
        api_key = st.text_input("Gemini API Key", type="password", help="Or set GEMINI_API_KEY in Streamlit Secrets")

    target_url = st.text_input("Target Website URL", placeholder="[https://courthaus.club](https://courthaus.club)")
    market = st.selectbox(
        "Target Market",
        ["India", "United States", "United Kingdom", "Singapore", "Australia", "Global"],
        index=0,
    )
    comp_input = st.text_input("Competitors (optional)", placeholder="Hudle, Playo, District")
    model_name = st.selectbox("Model", MODEL_CANDIDATES, index=0)
    run_btn = st.button("Generate Report", type="primary", use_container_width=True)

    st.divider()
    st.markdown(
        '<div style="font-family:monospace;font-size:0.8rem;line-height:2.0;color:#94a3b8;">'
        '<div style="color:#22d3ee;font-weight:700;">REPORT SECTIONS</div>'
        '<a href="#cover" style="color:#cbd5e1;text-decoration:none;">Cover</a><br>'
        '<a href="#01-executive-summary" style="color:#cbd5e1;text-decoration:none;">01 Executive Summary</a><br>'
        '<a href="#02-brand-health-score" style="color:#cbd5e1;text-decoration:none;">02 Brand Health Score</a><br>'
        '<a href="#03-channel-overview" style="color:#cbd5e1;text-decoration:none;">03 Channel Overview</a><br>'
        '<a href="#04-sentiment-analysis" style="color:#cbd5e1;text-decoration:none;">04 Sentiment Analysis</a><br>'
        '<a href="#05-news-media-coverage" style="color:#cbd5e1;text-decoration:none;">05 News &amp; Media Coverage</a><br>'
        '<a href="#06-competitor-landscape" style="color:#cbd5e1;text-decoration:none;">06 Competitor Landscape</a><br>'
        '<a href="#07-top-pain-points" style="color:#cbd5e1;text-decoration:none;">07 Top Pain Points</a><br>'
        '<div style="color:#475569;font-size:0.7rem;margin-top:8px;">PLAYBOOK &amp; STRATEGY</div>'
        '<a href="#08-full-thread-analysis" style="color:#cbd5e1;text-decoration:none;">08 Full Thread Analysis</a><br>'
        '<a href="#09-response-playbook" style="color:#cbd5e1;text-decoration:none;">09 Response Playbook</a><br>'
        '<a href="#10-content-strategy" style="color:#cbd5e1;text-decoration:none;">10 Content Strategy</a>'
        '</div>',
        unsafe_allow_html=True,
    )

# --- EXECUTION ---
if run_btn:
    if not api_key:
        st.error("Add your Gemini API Key in the sidebar or Streamlit Secrets.")
        st.stop()
    if not target_url.strip():
        st.warning("Enter a website URL first.")
        st.stop()

    clean_url = normalize_url(target_url)
    comps = [c.strip() for c in comp_input.split(",") if c.strip()][:3]

    with st.status("Building Brand Intelligence & AEO Report...", expanded=True) as status:
        st.write("1/3 Crawling homepage metadata, headings, and JSON-LD entities...")
        crawl_data = crawl_homepage(clean_url)

        st.write("2/3 Harvesting live Reddit, Quora, News, Web & Social mentions...")
        client = genai.Client(api_key=api_key)
        report = run_brand_intelligence_pipeline(client, model_name, crawl_data, market, comps)

        st.write("3/3 Scoring brand health, sentiment polarity & competitor landscape...")
        status.update(label="Report Ready", state="complete", expanded=False)

    st.session_state["bi_report"] = report
    st.session_state["bi_crawl"] = crawl_data

# --- RENDER REPORT ---
if "bi_report" not in st.session_state:
    st.info("👈 Paste any website URL in the left sidebar and click **Generate Report** to build an executive Brand Intelligence & AEO report.")
    st.stop()

report = st.session_state["bi_report"]
crawl = st.session_state["bi_crawl"]
entity = report["entity"]
channels = report.get("channels", [])
total_mentions = sum(c.get("mentions", 0) for c in channels)
active_platforms = sum(1 for c in channels if c.get("mentions", 0) > 0)
sent = report.get("sentiment", {})
neg_share = sent.get("negative_pct", 0)
health_score = report.get("brand_health_score", 60)

# === COVER ===
st.markdown('<div id="cover"></div>', unsafe_allow_html=True)
st.markdown(f'<h1 class="hero-brand">{entity["brand_name"]}</h1>', unsafe_allow_html=True)
st.markdown('<h2 class="hero-sub">Brand Intelligence Report</h2>', unsafe_allow_html=True)
st.markdown(
    f'<div class="hero-meta">Quora, Reddit and {max(0, active_platforms - 2)} more channels for {crawl["domain"]}<br>'
    f'{datetime.date.today().strftime("%B %d, %Y")} &nbsp;|&nbsp; {market} Market &nbsp;|&nbsp; Automated AEO Audit</div>',
    unsafe_allow_html=True,
)

st.markdown(render_donut_svg(health_score, "Brand Health Score", 200), unsafe_allow_html=True)

k1, k2, k3 = st.columns([1, 1, 1])
with k1:
    st.markdown(f'<div class="kpi-box"><div class="kpi-val">{total_mentions}</div><div class="kpi-lbl">Mentions</div></div>', unsafe_allow_html=True)
with k2:
    st.markdown(f'<div class="kpi-box"><div class="kpi-val">{active_platforms} / {len(channels)}</div><div class="kpi-lbl">Platforms</div></div>', unsafe_allow_html=True)
with k3:
    st.markdown(f'<div class="kpi-box"><div class="kpi-val-red">{neg_share}%</div><div class="kpi-lbl">Negative Share</div></div>', unsafe_allow_html=True)

pill_colors = {
    "Reddit": ("rgba(249,115,22,0.15)", "#fb923c"),
    "Quora": ("rgba(234,179,8,0.15)", "#facc15"),
    "G2": ("rgba(239,68,68,0.15)", "#f87171"),
    "Web": ("rgba(56,189,248,0.15)", "#38bdf8"),
    "News": ("rgba(16,185,129,0.15)", "#34d399"),
    "X": ("rgba(148,163,184,0.15)", "#94a3b8"),
    "YouTube": ("rgba(244,63,94,0.15)", "#fb7185"),
    "Facebook": ("rgba(59,130,246,0.15)", "#60a5fa"),
    "Instagram": ("rgba(168,85,247,0.15)", "#c084fc"),
}
pills_html = '<div class="pill-row">'
for c in channels:
    p = c["platform"]
    bg, fg = pill_colors.get(p, ("rgba(148,163,184,0.15)", "#cbd5e1"))
    pills_html += f'<span class="plat-pill" style="background:{bg};color:{fg};">{p}</span>'
pills_html += "</div>"
st.markdown(pills_html, unsafe_allow_html=True)

st.markdown('<hr class="report-divider">', unsafe_allow_html=True)

# === 01 EXECUTIVE SUMMARY ===
st.markdown('<div id="01-executive-summary"></div>', unsafe_allow_html=True)
st.markdown('<div class="section-kicker">// 01 EXECUTIVE SUMMARY</div>', unsafe_allow_html=True)
st.markdown("### Strategic Intelligence Overview")
st.info(report.get("executive_summary", ""))

st.markdown('<hr class="report-divider">', unsafe_allow_html=True)

# === 02 BRAND HEALTH SCORE ===
st.markdown('<div id="02-brand-health-score"></div>', unsafe_allow_html=True)
st.markdown('<div class="section-kicker">// 02 BRAND HEALTH SCORE</div>', unsafe_allow_html=True)
st.markdown(f"## Your Brand Health: {health_score}/100")

col_ring, col_cards = st.columns([1, 1.6])
with col_ring:
    st.markdown("<br><br>", unsafe_allow_html=True)
    st.markdown(render_donut_svg(health_score, "out of 100", 230), unsafe_allow_html=True)

with col_cards:
    sub = report.get("subscores", {})
    score_rows = [
        ("Sentiment Score", sub.get("sentiment", {})),
        ("Volume Score", sub.get("volume", {})),
        ("Reach Score", sub.get("reach", {})),
        ("Coverage Score", sub.get("coverage", {})),
        ("Freshness Score", sub.get("freshness", {})),
    ]
    for label, obj in score_rows:
        sc = obj.get("score", 50)
        sc_color = "#34d399" if sc >= 70 else "#facc15" if sc >= 45 else "#f87171"
        st.markdown(
            f'<div class="subscore-card">'
            f'<div><div style="color:#94a3b8;font-size:0.85rem;">{label}</div>'
            f'<div style="font-size:1.35rem;font-weight:800;color:{sc_color};">{sc} <span style="font-size:0.85rem;color:#64748b;">/ 100</span></div></div>'
            f'<div style="text-align:right;"><div style="font-family:monospace;font-size:0.8rem;color:#eab308;">{obj.get("weight", "")} weight</div>'
            f'<div style="font-size:0.8rem;color:#64748b;">{obj.get("detail", "")}</div></div>'
            f'</div>',
            unsafe_allow_html=True,
        )

st.markdown('<hr class="report-divider">', unsafe_allow_html=True)

# === 03 CHANNEL OVERVIEW ===
st.markdown('<div id="03-channel-overview"></div>', unsafe_allow_html=True)
st.markdown('<div class="section-kicker">// 03 CHANNEL OVERVIEW</div>', unsafe_allow_html=True)
st.markdown("## Where Your Brand Lives Online")

badge_styles = {
    "Debate / Mixed": ("rgba(234,179,8,0.16)", "#facc15"),
    "Polarized": ("rgba(249,115,22,0.16)", "#fb923c"),
    "Question driven": ("rgba(148,163,184,0.16)", "#cbd5e1"),
    "Not applicable": ("rgba(100,116,139,0.16)", "#94a3b8"),
    "Mostly positive": ("rgba(16,185,129,0.16)", "#34d399"),
    "Brand / Trade": ("rgba(148,163,184,0.16)", "#cbd5e1"),
    "Brand owned": ("rgba(34,211,238,0.16)", "#22d3ee"),
    "Industry / Partner": ("rgba(16,185,129,0.16)", "#34d399"),
}

rows_html = []
for ch in channels:
    plat = ch.get("platform", "")
    _, p_color = pill_colors.get(plat, ("", "#22d3ee"))
    ctype = ch.get("conversation_type", "Question driven")
    b_bg, b_fg = badge_styles.get(ctype, ("rgba(148,163,184,0.16)", "#cbd5e1"))
    note_txt = ch.get("note", "")
    mentions_val = ch.get("mentions", 0)
    rows_html.append(
        f'<tr style="border-bottom:1px solid #1a2230;">'
        f'<td style="padding:14px 18px;font-weight:700;color:{p_color};font-family:monospace;">{plat}</td>'
        f'<td style="padding:14px 18px;text-align:center;font-weight:700;color:#f8fafc;">{mentions_val}</td>'
        f'<td style="padding:14px 18px;"><span class="badge" style="background:{b_bg};color:{b_fg};">{ctype}</span></td>'
        f'<td style="padding:14px 18px;color:#94a3b8;font-size:0.88rem;">{note_txt}</td>'
        f'</tr>'
    )

table_html = (
    '<table style="width:100%;border-collapse:collapse;background:#11161f;border-radius:10px;overflow:hidden;border:1px solid #1e293b;">'
    '<thead>'
    '<tr style="border-bottom:1px solid #1e293b;text-align:left;font-family:monospace;font-size:0.78rem;color:#64748b;">'
    '<th style="padding:14px 18px;">PLATFORM</th>'
    '<th style="padding:14px 18px;text-align:center;">MENTIONS</th>'
    '<th style="padding:14px 18px;">CONVERSATION TYPE</th>'
    '<th style="padding:14px 18px;">NOTE</th>'
    '</tr>'
    '</thead>'
    '<tbody>'
    + "".join(rows_html)
    + f'<tr style="background:#0d1219;">'
    f'<td style="padding:14px 18px;font-weight:800;color:#f8fafc;font-family:monospace;">Total analyzed</td>'
    f'<td style="padding:14px 18px;text-align:center;font-weight:800;color:#22d3ee;">{total_mentions}</td>'
    f'<td></td><td></td>'
    f'</tr>'
    '</tbody></table>'
)
st.markdown(table_html, unsafe_allow_html=True)

st.markdown('<hr class="report-divider">', unsafe_allow_html=True)

# === 04 SENTIMENT ANALYSIS ===
st.markdown('<div id="04-sentiment-analysis"></div>', unsafe_allow_html=True)
st.markdown('<div class="section-kicker">// 04 SENTIMENT ANALYSIS</div>', unsafe_allow_html=True)
st.markdown(f"## {sent.get('headline', 'Conversation Polarity')}")
st.write(sent.get("intro", ""))

pos_p = sent.get("positive_pct", 50)
neg_p = sent.get("negative_pct", 25)
neu_p = sent.get("neutral_pct", 25)

sc1, sc2, sc3 = st.columns(3)
with sc1:
    st.markdown(f'<div class="sent-card-pos"><div style="font-family:monospace;font-size:0.75rem;color:#34d399;">POSITIVE</div><div style="font-size:2.2rem;font-weight:800;color:#34d399;">{pos_p}%</div></div>', unsafe_allow_html=True)
with sc2:
    st.markdown(f'<div class="sent-card-neg"><div style="font-family:monospace;font-size:0.75rem;color:#f87171;">NEGATIVE</div><div style="font-size:2.2rem;font-weight:800;color:#f87171;">{neg_p}%</div></div>', unsafe_allow_html=True)
with sc3:
    st.markdown(f'<div class="sent-card-neu"><div style="font-family:monospace;font-size:0.75rem;color:#94a3b8;">NEUTRAL</div><div style="font-size:2.2rem;font-weight:800;color:#e2e8f0;">{neu_p}%</div></div>', unsafe_allow_html=True)

st.markdown(
    f'<div style="margin:1.4rem 0 0.5rem 0;font-family:monospace;font-size:0.75rem;color:#64748b;">OVERALL SENTIMENT DISTRIBUTION</div>'
    f'<div style="display:flex;width:100%;height:26px;border-radius:6px;overflow:hidden;font-family:monospace;font-size:0.75rem;font-weight:700;">'
    f'<div style="width:{pos_p}%;background:#22c55e;color:#052e16;display:flex;align-items:center;justify-content:center;">{pos_p}%</div>'
    f'<div style="width:{neg_p}%;background:#ef4444;color:#fff;display:flex;align-items:center;justify-content:center;">{neg_p}%</div>'
    f'<div style="width:{neu_p}%;background:#64748b;color:#fff;display:flex;align-items:center;justify-content:center;">{neu_p}%</div>'
    f'</div>'
    f'<p style="color:#94a3b8;font-size:0.92rem;margin-top:0.9rem;">{sent.get("narrative", "")}</p>',
    unsafe_allow_html=True,
)

tq, tr = st.columns(2)
with tq:
    st.markdown("#### On Quora")
    for item in sent.get("quora_threads", [])[:3]:
        st.markdown(
            f'<div class="thread-card"><div style="font-weight:600;color:#e2e8f0;margin-bottom:6px;">"{item.get("title", "")}"</div>'
            f'<span class="badge" style="background:rgba(34,211,238,0.14);color:#22d3ee;">{item.get("tag", "Quora")}</span></div>',
            unsafe_allow_html=True,
        )
with tr:
    st.markdown("#### On Reddit")
    for item in sent.get("reddit_threads", [])[:3]:
        st.markdown(
            f'<div class="thread-card"><div style="font-weight:600;color:#e2e8f0;margin-bottom:6px;">"{item.get("title", "")}"</div>'
            f'<span class="badge" style="background:rgba(249,115,22,0.14);color:#fb923c;">{item.get("tag", "Reddit")}</span></div>',
            unsafe_allow_html=True,
        )

st.markdown('<hr class="report-divider">', unsafe_allow_html=True)

# === 05 NEWS & MEDIA COVERAGE ===
st.markdown('<div id="05-news-media-coverage"></div>', unsafe_allow_html=True)
st.markdown('<div class="section-kicker">// 05 NEWS & MEDIA COVERAGE</div>', unsafe_allow_html=True)
st.markdown("## Press & Third-Party Authority Signals")
if report.get("news_media"):
    st.dataframe(pd.DataFrame(report["news_media"]), use_container_width=True, hide_index=True)

st.markdown('<hr class="report-divider">', unsafe_allow_html=True)

# === 06 COMPETITOR LANDSCAPE ===
st.markdown('<div id="06-competitor-landscape"></div>', unsafe_allow_html=True)
st.markdown('<div class="section-kicker">// 06 COMPETITOR LANDSCAPE</div>', unsafe_allow_html=True)
st.markdown("## Category Share of Voice & AI Authority")
if report.get("competitor_landscape"):
    st.dataframe(pd.DataFrame(report["competitor_landscape"]), use_container_width=True, hide_index=True)

st.markdown('<hr class="report-divider">', unsafe_allow_html=True)

# === 07 TOP PAIN POINTS ===
st.markdown('<div id="07-top-pain-points"></div>', unsafe_allow_html=True)
st.markdown('<div class="section-kicker">// 07 TOP PAIN POINTS</div>', unsafe_allow_html=True)
st.markdown("## Buyer Objections & AEO Friction")
for pp in report.get("top_pain_points", []):
    with st.container(border=True):
        st.markdown(f"**{pp.get('pain_point')}** &nbsp; `{pp.get('frequency')} Frequency`")
        st.caption(f"AEO Impact: {pp.get('aeo_impact')}")

st.markdown('<hr class="report-divider">', unsafe_allow_html=True)

# === 08 FULL THREAD ANALYSIS (LIVE HARVESTED EVIDENCE) ===
st.markdown('<div id="08-full-thread-analysis"></div>', unsafe_allow_html=True)
st.markdown('<div class="section-kicker">// 08 FULL THREAD ANALYSIS</div>', unsafe_allow_html=True)
st.markdown("## Harvested Live Citations & Threads")
for ch_name, items in report.get("raw_evidence", {}).items():
    if items:
        with st.expander(f"{ch_name} ({len(items)} sampled sources)"):
            for it in items:
                st.markdown(f"**[{it.get('title')}]({it.get('url')})**")
                st.caption(it.get("snippet"))

st.markdown('<hr class="report-divider">', unsafe_allow_html=True)

# === 09 RESPONSE PLAYBOOK ===
st.markdown('<div id="09-response-playbook"></div>', unsafe_allow_html=True)
st.markdown('<div class="section-kicker">// 09 RESPONSE PLAYBOOK</div>', unsafe_allow_html=True)
st.markdown("## Community & Citation Intervention Playbook")
if report.get("response_playbook"):
    st.dataframe(pd.DataFrame(report["response_playbook"]), use_container_width=True, hide_index=True)

st.markdown('<hr class="report-divider">', unsafe_allow_html=True)

# === 10 CONTENT STRATEGY ===
st.markdown('<div id="10-content-strategy"></div>', unsafe_allow_html=True)
st.markdown('<div class="section-kicker">// 10 CONTENT STRATEGY</div>', unsafe_allow_html=True)
st.markdown("## AEO Content & Schema Roadmap")
for step in report.get("content_strategy", []):
    with st.container(border=True):
        st.markdown(f"**{step.get('pillar')}** — *Target Queries: {step.get('target_queries')}*")
        st.write(step.get("execution_step"))

st.download_button(
    "⬇️ Export Full Report (JSON)",
    data=json.dumps(report, indent=2),
    file_name=f"brand_intelligence_{crawl['domain']}.json",
    mime="application/json",
)
