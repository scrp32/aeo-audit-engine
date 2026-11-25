import json
import re
import time
from urllib.parse import urljoin, urlparse

import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup
from google import genai
from google.genai import types

st.set_page_config(
    page_title="AEO Visibility & Readiness Auditor",
    page_icon="🔍",
    layout="wide",
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    )
}

AI_BOTS = ["GPTBot", "OAI-SearchBot", "Google-Extended", "PerplexityBot", "ClaudeBot"]

RECOMMENDED_SCHEMAS = {
    "Organization",
    "LocalBusiness",
    "FAQPage",
    "Article",
    "Product",
    "Service",
    "WebSite",
    "BreadcrumbList",
    "HowTo",
}

# Models available on the Gemini API Free Tier (with separate per-model quotas)
MODEL_CANDIDATES = [
    "gemini-4-hydrogen",
    "gemini-3.8-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash-lite",
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


def generate_with_resilience(
    client: genai.Client,
    primary_model: str,
    contents: str,
    config: types.GenerateContentConfig,
):
    """Tries primary model, waits briefly on 503, and switches model immediately on 404/429."""
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
                # Immediately switch to next model if quota (429) or not found (404)
                if any(k in err_str for k in ["404", "NOT_FOUND", "429", "RESOURCE_EXHAUSTED"]):
                    break
                # Brief backoff only for transient 503 overload
                if "503" in err_str or "UNAVAILABLE" in err_str:
                    time.sleep(2 * (attempt + 1))
                    continue
                raise err

    raise RuntimeError(
        f"Gemini API quota/availability error across fallback models ({', '.join(ordered_models)}). "
        f"If 'Live Google Search Grounding' is checked, uncheck it in the sidebar (requires a paid Tier 1 key) "
        f"or wait 60 seconds for per-minute quota reset. Details: {last_err}"
    )


def check_robots_and_llms(base_url: str) -> dict:
    parsed = urlparse(base_url)
    root = f"{parsed.scheme}://{parsed.netloc}"
    bot_status = {bot: "Allowed (Default)" for bot in AI_BOTS}
    robots_found = False
    llms_txt_found = False

    try:
        r = requests.get(urljoin(root, "/robots.txt"), headers=HEADERS, timeout=8)
        if r.status_code == 200 and "user-agent" in r.text.lower():
            robots_found = True
            current_agents = []
            for line in r.text.splitlines():
                line = line.split("#")[0].strip()
                if not line:
                    continue
                if line.lower().startswith("user-agent:"):
                    agent = line.split(":", 1)[1].strip()
                    current_agents = [agent]
                elif line.lower().startswith("disallow:"):
                    path = line.split(":", 1)[1].strip()
                    if path == "/":
                        for bot in AI_BOTS:
                            if "*" in current_agents or any(
                                bot.lower() == a.lower() for a in current_agents
                            ):
                                bot_status[bot] = "Blocked (Disallow: /)"
    except Exception:
        pass

    try:
        l_res = requests.get(urljoin(root, "/llms.txt"), headers=HEADERS, timeout=6)
        if l_res.status_code == 200 and len(l_res.text.strip()) > 40 and "<html" not in l_res.text.lower():
            llms_txt_found = True
    except Exception:
        pass

    return {
        "robots_found": robots_found,
        "llms_txt_found": llms_txt_found,
        "bot_status": bot_status,
    }


def extract_json_ld_types(soup: BeautifulSoup) -> list[str]:
    found_types = []
    for script in soup.find_all("script", type="application/ld+json"):
        if not script.string:
            continue
        try:
            data = json.loads(script.string)
            items = data if isinstance(data, list) else [data]
            for item in items:
                if isinstance(item, dict):
                    if "@graph" in item and isinstance(item["@graph"], list):
                        for node in item["@graph"]:
                            t = node.get("@type")
                            if isinstance(t, list):
                                found_types.extend(t)
                            elif isinstance(t, str):
                                found_types.append(t)
                    t = item.get("@type")
                    if isinstance(t, list):
                        found_types.extend(t)
                    elif isinstance(t, str):
                        found_types.append(t)
        except Exception:
            continue
    return sorted(set(found_types))


def crawl_site(url: str) -> dict:
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")

    title = soup.title.string.strip() if soup.title and soup.title.string else ""
    meta_desc_tag = soup.find("meta", attrs={"name": re.compile("^description$", re.I)})
    meta_desc = meta_desc_tag.get("content", "").strip() if meta_desc_tag else ""

    h1s = [h.get_text(" ", strip=True) for h in soup.find_all("h1")]
    h2s = [h.get_text(" ", strip=True) for h in soup.find_all("h2")]
    h3s = [h.get_text(" ", strip=True) for h in soup.find_all("h3")]

    all_headings = h1s + h2s + h3s
    question_headings = [
        h
        for h in all_headings
        if "?" in h
        or h.lower().startswith(("what ", "how ", "why ", "when ", "where ", "which ", "can ", "is "))
    ]

    schemas = extract_json_ld_types(soup)
    bots_and_llms = check_robots_and_llms(resp.url)

    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    body_text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
    word_count = len(body_text.split())

    has_semantic_tags = bool(soup.find(["main", "article", "section"]))
    has_tables_or_lists = len(soup.find_all(["ul", "ol", "table"])) >= 2

    score = 0
    breakdown = {}

    allowed_count = sum(1 for v in bots_and_llms["bot_status"].values() if "Allowed" in v)
    crawler_pts = int((allowed_count / len(AI_BOTS)) * 20) + (5 if bots_and_llms["llms_txt_found"] else 0)
    score += crawler_pts
    breakdown["AI Crawler & llms.txt Access"] = f"{crawler_pts}/25"

    schema_pts = min(25, len(schemas) * 8 + (5 if "FAQPage" in schemas else 0))
    score += schema_pts
    breakdown["Schema & Entity Markup"] = f"{schema_pts}/25"

    qa_pts = min(15, len(question_headings) * 5)
    struct_pts = (8 if has_semantic_tags else 0) + (7 if has_tables_or_lists else 0)
    score += qa_pts + struct_pts
    breakdown["Q&A Coverage & Extractable Formatting"] = f"{qa_pts + struct_pts}/30"

    entity_pts = (
        (5 if title else 0)
        + (5 if len(meta_desc) >= 60 else 0)
        + (5 if len(h1s) == 1 else 2 if len(h1s) > 1 else 0)
        + (5 if word_count >= 350 else 2)
    )
    score += entity_pts
    breakdown["Entity Clarity & Content Depth"] = f"{entity_pts}/20"

    return {
        "final_url": resp.url,
        "domain": urlparse(resp.url).netloc.replace("www.", ""),
        "title": title,
        "meta_description": meta_desc,
        "h1s": h1s[:5],
        "h2s": h2s[:12],
        "question_headings": question_headings[:10],
        "word_count": word_count,
        "schemas_found": schemas,
        "schemas_missing": sorted(RECOMMENDED_SCHEMAS - set(schemas)),
        "bots_and_llms": bots_and_llms,
        "readiness_score": score,
        "score_breakdown": breakdown,
        "body_excerpt": body_text[:4000],
    }


def run_llm_and_serp_audit(
    client: genai.Client,
    model_name: str,
    use_search_grounding: bool,
    crawl_data: dict,
    market: str,
    competitors_override: list[str],
    concern: str,
) -> dict:
    # Call 1: Entity, Competitors & Test Plan (No search tool needed -> fast & quota-light)
    discovery_prompt = f"""
Analyze this crawled webpage and generate an AEO test plan for target market: {market}.
Domain: {crawl_data['domain']}
Title: {crawl_data['title']}
Meta Description: {crawl_data['meta_description']}
H1s: {crawl_data['h1s']}
H2s: {crawl_data['h2s']}
User's specific AEO concern: {concern or 'General AI recommendation visibility'}
User-supplied competitors (use these if non-empty, otherwise infer 2 top direct competitors in {market}): {competitors_override}
Page Text Excerpt:
{crawl_data['body_excerpt']}

Return strict JSON with keys:
- "brand_name": string
- "category": string (concise category description)
- "competitors": list of 2 direct competitor brand names in {market}
- "buyer_prompts": list of 5 realistic unbranded buyer-intent prompts a prospect in {market} would ask ChatGPT/Gemini when looking for this solution (do NOT include the brand name)
- "core_keywords": list of 4 core commercial/informational Google search keywords for this business in {market}
"""
    plan_resp = generate_with_resilience(
        client=client,
        primary_model=model_name,
        contents=discovery_prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.2,
        ),
    )
    plan = safe_json_loads(plan_resp.text)

    brand = plan["brand_name"]
    domain = crawl_data["domain"]
    competitors = plan["competitors"][:2]
    buyer_prompts = plan["buyer_prompts"][:5]

    # Call 2: Single Consolidated Visibility + Competitive + SERP + Opportunities Assessment
    # (Uses 1 API call instead of 6 so it never trips Free Tier RPM limits)
    tools_list = [types.Tool(google_search=types.GoogleSearch())] if use_search_grounding else None

    audit_prompt = f"""
You are a senior Answer Engine Optimization (AEO) & Generative Engine Optimization (GEO) auditor.
Evaluate {brand} ({domain}) vs competitors {competitors} in target market: {market}.

Crawled Technical Data:
- AEO Readiness Score: {crawl_data['readiness_score']}/100 ({crawl_data['score_breakdown']})
- Found JSON-LD Schemas: {crawl_data['schemas_found']}
- Missing JSON-LD Schemas: {crawl_data['schemas_missing']}
- AI Crawler & llms.txt Status: {crawl_data['bots_and_llms']}
- Question Headings Found: {crawl_data['question_headings']}

Unbranded Buyer Prompts to Evaluate for {market}:
{json.dumps(buyer_prompts, indent=2)}

Core Google Search Keywords to Evaluate for {market}:
{json.dumps(plan['core_keywords'], indent=2)}

Return strict JSON with these exact keys:
1. "prompt_evaluations": list of 5 objects (one for each buyer prompt above) with keys:
   - "prompt": string (exact prompt text)
   - "brand_mentioned": boolean (true if {brand} is realistically recommended/mentioned in AI answers today for this unbranded query in {market})
   - "domain_cited": boolean (true if {domain} is likely cited as a source link)
   - "competitors_recommended": list of competitor/incumbent brands typically recommended instead
   - "simulated_ai_answer": string (concise 2-3 sentence realistic AI answer showing how an assistant answers this buyer query today)
2. "competitive_snapshot": string (markdown comparison of {brand} vs {competitors[0]} and {competitors[1]} across AI entity recognition, third-party citations, review/directory presence, and content authority in {market})
3. "serp_checks": list of 4 objects (one per core keyword) with keys:
   - "keyword": string
   - "brand_visibility": string (e.g. "Strong Branded", "Competing on Page 1", "Low / Displaced by Aggregators")
   - "ai_overview_risk": string ("High - AI answers directly", "Medium", "Low")
   - "dominant_domains": list of 2-3 domains/platforms dominating this query in {market}
4. "schema_recommendations": list of 3 specific JSON-LD schema additions tailored to {domain} with exact rationale
5. "top_3_opportunities": list of 3 objects, each with:
   - "title": string
   - "impact": string ("Critical" or "High")
   - "effort": string ("Low", "Medium", or "High")
   - "action_plan": string (specific, actionable steps tailored to {domain} and {market})
"""
    audit_resp = generate_with_resilience(
        client=client,
        primary_model=model_name,
        contents=audit_prompt,
        config=types.GenerateContentConfig(
            tools=tools_list,
            response_mime_type="application/json",
            temperature=0.2,
        ),
    )
    synthesis = safe_json_loads(audit_resp.text)

    # Extract grounded URLs if search grounding was enabled
    grounded_urls = []
    cand = audit_resp.candidates[0] if audit_resp.candidates else None
    if cand and cand.grounding_metadata and cand.grounding_metadata.grounding_chunks:
        for chunk in cand.grounding_metadata.grounding_chunks:
            if chunk.web and chunk.web.uri:
                grounded_urls.append(chunk.web.uri)

    prompt_results = []
    brand_mentions = 0
    brand_citations = 0

    for item in synthesis.get("prompt_evaluations", []):
        m_bool = bool(item.get("brand_mentioned"))
        c_bool = bool(item.get("domain_cited"))
        if m_bool:
            brand_mentions += 1
        if c_bool:
            brand_citations += 1
        comps = item.get("competitors_recommended") or []
        prompt_results.append(
            {
                "Prompt": item.get("prompt", ""),
                "Brand Mentioned": "✅ Yes" if m_bool else "❌ No",
                "Domain Cited": "✅ Yes" if c_bool else "❌ No",
                "Competitors Recommended": ", ".join(comps) if comps else "None / Other brands",
                "AI Answer Snippet": item.get("simulated_ai_answer", ""),
            }
        )

    return {
        "plan": plan,
        "brand_mentions": brand_mentions,
        "brand_citations": brand_citations,
        "prompt_results": prompt_results,
        "grounded_urls": grounded_urls[:10],
        "synthesis": synthesis,
    }


# --- UI LAYOUT ---
st.title("🔍 AEO & AI Visibility Auditor")
st.caption(
    "6-section Answer Engine Optimization audit: checks AI crawler access, schema gaps, "
    "unbranded buyer prompt visibility, competitor share of voice, and SERP displacement."
)

with st.sidebar:
    st.header("Configuration")
    api_key = st.secrets.get("GEMINI_API_KEY", "") if hasattr(st, "secrets") else ""
    if not api_key:
        api_key = st.text_input("Gemini API Key", type="password", help="Or set GEMINI_API_KEY in Streamlit Secrets")

    model_name = st.selectbox(
        "Primary Gemini Model",
        MODEL_CANDIDATES,
        index=0,
    )
    use_search_grounding = st.checkbox(
        "Enable Live Google Search Grounding",
        value=False,
        help="Requires a paid Tier 1+ Gemini API billing account (5,000 free grounded calls/mo). Leave unchecked on the $0 Free Tier.",
    )
    market = st.selectbox(
        "Target Market",
        ["India", "United States", "United Kingdom", "Singapore", "United Arab Emirates", "Australia", "Global"],
        index=0,
    )
    comp_input = st.text_input(
        "Optional: 2 Direct Competitors (comma-separated)",
        placeholder="e.g., Hudle, Playo (leave blank to auto-detect)",
    )
    concern = st.text_area(
        "Biggest AEO / Visibility Concern (optional)",
        placeholder="e.g., We rank on Google but ChatGPT/Gemini recommend competitors instead.",
        height=80,
    )

col_url, col_btn = st.columns([4, 1])
with col_url:
    target_url = st.text_input("Website URL", placeholder="[https://example.com](https://example.com)", label_visibility="collapsed")
with col_btn:
    run_audit = st.button("Run AEO Audit", type="primary", use_container_width=True)

if run_audit:
    if not api_key:
        st.error("Please provide a Gemini API key in the sidebar or via Streamlit Secrets (`GEMINI_API_KEY`).")
        st.stop()
    if not target_url.strip():
        st.warning("Enter a valid website URL.")
        st.stop()

    clean_url = normalize_url(target_url)
    competitors_override = [c.strip() for c in comp_input.split(",") if c.strip()][:2]

    with st.status("Running 6-Point AEO Audit...", expanded=True) as status:
        st.write("1/3 Crawling page structure, `robots.txt`, `llms.txt`, and JSON-LD schema...")
        try:
            crawl_data = crawl_site(clean_url)
        except Exception as e:
            st.error(f"Failed to crawl `{clean_url}`: {e}")
            st.stop()

        st.write("2/3 Evaluating unbranded buyer prompts, competitors & SERP visibility...")
        client = genai.Client(api_key=api_key)
        try:
            audit_data = run_llm_and_serp_audit(
                client=client,
                model_name=model_name,
                use_search_grounding=use_search_grounding,
                crawl_data=crawl_data,
                market=market,
                competitors_override=competitors_override,
                concern=concern,
            )
        except Exception as e:
            st.error(f"LLM Visibility Audit failed: {e}")
            st.stop()

        st.write("3/3 Rendering 6-section AEO report...")
        status.update(label="AEO Audit Complete!", state="complete", expanded=False)

    plan = audit_data["plan"]
    synth = audit_data["synthesis"]

    st.divider()
    st.subheader(f"AEO Visibility Report: {plan['brand_name']} (`{crawl_data['domain']}`)")
    st.caption(
        f"Category: **{plan['category']}** | Market: **{market}** | "
        f"Benchmarked Competitors: **{', '.join(plan['competitors'])}**"
    )

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("AEO Readiness Score", f"{crawl_data['readiness_score']}/100")
    m2.metric("LLM Brand Mentions", f"{audit_data['brand_mentions']} / 5 prompts")
    m3.metric("Direct Domain Citations", f"{audit_data['brand_citations']} / 5 prompts")
    m4.metric("Schemas Detected", f"{len(crawl_data['schemas_found'])}")

    st.markdown("### 1. LLM Visibility Check (Unbranded Buyer Prompts)")
    df_prompts = pd.DataFrame(audit_data["prompt_results"])
    st.dataframe(
        df_prompts[["Prompt", "Brand Mentioned", "Domain Cited", "Competitors Recommended"]],
        use_container_width=True,
        hide_index=True,
    )
    with st.expander("View Sample AI Responses"):
        for row in audit_data["prompt_results"]:
            st.markdown(f"**Prompt:** {row['Prompt']}")
            st.write(row["AI Answer Snippet"])
            st.divider()

    st.markdown("### 2. Competitive Snapshot")
    st.markdown(synth.get("competitive_snapshot", ""))

    st.markdown("### 3. AEO Readiness Score & AI Bot Access")
    c_left, c_right = st.columns(2)
    with c_left:
        st.markdown("**Score Breakdown**")
        for k, v in crawl_data["score_breakdown"].items():
            st.write(f"- **{k}:** {v}")
        st.write(f"- **`llms.txt` Present:** {'✅ Yes' if crawl_data['bots_and_llms']['llms_txt_found'] else '❌ Missing'}")
        st.write(f"- **Question-Based Headings:** {len(crawl_data['question_headings'])} found")
    with c_right:
        st.markdown("**AI Crawler Permissions (`robots.txt`)**")
        bot_df = pd.DataFrame(
            [{"AI Crawler": k, "Status": v} for k, v in crawl_data["bots_and_llms"]["bot_status"].items()]
        )
        st.dataframe(bot_df, use_container_width=True, hide_index=True)

    st.markdown("### 4. SERP & Google AI Overview Position Check")
    if synth.get("serp_checks"):
        st.dataframe(pd.DataFrame(synth["serp_checks"]), use_container_width=True, hide_index=True)

    st.markdown("### 5. Schema Gap Analysis")
    s1, s2 = st.columns(2)
    with s1:
        st.success(f"**Detected JSON-LD Types:** {', '.join(crawl_data['schemas_found']) or 'None detected'}")
    with s2:
        st.warning(f"**Missing High-Value Types:** {', '.join(crawl_data['schemas_missing'])}")
    for rec in synth.get("schema_recommendations", []):
        st.write(f"- {rec}")

    st.markdown("### 6. Top 3 High-Impact AEO Opportunities")
    for idx, opp in enumerate(synth.get("top_3_opportunities", [])[:3], start=1):
        with st.container(border=True):
            st.markdown(f"**#{idx}: {opp.get('title')}** — Impact: `{opp.get('impact')}` | Effort: `{opp.get('effort')}`")
            st.write(opp.get("action_plan"))

    if audit_data["grounded_urls"]:
        with st.expander("Grounded Google Search Sources Used"):
            for u in audit_data["grounded_urls"]:
                st.write(f"- {u}")

    report_payload = json.dumps(
        {"crawl_data": crawl_data, "audit_data": audit_data},
        indent=2,
        default=str,
    )
    st.download_button(
        label="⬇️ Download Full Audit Data (JSON)",
        data=report_payload,
        file_name=f"aeo_audit_{crawl_data['domain']}.json",
        mime="application/json",
    )
