import datetime
import json
import re
import time
import xml.etree.ElementTree as ET
from urllib.parse import quote_plus, urlparse

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
    font-size: 2.8rem;
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
    margin-bottom: 1.5rem;
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
.kpi-val-cyan {
    font-size: 2.1rem;
    font-weight: 800;
    color: #22d3ee;
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
    padding: 15px 18px;
    margin-bottom: 10px;
}
.pressure-box {
    background: rgba(239, 68, 68, 0.07);
    border-left: 4px solid #ef4444;
    border-top: 1px solid rgba(239, 68, 68, 0.22);
    border-right: 1px solid rgba(239, 68, 68, 0.22);
    border-bottom: 1px solid rgba(239, 68, 68, 0.22);
    border-radius: 8px;
    padding: 16px 20px;
    margin-top: 14px;
}
.badge {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 6px;
    font-family: monospace;
    font-size: 0.76rem;
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
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

MODEL_CANDIDATES = [
    "gemini-3.8-flash",
    "gemini-3.5-flash-lite",
    "gemini-4-hydrogen",
    "gemini-3.6-flash",
]

CHANNELS = [
    ("Reddit", "site:reddit.com", "#f97316", 45),
    ("Quora", "site:quora.com", "#eab308", 45),
    ("G2", "site:g2.com", "#ef4444", 15),
    ("Web", "", "#38bdf8", 100),
    ("News", "", "#10b981", 50),
    ("X", "site:x.com OR site:twitter.com", "#64748b", 20),
    ("YouTube", "site:youtube.com", "#f43f5e", 20),
    ("Facebook", "site:facebook.com", "#3b82f6", 20),
    ("Instagram", "site:instagram.com", "#a855f7", 20),
]

KNOWN_AUTHORITY_1000 = {
    "nytimes.com": 940,
    "yahoo.com": 930,
    "finance.yahoo.com": 930,
    "forbes.com": 920,
    "bloomberg.com": 915,
    "reuters.com": 910,
    "economictimes.indiatimes.com": 820,
    "brandequity.economictimes.indiatimes.com": 820,
    "indiatimes.com": 780,
    "hindustantimes.com": 760,
    "livemint.com": 750,
    "moneycontrol.com": 745,
    "business-standard.com": 720,
    "gqindia.com": 680,
    "yourstory.com": 670,
    "inc42.com": 660,
    "mensxp.com": 640,
    "prnewswire.com": 640,
    "businesswire.com": 635,
    "wwd.com": 610,
    "vogue.in": 620,
    "vogue.com": 790,
    "reddit.com": 890,
    "quora.com": 850,
    "youtube.com": 960,
    "linkedin.com": 950,
    "instagram.com": 930,
    "facebook.com": 940,
    "x.com": 920,
    "twitter.com": 920,
    "g2.com": 770,
    "trustpilot.com": 760,
    "wikipedia.org": 970,
    "amazon.in": 880,
    "amazon.com": 950,
}

BOT_BLOCK_MARKERS = [
    "just a moment",
    "attention required",
    "access denied",
    "cloudflare",
    "enable javascript",
    "verify you are human",
    "403 forbidden",
]


def extract_clean_host(url: str) -> str:
    """Returns exact normalized hostname (e.g. 'x.com', 'netflix.com') so suffix checks don't false-match."""
    try:
        host = urlparse(url.strip()).netloc.lower()
        host = host.split(":")[0]
        if host.startswith("www."):
            host = host[4:]
        return host
    except Exception:
        return ""


def host_matches_allowed(url: str, allowed_domains: list[str]) -> bool:
    """Exact domain or subdomain match: 'x.com' matches 'x.com' & 'mobile.x.com', NEVER 'netflix.com'."""
    host = extract_clean_host(url)
    if not host:
        return False
    for d in allowed_domains:
        d_clean = d.lower().removeprefix("www.")
        if host == d_clean or host.endswith("." + d_clean):
            return True
    return False


def estimate_domain_authority_1000(url: str) -> tuple[str, int]:
    netloc = extract_clean_host(url)
    if not netloc:
        return ("unknown", 220)

    if netloc in KNOWN_AUTHORITY_1000:
        return (netloc, KNOWN_AUTHORITY_1000[netloc])

    parts = netloc.split(".")
    root = ".".join(parts[-2:]) if len(parts) >= 2 else netloc
    if root in KNOWN_AUTHORITY_1000:
        return (netloc, KNOWN_AUTHORITY_1000[root])

    score = 260
    if netloc.endswith((".gov", ".gov.in", ".edu", ".ac.in", ".org")):
        score += 180
    elif any(k in netloc for k in ["news", "times", "post", "journal", "tribune", "daily", "magazine", "wire", "spotlight", "equity"]):
        score += 210
    elif any(k in netloc for k in ["blog", "wordpress", "blogspot", "medium", "substack"]):
        score += 70
    if len(parts) > 2:
        score -= 35
    return (netloc, max(120, min(680, score)))


def normalize_url(raw_url: str) -> str:
    raw_url = raw_url.strip()
    md_match = re.match(r"^\[.*?\]\((https?://.*?)\)$", raw_url)
    if md_match:
        raw_url = md_match.group(1).strip()
    if not raw_url.startswith(("http://", "https://")):
        raw_url = "https://" + raw_url
    return raw_url


def humanize_domain_name(domain: str) -> str:
    stem = domain.lower().removeprefix("www.").split(".")[0]
    if "-" in stem:
        return " ".join(w.capitalize() for w in stem.split("-") if w)
    known_splits = {
        "naturaldiamondcouncil": "Natural Diamond Council",
        "naturaldiamonds": "Natural Diamonds",
        "himscience": "H.I.M",
    }
    if stem in known_splits:
        return known_splits[stem]
    return stem.capitalize()


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
    errors_seen = []

    for model_id in ordered_models:
        try:
            return client.models.generate_content(
                model=model_id,
                contents=contents,
                config=config,
            )
        except Exception as err:
            err_msg = str(err)
            errors_seen.append(f"{model_id}: {err_msg[:180]}")
            upper = err_msg.upper()
            if any(k in upper for k in ["503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED"]):
                time.sleep(3)
                continue
            if "404" in upper or "NOT_FOUND" in upper:
                continue
            raise RuntimeError(f"Gemini API Error on {model_id}: {err_msg}")

    raise RuntimeError(" | ".join(errors_seen))


def crawl_homepage_resilient(url: str) -> dict:
    domain = extract_clean_host(url)
    fallback_brand = humanize_domain_name(domain)

    try:
        resp = requests.get(url, headers=HEADERS, timeout=12)
        if resp.status_code >= 400:
            raise ValueError(f"HTTP {resp.status_code}")
        soup = BeautifulSoup(resp.text, "lxml")
        title = soup.title.string.strip() if soup.title and soup.title.string else ""
        if any(m in title.lower() for m in BOT_BLOCK_MARKERS):
            raise ValueError("Bot challenge page detected")

        og_site_tag = soup.find("meta", attrs={"property": "og:site_name"})
        og_site_name = og_site_tag.get("content", "").strip() if og_site_tag else ""
        meta_tag = soup.find("meta", attrs={"name": re.compile("^description$", re.I)})
        meta_desc = meta_tag.get("content", "").strip() if meta_tag else ""
        h1s = [h.get_text(" ", strip=True) for h in soup.find_all("h1")]

        for tag in soup(["script", "style", "noscript", "svg"]):
            tag.decompose()
        text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))

        return {
            "final_url": resp.url,
            "domain": extract_clean_host(resp.url) or domain,
            "title": title,
            "og_site_name": og_site_name,
            "meta_description": meta_desc,
            "h1s": h1s[:4],
            "excerpt": text[:1600],
            "crawl_blocked": False,
            "fallback_brand": fallback_brand,
        }
    except Exception as e:
        return {
            "final_url": url,
            "domain": domain,
            "title": "",
            "og_site_name": "",
            "meta_description": "",
            "h1s": [],
            "excerpt": "",
            "crawl_blocked": True,
            "crawl_note": str(e),
            "fallback_brand": fallback_brand,
        }


def resolve_brand_queries_via_llm(
    client: genai.Client,
    model_name: str,
    crawl_data: dict,
    market: str,
    brand_override: str,
) -> dict:
    prompt = f"""
Identify the brand and search queries for a Brand Intelligence & AEO audit.
URL: {crawl_data['final_url']} | Domain: {crawl_data['domain']} | Market: {market}
User Brand Override: {brand_override}
Page Title: {crawl_data['title']} | OG Site: {crawl_data['og_site_name']} | Meta: {crawl_data['meta_description']}
Crawl Blocked by WAF: {crawl_data['crawl_blocked']}

Return strict JSON:
{{
  "brand_name": "Clean official brand name (use User Brand Override if provided; otherwise infer accurately from domain/title, e.g. Natural Diamond Council for naturaldiamondcouncil.com, or H.I.M for himscience.com)",
  "category": "concise category",
  "is_b2b_software": true or false,
  "brand_queries": [
    "exact brand query 1 (e.g. \\"Natural Diamond Council\\")",
    "domain or secondary brand query 2 (e.g. \\"Only Natural Diamonds\\")"
  ],
  "category_discussion_query": "core consumer/buyer debate query for Reddit/Quora (e.g. natural diamonds vs lab grown)",
  "relevance_keywords": ["3-5 lowercase keywords that confirm an article/thread is actually about this brand or its exact industry"]
}}
"""
    try:
        resp = generate_with_resilience(
            client=client,
            primary_model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.1),
        )
        data = safe_json_loads(resp.text)
        if brand_override.strip():
            data["brand_name"] = brand_override.strip()
        return data
    except Exception:
        b = brand_override.strip() or crawl_data["fallback_brand"]
        return {
            "brand_name": b,
            "category": "Consumer / Commercial Brand",
            "is_b2b_software": False,
            "brand_queries": [f'"{b}"', f'"{crawl_data["domain"]}"'],
            "category_discussion_query": b,
            "relevance_keywords": [w.lower() for w in b.split() if len(w) >= 3] + [crawl_data["domain"].split(".")[0]],
        }


# --- SEARCH ENGINE PROVIDERS ---
def search_via_serper(query: str, serper_key: str, gl: str = "in", num: int = 30, search_type: str = "search") -> list[dict]:
    endpoint = "[https://google.serper.dev/news](https://google.serper.dev/news)" if search_type == "news" else "[https://google.serper.dev/search](https://google.serper.dev/search)"
    resp = requests.post(
        endpoint,
        headers={"X-API-KEY": serper_key, "Content-Type": "application/json"},
        json={"q": query, "gl": gl, "num": min(num, 100)},
        timeout=12,
    )
    resp.raise_for_status()
    data = resp.json()
    items = data.get("news", []) if search_type == "news" else data.get("organic", [])
    return [
        {
            "title": it.get("title", ""),
            "body": it.get("snippet", ""),
            "href": it.get("link", ""),
        }
        for it in items
        if it.get("link")
    ]


def search_via_tavily(query: str, tavily_key: str, max_results: int = 20, include_domains: list[str] | None = None) -> list[dict]:
    payload = {
        "api_key": tavily_key,
        "query": query,
        "search_depth": "basic",
        "max_results": min(max_results, 20),
    }
    if include_domains:
        payload["include_domains"] = include_domains
    resp = requests.post("[https://api.tavily.com/search](https://api.tavily.com/search)", json=payload, timeout=15)
    resp.raise_for_status()
    return [
        {
            "title": it.get("title", ""),
            "body": it.get("content", "")[:200],
            "href": it.get("url", ""),
        }
        for it in resp.json().get("results", [])
        if it.get("url")
    ]


def search_google_news_rss(query: str, gl: str = "IN", max_res: int = 30) -> list[dict]:
    url = f"[https://news.google.com/rss/search?q=](https://news.google.com/rss/search?q=){quote_plus(query)}&hl=en-{gl}&gl={gl}&ceid={gl}:en"
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        if r.status_code != 200:
            return []
        root = ET.fromstring(r.text)
        out = []
        for item in root.findall(".//item")[:max_res]:
            title = item.findtext("title") or ""
            link = item.findtext("link") or ""
            source_el = item.find("source")
            src_url = source_el.attrib.get("url", "") if source_el is not None else ""
            out.append({"title": title, "body": title, "href": src_url or link})
        return out
    except Exception:
        return []


def collect_live_mentions_novastacks_scale(
    brand_meta: dict,
    domain: str,
    market: str,
    serper_key: str = "",
    tavily_key: str = "",
) -> tuple[dict, dict]:
    region_map = {
        "India": ("in-en", "in", "IN"),
        "United States": ("us-en", "us", "US"),
        "United Kingdom": ("uk-en", "gb", "GB"),
        "Singapore": ("sg-en", "sg", "SG"),
        "Australia": ("au-en", "au", "AU"),
        "Global": ("wt-wt", "us", "US"),
    }
    ddg_region, gl_low, gl_up = region_map.get(market, ("wt-wt", "us", "US"))
    evidence = {ch[0]: [] for ch in CHANNELS}
    telemetry = {ch[0]: {"raw": 0, "kept": 0} for ch in CHANNELS}
    seen_urls = set()
    diag = {
        "engine": "Serper (Google SERP)" if serper_key else "Tavily Search" if tavily_key else "Free DDGS + Google RSS",
        "errors": [],
        "telemetry": telemetry,
    }

    brand_name = brand_meta.get("brand_name", domain)
    brand_queries = brand_meta.get("brand_queries") or [f'"{brand_name}"']
    cat_query = brand_meta.get("category_discussion_query") or brand_queries[0]
    rel_keywords = [k.lower() for k in brand_meta.get("relevance_keywords", []) if len(k) >= 3]
    domain_stem = domain.split(".")[0].lower()

    clean_brand = brand_name.replace('"', "").strip()
    clean_cat = re.sub(r'["()]', "", cat_query).split(" OR ")[0].strip()

    domain_matchers = {
        "Reddit": ["reddit.com"],
        "Quora": ["quora.com"],
        "G2": ["g2.com"],
        "X": ["x.com", "twitter.com"],
        "YouTube": ["youtube.com", "youtu.be"],
        "Facebook": ["facebook.com"],
        "Instagram": ["instagram.com"],
    }

    def is_relevant(title: str, snippet: str, url: str, strict: bool = True, exact_brand_only: bool = False) -> bool:
        hay = f"{title} {snippet} {url}".lower()
        if domain.lower() in hay or (len(domain_stem) >= 6 and domain_stem in hay):
            return True
        if len(clean_brand) >= 5 and clean_brand.lower() in hay:
            return True
        if exact_brand_only:
            return False
        if not strict and len(clean_brand) >= 6:
            return True
        if rel_keywords and any(kw in hay for kw in rel_keywords):
            return True
        return False

    def ingest(
        channel_name: str,
        raw_list: list[dict],
        cap: int,
        required_domains: list[str] | None = None,
        exclude_own_domain: bool = False,
        strict_relevance: bool = True,
        exact_brand_only: bool = False,
    ):
        telemetry[channel_name]["raw"] += len(raw_list)
        target_bucket = evidence[channel_name]
        for it in raw_list:
            if len(target_bucket) >= cap:
                break
            u = it.get("href") or it.get("url") or ""
            if not u or u in seen_urls:
                continue
            if required_domains and not host_matches_allowed(u, required_domains):
                continue
            title_txt = it.get("title", "").strip()
            snip_txt = (it.get("body") or it.get("snippet") or "").strip()[:180]
            if not is_relevant(title_txt, snip_txt, u, strict=strict_relevance, exact_brand_only=exact_brand_only):
                continue
            dom, da = estimate_domain_authority_1000(u)
            if exclude_own_domain and (dom == domain.lower() or dom.endswith("." + domain.lower())):
                continue
            seen_urls.add(u)
            target_bucket.append(
                {
                    "title": title_txt,
                    "snippet": snip_txt,
                    "url": u,
                    "domain": dom,
                    "authority_1000": da,
                }
            )
        telemetry[channel_name]["kept"] = len(target_bucket)

    def run_web_query(query: str, max_res: int, include_domains: list[str] | None = None) -> list[dict]:
        if serper_key:
            try:
                return search_via_serper(query, serper_key, gl=gl_low, num=max_res, search_type="search")
            except Exception as e:
                diag["errors"].append(f"Serper: {str(e)[:120]}")

        if tavily_key:
            try:
                return search_via_tavily(query, tavily_key, max_results=max_res, include_domains=include_domains)
            except Exception as e:
                diag["errors"].append(f"Tavily: {str(e)[:120]}")

        try:
            with DDGS() as ddgs:
                time.sleep(0.25)
                res = list(ddgs.text(query, region=ddg_region, max_results=max_res))
                if res:
                    return res
        except Exception as e:
            msg = f"DDGS web: {str(e)[:90]}"
            if msg not in diag["errors"]:
                diag["errors"].append(msg)
        return []

    # 1. Social & Forum channels
    for name, site_filter, _, cap in CHANNELS:
        if name in ("Web", "News"):
            continue
        req_doms = domain_matchers.get(name)
        is_g2 = name == "G2"

        # Pass 1: Direct quoted brand query (require exact brand/domain match on G2 to prevent software false positives)
        r1 = run_web_query(f'"{clean_brand}" {site_filter}', cap, include_domains=req_doms)
        ingest(name, r1, cap, required_domains=req_doms, strict_relevance=is_g2, exact_brand_only=is_g2)

        # Pass 2: Domain-stem query for X/Facebook/Reddit/Quora if still below cap
        if not is_g2 and len(evidence[name]) < cap and len(domain_stem) >= 6:
            r1b = run_web_query(f"{domain_stem} {site_filter}", cap, include_domains=req_doms)
            ingest(name, r1b, cap, required_domains=req_doms, strict_relevance=True)

        # Pass 3: Category debate query on Reddit & Quora
        if name in ("Reddit", "Quora") and len(evidence[name]) < cap and clean_cat.lower() != clean_brand.lower():
            r2 = run_web_query(f"{clean_cat} {site_filter}", cap, include_domains=req_doms)
            ingest(name, r2, cap, required_domains=req_doms, strict_relevance=True)

    # 2. News (50 target)
    if serper_key:
        try:
            ingest(
                "News",
                search_via_serper(clean_brand, serper_key, gl=gl_low, num=35, search_type="news"),
                50,
                strict_relevance=False,
            )
            if len(evidence["News"]) < 50 and clean_cat.lower() != clean_brand.lower():
                ingest(
                    "News",
                    search_via_serper(clean_cat, serper_key, gl=gl_low, num=25, search_type="news"),
                    50,
                    strict_relevance=True,
                )
        except Exception as e:
            diag["errors"].append(f"Serper News: {str(e)[:120]}")
    else:
        try:
            with DDGS() as ddgs:
                ingest("News", list(ddgs.news(clean_brand, region=ddg_region, max_results=30)), 50, strict_relevance=False)
                if len(evidence["News"]) < 50 and clean_cat.lower() != clean_brand.lower():
                    ingest("News", list(ddgs.news(clean_cat, region=ddg_region, max_results=30)), 50, strict_relevance=True)
        except Exception:
            pass
        if len(evidence["News"]) < 25:
            ingest("News", search_google_news_rss(clean_brand, gl=gl_up, max_res=30), 50, strict_relevance=False)

    # 3. General Web (100 target — clean queries without chained -site: operators)
    w1 = run_web_query(f'"{clean_brand}"', 60)
    ingest("Web", w1, 100, exclude_own_domain=True, strict_relevance=False)
    if len(evidence["Web"]) < 100 and clean_cat.lower() != clean_brand.lower():
        w2 = run_web_query(clean_cat, 60)
        ingest("Web", w2, 100, exclude_own_domain=True, strict_relevance=True)

    if len(evidence["Web"]) == 0 and not serper_key and not tavily_key:
        rss_web = search_google_news_rss(f"{clean_brand} OR {clean_cat}", gl=gl_up, max_res=30)
        ingest("Web", rss_web, 40, exclude_own_domain=True, strict_relevance=True)

    return evidence, diag


def run_brand_intelligence_pipeline(
    client: genai.Client,
    model_name: str,
    crawl_data: dict,
    market: str,
    competitors_override: list[str],
    brand_override: str = "",
    serper_key: str = "",
    tavily_key: str = "",
) -> dict:
    brand_meta = resolve_brand_queries_via_llm(client, model_name, crawl_data, market, brand_override)
    brand = brand_meta["brand_name"]

    evidence, search_diag = collect_live_mentions_novastacks_scale(
        brand_meta, crawl_data["domain"], market, serper_key=serper_key, tavily_key=tavily_key
    )

    actual_counts = {ch: len(items) for ch, items in evidence.items()}
    total_harvested = sum(actual_counts.values())
    active_channel_count = sum(1 for v in actual_counts.values() if v > 0)

    web_and_news = evidence.get("Web", []) + evidence.get("News", [])
    avg_da = int(sum(x["authority_1000"] for x in web_and_news) / len(web_and_news)) if web_and_news else 280

    combined_authority_pool = sorted(
        web_and_news,
        key=lambda x: x["authority_1000"],
        reverse=True,
    )[:6]

    digest_for_llm = {
        ch: [
            {
                "title": it["title"][:110],
                "snippet": it["snippet"][:140],
                "domain": it["domain"],
                "da": it["authority_1000"],
            }
            for it in items[:7]
        ]
        for ch, items in evidence.items()
        if items
    }

    synthesis_prompt = f"""
You are a senior Brand Intelligence & AEO analyst producing an executive report matching Novastacks AI's methodology.
Brand: {brand} | Category: {brand_meta.get('category')} | Domain: {crawl_data['domain']} | Market: {market}
User Competitor Overrides (ONLY use if non-empty; otherwise infer actual category competitors for {brand} in {market}): {competitors_override}
Actual Harvested Mention Counts: {json.dumps(actual_counts)} (Total: {total_harvested}, Active: {active_channel_count}/9)
Average Source Domain Authority: {avg_da}/1000

Live Harvested Evidence Sample:
{json.dumps(digest_for_llm)}

IMPORTANT RULES:
- Every headline in "news_cards" and "top_authority_sentiments" MUST come strictly from the Live Harvested Evidence Sample above.
- If User Competitor Overrides is empty, identify 2-3 real direct competitors in {market} for {brand}'s industry.

Return strict JSON:
{{
  "entity": {{
    "brand_name": "{brand}",
    "category": "{brand_meta.get('category')}",
    "is_b2b_software": {str(brand_meta.get('is_b2b_software', False)).lower()},
    "direct_competitors": [
      {{"domain": "competitor1.com", "type": "Branded retail / Direct SaaS / Marketplace", "summary": "1 sentence on how they compete"}}
    ],
    "category_pressure": {{
      "label": "Primary alternative/substitute category creating buyer skepticism",
      "summary": "2 sentences explaining how this alternative drives skeptical threads."
    }}
  }},
  "executive_summary": {{
    "headline": "What People Are Saying: <6-10 word thesis>",
    "paragraphs": [
      "Paragraph 1 summarizing total mentions ({total_harvested} across {active_channel_count} of 9 channels) and sentiment split.",
      "Paragraph 2 summarizing Quora & Reddit question/debate themes citing real titles from the evidence.",
      "Paragraph 3 summarizing News/Media and owned channel balance and the core narrative gap to manage."
    ]
  }},
  "freshness_score": integer (0-100),
  "score_commentary": "2 sentence takeaway on what holds back the Brand Health Score.",
  "channel_notes": [
    {{
      "platform": "Reddit",
      "conversation_type": "Debate / Mixed | Question driven | Not applicable (consumer brand) | Polarized | Mostly positive | Brand / Trade | Brand owned | Industry / Partner",
      "note": "concise note",
      "deep_dive_read": "1-2 sentence qualitative read on this channel"
    }}
  ],
  "sentiment": {{
    "headline": "2-4 word headline e.g. A Polarized Conversation",
    "intro": "2 sentence explanation of the sentiment classification.",
    "positive_pct": integer,
    "negative_pct": integer,
    "neutral_pct": integer,
    "narrative": "2-3 sentence analytical callout explaining what drives negative vs positive share.",
    "quora_threads": [
      {{"title": "real Quora question from evidence", "tag": "Mentions Brand or Category"}}
    ],
    "reddit_threads": [
      {{"title": "real Reddit thread from evidence", "tag": "r/subreddit"}}
    ]
  }},
  "news_cards": [
    {{
      "headline": "real news/press headline from evidence",
      "domain": "outlet.com",
      "tone": "Positive | Negative | Neutral",
      "summary": "1-2 sentence summary of the coverage."
    }}
  ],
  "top_authority_sentiments": [
    {{
      "domain": "domain",
      "headline": "headline",
      "authority": integer,
      "sentiment": "Positive | Negative | Neutral"
    }}
  ],
  "top_pain_points": [
    {{
      "title": "Pain point title",
      "channels": "e.g. Quora, Web",
      "detail": "1-2 sentence explanation."
    }}
  ],
  "thread_triage": {{
    "response_recommended_count": integer,
    "priority_threads": [
      {{
        "source": "Reddit r/... or Quora",
        "title": "real thread title from evidence",
        "priority": "High priority | Medium priority",
        "recommendation": "Concrete, non-defensive reply strategy."
      }}
    ]
  }},
  "response_playbook": [
    {{
      "channel": "Reddit | Quora | News | Owned Content",
      "action": "Actionable playbook rule"
    }}
  ],
  "content_strategy": [
    {{
      "pillar": "Pillar 1: ...",
      "description": "Concrete content & AEO execution plan for {market}."
    }}
  ]
}}
"""
    synth_resp = generate_with_resilience(
        client=client,
        primary_model=model_name,
        contents=synthesis_prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.2),
    )
    ai_out = safe_json_loads(synth_resp.text)
    entity = ai_out.get("entity", {"brand_name": brand, "category": "", "is_b2b_software": False})

    pos_pct = ai_out.get("sentiment", {}).get("positive_pct", 50)
    sent_score = max(0, min(100, int(pos_pct)))
    vol_score = min(100, int((total_harvested / 300) * 100))
    reach_score = min(100, int((avg_da / 1000) * 100))
    cov_score = int((active_channel_count / 9) * 100)
    fresh_score = max(0, min(100, int(ai_out.get("freshness_score", 55))))

    brand_health_score = round(
        sent_score * 0.30
        + vol_score * 0.20
        + reach_score * 0.20
        + cov_score * 0.15
        + fresh_score * 0.15
    )

    notes_by_plat = {n["platform"]: n for n in ai_out.get("channel_notes", [])}
    merged_channels = []
    for name, _, _, _ in CHANNELS:
        cnt = actual_counts.get(name, 0)
        meta = notes_by_plat.get(name, {})
        ctype = meta.get("conversation_type", "Not applicable" if cnt == 0 else "Question driven")
        if cnt == 0 and name == "G2" and not entity.get("is_b2b_software"):
            ctype = "Not applicable (consumer brand)"
        merged_channels.append(
            {
                "platform": name,
                "mentions": cnt,
                "conversation_type": ctype,
                "note": meta.get("note", ""),
                "deep_dive_read": meta.get("deep_dive_read", meta.get("note", "")),
            }
        )

    return {
        "entity": entity,
        "brand_health_score": brand_health_score,
        "total_mentions": total_harvested,
        "active_platforms": active_channel_count,
        "avg_da": avg_da,
        "search_diag": search_diag,
        "brand_meta": brand_meta,
        "subscores": {
            "Sentiment": {"score": sent_score, "weight": "30%", "basis": f"{pos_pct}% positive across analyzed web"},
            "Volume": {"score": vol_score, "weight": "20%", "basis": f"{total_harvested} total harvested mentions"},
            "Reach": {"score": reach_score, "weight": "20%", "basis": f"Avg domain authority {avg_da}/1000"},
            "Coverage": {"score": cov_score, "weight": "15%", "basis": f"{active_channel_count} of 9 platforms"},
            "Freshness": {"score": fresh_score, "weight": "15%", "basis": "Recency of indexed mentions"},
        },
        "channels": merged_channels,
        "authority_table": ai_out.get("top_authority_sentiments")
        or [
            {
                "domain": x["domain"],
                "headline": x["title"],
                "authority": x["authority_1000"],
                "sentiment": "Neutral",
            }
            for x in combined_authority_pool[:6]
        ],
        "ai": ai_out,
        "evidence": evidence,
    }


# --- SIDEBAR NAVIGATION & INPUTS ---
with st.sidebar:
    st.markdown("### 🧬 NOVASTACKS-STYLE AUDIT")
    st.caption(f"Report Date: {datetime.date.today().strftime('%B %d, %Y')}")
    st.divider()

    api_key = st.secrets.get("GEMINI_API_KEY", "") if hasattr(st, "secrets") else ""
    if not api_key:
        api_key = st.text_input("Gemini API Key", type="password", help="Or set GEMINI_API_KEY in Streamlit Secrets")

    serper_key = st.secrets.get("SERPER_API_KEY", "") if hasattr(st, "secrets") else ""
    tavily_key = st.secrets.get("TAVILY_API_KEY", "") if hasattr(st, "secrets") else ""
    if not serper_key and not tavily_key:
        with st.expander("🔍 Search API Key (Boosts Volume to 300+)", expanded=False):
            serper_key = st.text_input(
                "Serper.dev API Key (Recommended)",
                type="password",
                help="Free 2,500 Google SERP queries at serper.dev",
            )
            tavily_key = st.text_input(
                "OR Tavily API Key",
                type="password",
                help="Optional alternative: free 1,000 searches/mo at tavily.com",
            )

    target_url = st.text_input("Target Website URL", placeholder="[https://www.naturaldiamondcouncil.com](https://www.naturaldiamondcouncil.com)")
    brand_override = st.text_input("Brand Name (optional)", placeholder="Auto-detected from site if blank")
    market = st.selectbox(
        "Target Market",
        ["India", "United States", "United Kingdom", "Singapore", "Australia", "Global"],
        index=0,
    )
    comp_input = st.text_input("Direct Competitors (optional)", placeholder="Leave blank to auto-detect")
    model_name = st.selectbox("Model", MODEL_CANDIDATES, index=0)
    run_btn = st.button("Generate Full Report", type="primary", use_container_width=True)

    st.divider()
    st.markdown(
        '<div style="font-family:monospace;font-size:0.79rem;line-height:1.95;color:#94a3b8;">'
        '<div style="color:#22d3ee;font-weight:700;">REPORT NAVIGATION</div>'
        '<a href="#cover" style="color:#cbd5e1;text-decoration:none;">Cover</a><br>'
        '<a href="#01-executive-summary" style="color:#cbd5e1;text-decoration:none;">01 Executive Summary</a><br>'
        '<a href="#02-brand-health-score" style="color:#cbd5e1;text-decoration:none;">02 Brand Health Score</a><br>'
        '<a href="#03-channel-overview" style="color:#cbd5e1;text-decoration:none;">03 Channel Overview</a><br>'
        '<a href="#04-sentiment-analysis" style="color:#cbd5e1;text-decoration:none;">04 Sentiment Analysis</a><br>'
        '<a href="#05-news-media-coverage" style="color:#cbd5e1;text-decoration:none;">05 News &amp; Media Coverage</a><br>'
        '<a href="#06-competitor-landscape" style="color:#cbd5e1;text-decoration:none;">06 Competitor Landscape</a><br>'
        '<a href="#07-top-pain-points" style="color:#cbd5e1;text-decoration:none;">07 Top Pain Points</a><br>'
        '<div style="color:#475569;font-size:0.7rem;margin-top:8px;">DEEP DIVE &amp; PLAYBOOK</div>'
        '<a href="#08-full-thread-analysis" style="color:#cbd5e1;text-decoration:none;">08 Full Thread Analysis</a><br>'
        '<a href="#09-social-media-deep-dive" style="color:#cbd5e1;text-decoration:none;">09 Social Media Deep Dive</a><br>'
        '<a href="#10-response-playbook" style="color:#cbd5e1;text-decoration:none;">10 Response Playbook</a><br>'
        '<a href="#11-content-strategy" style="color:#cbd5e1;text-decoration:none;">11 Content Strategy</a>'
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

    with st.status("Running 11-Section Brand Intelligence & AEO Harvest...", expanded=True) as status:
        st.write("1/3 Crawling target URL metadata (with WAF fallback)...")
        crawl_data = crawl_homepage_resilient(clean_url)
        if crawl_data.get("crawl_blocked"):
            st.write(f"ℹ️ Site WAF blocked direct scrape ({crawl_data.get('crawl_note')}); using AI domain entity resolution.")

        st.write("2/3 Harvesting live Reddit, Quora, News, Web & Social threads + Domain Authority...")
        client = genai.Client(api_key=api_key)
        try:
            report = run_brand_intelligence_pipeline(
                client,
                model_name,
                crawl_data,
                market,
                comps,
                brand_override,
                serper_key=serper_key,
                tavily_key=tavily_key,
            )
        except Exception as e:
            st.error(f"API Quota / Model Error: {e}")
            st.stop()

        st.write("3/3 Computing weighted Brand Health Score, sentiment split & playbook...")
        status.update(label="Report Generated!", state="complete", expanded=False)

    st.session_state["bi_report"] = report
    st.session_state["bi_crawl"] = crawl_data

# --- RENDER REPORT ---
if "bi_report" not in st.session_state:
    st.info("👈 Paste any website URL in the left sidebar and click **Generate Full Report**.")
    st.stop()

report = st.session_state["bi_report"]
crawl = st.session_state["bi_crawl"]
entity = report["entity"]
ai = report["ai"]
channels = report["channels"]
total_mentions = report["total_mentions"]
active_platforms = report["active_platforms"]
sent = ai.get("sentiment", {})
neg_share = sent.get("negative_pct", 0)
health_score = report["brand_health_score"]
search_diag = report.get("search_diag", {})

if search_diag.get("errors") and total_mentions == 0:
    st.warning(
        f"**Search Engine Notice ({search_diag.get('engine')}):** `{search_diag['errors'][0]}` — "
        "Add a free **Serper.dev API key** (2,500 free Google searches) in the sidebar to populate all 9 platforms."
    )

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

# === COVER ===
st.markdown('<div id="cover"></div>', unsafe_allow_html=True)
st.markdown(f'<h1 class="hero-brand">{entity["brand_name"]}</h1>', unsafe_allow_html=True)
st.markdown('<h2 class="hero-sub">Brand Intelligence Report</h2>', unsafe_allow_html=True)
st.markdown(
    f'<div class="hero-meta">Quora, Reddit and {max(0, active_platforms - 2)} more channels for {crawl["domain"]}<br>'
    f'{datetime.date.today().strftime("%B %d, %Y")} &nbsp;|&nbsp; {market} Market</div>',
    unsafe_allow_html=True,
)
st.markdown(render_donut_svg(health_score, "Brand Health Score", 200), unsafe_allow_html=True)

k1, k2, k3 = st.columns(3)
with k1:
    st.markdown(f'<div class="kpi-box"><div class="kpi-val">{total_mentions}</div><div class="kpi-lbl">Mentions</div></div>', unsafe_allow_html=True)
with k2:
    st.markdown(f'<div class="kpi-box"><div class="kpi-val">{active_platforms} / 9</div><div class="kpi-lbl">Platforms</div></div>', unsafe_allow_html=True)
with k3:
    st.markdown(f'<div class="kpi-box"><div class="kpi-val-red">{neg_share}%</div><div class="kpi-lbl">Negative Share</div></div>', unsafe_allow_html=True)

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
exec_sum = ai.get("executive_summary", {})
st.markdown(f"## {exec_sum.get('headline', 'Executive Summary')}")
for para in exec_sum.get("paragraphs", []):
    st.write(para)

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
    for label, obj in report["subscores"].items():
        sc = obj["score"]
        sc_color = "#34d399" if sc >= 70 else "#facc15" if sc >= 45 else "#f87171"
        st.markdown(
            f'<div class="subscore-card">'
            f'<div><div style="color:#94a3b8;font-size:0.85rem;">{label}</div>'
            f'<div style="font-size:1.35rem;font-weight:800;color:{sc_color};">{sc} <span style="font-size:0.85rem;color:#64748b;">/ 100</span></div></div>'
            f'<div style="text-align:right;"><div style="font-family:monospace;font-size:0.8rem;color:#eab308;">{obj["weight"]} weight</div>'
            f'<div style="font-size:0.8rem;color:#64748b;">{obj["basis"]}</div></div>'
            f'</div>',
            unsafe_allow_html=True,
        )
st.caption(ai.get("score_commentary", ""))

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
    "Not applicable (consumer brand)": ("rgba(100,116,139,0.16)", "#94a3b8"),
    "Mostly positive": ("rgba(16,185,129,0.16)", "#34d399"),
    "Brand / Trade": ("rgba(148,163,184,0.16)", "#cbd5e1"),
    "Brand owned": ("rgba(34,211,238,0.16)", "#22d3ee"),
    "Industry / Partner": ("rgba(16,185,129,0.16)", "#34d399"),
}

rows_html = []
for ch in channels:
    plat = ch["platform"]
    _, p_color = pill_colors.get(plat, ("", "#22d3ee"))
    ctype = ch["conversation_type"]
    b_bg, b_fg = badge_styles.get(ctype, ("rgba(148,163,184,0.16)", "#cbd5e1"))
    rows_html.append(
        f'<tr style="border-bottom:1px solid #1a2230;">'
        f'<td style="padding:14px 18px;font-weight:700;color:{p_color};font-family:monospace;">{plat}</td>'
        f'<td style="padding:14px 18px;text-align:center;font-weight:700;color:#f8fafc;">{ch["mentions"]}</td>'
        f'<td style="padding:14px 18px;"><span class="badge" style="background:{b_bg};color:{b_fg};">{ctype}</span></td>'
        f'<td style="padding:14px 18px;color:#94a3b8;font-size:0.88rem;">{ch["note"]}</td>'
        f'</tr>'
    )

table_html = (
    '<table style="width:100%;border-collapse:collapse;background:#11161f;border-radius:10px;overflow:hidden;border:1px solid #1e293b;">'
    '<thead><tr style="border-bottom:1px solid #1e293b;text-align:left;font-family:monospace;font-size:0.78rem;color:#64748b;">'
    '<th style="padding:14px 18px;">PLATFORM</th><th style="padding:14px 18px;text-align:center;">MENTIONS</th>'
    '<th style="padding:14px 18px;">CONVERSATION TYPE</th><th style="padding:14px 18px;">NOTE</th></tr></thead><tbody>'
    + "".join(rows_html)
    + f'<tr style="background:#0d1219;"><td style="padding:14px 18px;font-weight:800;color:#f8fafc;font-family:monospace;">Total analyzed</td>'
    f'<td style="padding:14px 18px;text-align:center;font-weight:800;color:#22d3ee;">{total_mentions}</td><td></td><td></td></tr>'
    '</tbody></table>'
)
st.markdown(table_html, unsafe_allow_html=True)

with st.expander("🔎 Harvest Telemetry (Raw Search Hits vs. Kept After Filtering)"):
    tel = search_diag.get("telemetry", {})
    bmeta = report.get("brand_meta", {})
    st.caption(
        f"Engine: **{search_diag.get('engine')}** | Resolved Brand: **{bmeta.get('brand_name')}** | "
        f"Category Query: `{bmeta.get('category_discussion_query')}` | Keywords: `{bmeta.get('relevance_keywords')}`"
    )
    if tel:
        tel_df = pd.DataFrame(
            [{"Platform": k, "Raw Hits": v["raw"], "Kept": v["kept"]} for k, v in tel.items()]
        )
        st.dataframe(tel_df, use_container_width=True, hide_index=True)

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
    f'</div><p style="color:#94a3b8;font-size:0.92rem;margin-top:0.9rem;">{sent.get("narrative", "")}</p>',
    unsafe_allow_html=True,
)

quora_cnt = next((c["mentions"] for c in channels if c["platform"] == "Quora"), 0)
reddit_cnt = next((c["mentions"] for c in channels if c["platform"] == "Reddit"), 0)
tq, tr = st.columns(2)
with tq:
    st.markdown(f"#### On Quora ({quora_cnt} questions)")
    for item in sent.get("quora_threads", [])[:5]:
        st.markdown(
            f'<div class="thread-card"><div style="font-weight:600;color:#e2e8f0;margin-bottom:6px;">"{item.get("title", "")}"</div>'
            f'<span class="badge" style="background:rgba(34,211,238,0.14);color:#22d3ee;">{item.get("tag", "Quora")}</span></div>',
            unsafe_allow_html=True,
        )
with tr:
    st.markdown(f"#### On Reddit ({reddit_cnt} threads)")
    for item in sent.get("reddit_threads", [])[:5]:
        st.markdown(
            f'<div class="thread-card"><div style="font-weight:600;color:#e2e8f0;margin-bottom:6px;">"{item.get("title", "")}"</div>'
            f'<span class="badge" style="background:rgba(249,115,22,0.14);color:#fb923c;">{item.get("tag", "Reddit")}</span></div>',
            unsafe_allow_html=True,
        )

st.markdown('<hr class="report-divider">', unsafe_allow_html=True)

# === 05 NEWS & MEDIA COVERAGE ===
st.markdown('<div id="05-news-media-coverage"></div>', unsafe_allow_html=True)
st.markdown('<div class="section-kicker">// 05 NEWS & MEDIA COVERAGE</div>', unsafe_allow_html=True)
st.markdown("## Press & Earned Media Coverage")

for idx, nc in enumerate(ai.get("news_cards", [])[:6], start=1):
    tone = nc.get("tone", "Neutral")
    t_bg, t_fg = (
        ("rgba(16,185,129,0.16)", "#34d399")
        if tone == "Positive"
        else ("rgba(239,68,68,0.16)", "#f87171")
        if tone == "Negative"
        else ("rgba(148,163,184,0.16)", "#cbd5e1")
    )
    st.markdown(
        f'<div class="thread-card">'
        f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">'
        f'<span style="font-weight:700;color:#f8fafc;">{idx}. {nc.get("headline")}</span>'
        f'<span class="badge" style="background:{t_bg};color:{t_fg};">{tone}</span></div>'
        f'<div style="font-family:monospace;font-size:0.78rem;color:#22d3ee;margin-bottom:4px;">{nc.get("domain")}</div>'
        f'<div style="color:#94a3b8;font-size:0.88rem;">{nc.get("summary")}</div></div>',
        unsafe_allow_html=True,
    )

st.markdown("#### Top Web Mentions by Domain Authority (0–1000)")
if report.get("authority_table"):
    st.dataframe(pd.DataFrame(report["authority_table"]), use_container_width=True, hide_index=True)

st.markdown('<hr class="report-divider">', unsafe_allow_html=True)

# === 06 COMPETITOR LANDSCAPE ===
st.markdown('<div id="06-competitor-landscape"></div>', unsafe_allow_html=True)
st.markdown('<div class="section-kicker">// 06 COMPETITOR LANDSCAPE</div>', unsafe_allow_html=True)
st.markdown("## Direct Competitors & Category Pressure")

for dc in entity.get("direct_competitors", []):
    st.markdown(f"- **`{dc.get('domain')}`** *({dc.get('type')})*: {dc.get('summary')}")

cp = entity.get("category_pressure", {})
if cp:
    st.markdown(
        f'<div class="pressure-box">'
        f'<div style="font-family:monospace;font-size:0.76rem;color:#f87171;font-weight:700;">THE REAL PRESSURE — {cp.get("label", "").upper()}</div>'
        f'<div style="color:#e2e8f0;font-size:0.92rem;margin-top:6px;">{cp.get("summary", "")}</div></div>',
        unsafe_allow_html=True,
    )

st.markdown('<hr class="report-divider">', unsafe_allow_html=True)

# === 07 TOP PAIN POINTS ===
st.markdown('<div id="07-top-pain-points"></div>', unsafe_allow_html=True)
st.markdown('<div class="section-kicker">// 07 TOP PAIN POINTS</div>', unsafe_allow_html=True)
st.markdown("## Core Buyer Objections & Narrative Friction")

for idx, pp in enumerate(ai.get("top_pain_points", [])[:5], start=1):
    st.markdown(
        f'<div class="thread-card">'
        f'<div style="font-weight:700;color:#f8fafc;">{idx}. {pp.get("title")} '
        f'<span style="font-family:monospace;font-size:0.78rem;color:#eab308;">({pp.get("channels")})</span></div>'
        f'<div style="color:#94a3b8;font-size:0.88rem;margin-top:4px;">{pp.get("detail")}</div></div>',
        unsafe_allow_html=True,
    )

st.markdown('<hr class="report-divider">', unsafe_allow_html=True)

# === 08 FULL THREAD ANALYSIS ===
st.markdown('<div id="08-full-thread-analysis"></div>', unsafe_allow_html=True)
st.markdown('<div class="section-kicker">// 08 FULL THREAD ANALYSIS</div>', unsafe_allow_html=True)
st.markdown("## High-Priority Threads Requiring Response")

triage = ai.get("thread_triage", {})
tk1, tk2, tk3 = st.columns(3)
with tk1:
    st.markdown(f'<div class="kpi-box"><div class="kpi-val">{total_mentions}</div><div class="kpi-lbl">Total Mentions</div></div>', unsafe_allow_html=True)
with tk2:
    st.markdown(f'<div class="kpi-box"><div class="kpi-val-cyan">{quora_cnt + reddit_cnt}</div><div class="kpi-lbl">Quora + Reddit Threads</div></div>', unsafe_allow_html=True)
with tk3:
    st.markdown(f'<div class="kpi-box"><div class="kpi-val">{triage.get("response_recommended_count", len(triage.get("priority_threads", [])))}</div><div class="kpi-lbl">Response Recommended</div></div>', unsafe_allow_html=True)

for pt in triage.get("priority_threads", []):
    prio = pt.get("priority", "High priority")
    p_bg, p_fg = ("rgba(239,68,68,0.16)", "#f87171") if "High" in prio else ("rgba(234,179,8,0.16)", "#facc15")
    st.markdown(
        f'<div class="thread-card">'
        f'<div style="display:flex;justify-content:space-between;align-items:center;">'
        f'<span style="font-family:monospace;font-size:0.78rem;color:#22d3ee;">{pt.get("source")}</span>'
        f'<span class="badge" style="background:{p_bg};color:{p_fg};">{prio}</span></div>'
        f'<div style="font-weight:700;color:#f8fafc;margin:6px 0;">{pt.get("title")}</div>'
        f'<div style="color:#94a3b8;font-size:0.88rem;"><strong>Recommended:</strong> {pt.get("recommendation")}</div></div>',
        unsafe_allow_html=True,
    )

st.markdown('<hr class="report-divider">', unsafe_allow_html=True)

# === 09 SOCIAL MEDIA DEEP DIVE ===
st.markdown('<div id="09-social-media-deep-dive"></div>', unsafe_allow_html=True)
st.markdown('<div class="section-kicker">// 09 SOCIAL MEDIA DEEP DIVE</div>', unsafe_allow_html=True)
st.markdown("## Channel-by-Channel Qualitative Read")

dd_rows = [
    {
        "Channel": c["platform"],
        "Results": c["mentions"],
        "Qualitative Read": c["deep_dive_read"],
    }
    for c in channels
    if c["platform"] != "G2" or c["mentions"] > 0
]
st.dataframe(pd.DataFrame(dd_rows), use_container_width=True, hide_index=True)

st.markdown('<hr class="report-divider">', unsafe_allow_html=True)

# === 10 RESPONSE PLAYBOOK ===
st.markdown('<div id="10-response-playbook"></div>', unsafe_allow_html=True)
st.markdown('<div class="section-kicker">// 10 RESPONSE PLAYBOOK</div>', unsafe_allow_html=True)
st.markdown("## Tactical Community & PR Playbook")
for idx, rp in enumerate(ai.get("response_playbook", []), start=1):
    st.markdown(f"**{idx}. {rp.get('channel')}:** {rp.get('action')}")

st.markdown('<hr class="report-divider">', unsafe_allow_html=True)

# === 11 CONTENT STRATEGY ===
st.markdown('<div id="11-content-strategy"></div>', unsafe_allow_html=True)
st.markdown('<div class="section-kicker">// 11 CONTENT STRATEGY</div>', unsafe_allow_html=True)
st.markdown("## AEO Content & Entity Strategy Pillars")
for cs in ai.get("content_strategy", []):
    with st.container(border=True):
        st.markdown(f"**{cs.get('pillar')}**")
        st.write(cs.get("description"))

st.download_button(
    "⬇️ Export Full Report (JSON)",
    data=json.dumps(report, indent=2),
    file_name=f"brand_intelligence_{crawl['domain']}.json",
    mime="application/json",
)
