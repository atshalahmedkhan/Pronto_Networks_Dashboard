#!/usr/bin/env python3
"""
Pronto Networks — GTM Lead Intelligence System
================================================
Finds, enriches, scores, and drafts cold emails for ICP-matched prospects
using the Anthropic Claude API.

Usage:
    python pronto_gtm_system.py

Outputs (./output/):
    pronto_leads_dashboard.html
    pronto_leads.csv
    pronto_emails.txt
    progress.json
"""

from __future__ import annotations

import csv
import html
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from anthropic import Anthropic, APIError, APIConnectionError, RateLimitError
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MODEL = "claude-haiku-4-5"
BATCH_SIZE = 3
API_DELAY_SECONDS = 15.0
MAX_RETRIES = 4
RETRY_BASE_DELAY = 3.0

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"
PROGRESS_FILE = OUTPUT_DIR / "progress.json"
CSV_FILE = OUTPUT_DIR / "pronto_leads.csv"
EMAILS_FILE = OUTPUT_DIR / "pronto_emails.txt"
DASHBOARD_FILE = OUTPUT_DIR / "pronto_leads_dashboard.html"

TARGET_PROSPECT_COUNT = 25
TOP_EMAIL_COUNT = 10

PRONTO_CUSTOMERS = [
    "Toast",
    "SpotOn",
    "365 Retail Markets",
    "Lightspeed Retail",
    "Elavon",
]

ICP_INDUSTRIES = [
    "hospitality",
    "retail",
    "healthcare",
    "POS",
    "kiosk",
    "smart cities",
]

# ---------------------------------------------------------------------------
# Progress persistence (resume on crash)
# ---------------------------------------------------------------------------


class ProgressStore:
    """Read/write pipeline state to progress.json."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.data: dict[str, Any] = self._load()

    def _load(self) -> dict[str, Any]:
        if self.path.exists():
            try:
                with open(self.path, encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError) as exc:
                print(f"  [warn] Could not load progress: {exc}. Starting fresh.")
        return {
            "step": "prospects",
            "prospects": [],
            "enriched_indices": [],
            "scored_indices": [],
            "emails": {},
            "completed": False,
        }

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)

    @property
    def prospects(self) -> list[dict[str, Any]]:
        return self.data.setdefault("prospects", [])

    @prospects.setter
    def prospects(self, value: list[dict[str, Any]]) -> None:
        self.data["prospects"] = value
        self.save()

    def mark_enriched(self, index: int) -> None:
        indices: list[int] = self.data.setdefault("enriched_indices", [])
        if index not in indices:
            indices.append(index)
        self.save()

    def mark_scored(self, index: int) -> None:
        indices: list[int] = self.data.setdefault("scored_indices", [])
        if index not in indices:
            indices.append(index)
        self.save()

    def is_enriched(self, index: int) -> bool:
        return index in self.data.get("enriched_indices", [])

    def is_scored(self, index: int) -> bool:
        return index in self.data.get("scored_indices", [])


# ---------------------------------------------------------------------------
# Anthropic API helpers
# ---------------------------------------------------------------------------


def get_client() -> Anthropic:
    load_dotenv(BASE_DIR / ".env")
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: Set ANTHROPIC_API_KEY in pronto_gtm/.env")
        sys.exit(1)
    return Anthropic(api_key=api_key)


def extract_text(response: Any) -> str:
    """Concatenate all text blocks from a Messages API response."""
    parts: list[str] = []
    for block in response.content:
        if getattr(block, "type", None) == "text":
            parts.append(block.text)
    return "\n".join(parts).strip()


def parse_json_payload(text: str) -> Any:
    """Extract JSON from model output (raw or fenced code block)."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    # Try whole string first, then first JSON array/object substring
    for candidate in (text, _find_json_substring(text)):
        if not candidate:
            continue
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    raise ValueError(f"No valid JSON found in model response:\n{text[:500]}...")


def _find_json_substring(text: str) -> str | None:
    for opener, closer in (("[", "]"), ("{", "}")):
        start = text.find(opener)
        if start == -1:
            continue
        depth = 0
        in_string = False
        escape = False
        for i, ch in enumerate(text[start:], start):
            if escape:
                escape = False
                continue
            if ch == "\\" and in_string:
                escape = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == opener:
                depth += 1
            elif ch == closer:
                depth -= 1
                if depth == 0:
                    return text[start : i + 1]
    return None


def call_claude(
    client: Anthropic,
    prompt: str,
    *,
    max_tokens: int = 1500,
) -> str:
    """Call Claude with retries and delay between requests."""
    last_error: Exception | None = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            time.sleep(API_DELAY_SECONDS)
            return extract_text(response)

        except RateLimitError as exc:
            last_error = exc
            wait = RETRY_BASE_DELAY * (2 ** (attempt - 1))
            print(f"  [retry {attempt}/{MAX_RETRIES}] Rate limited — waiting {wait:.0f}s")
            time.sleep(wait)
        except (APIConnectionError, APIError) as exc:
            last_error = exc
            wait = RETRY_BASE_DELAY * attempt
            print(f"  [retry {attempt}/{MAX_RETRIES}] API error: {exc} — waiting {wait:.0f}s")
            time.sleep(wait)
        except Exception as exc:
            last_error = exc
            print(f"  [retry {attempt}/{MAX_RETRIES}] Unexpected: {exc}")
            time.sleep(RETRY_BASE_DELAY)

    raise RuntimeError(f"Claude API failed after {MAX_RETRIES} attempts: {last_error}")


# ---------------------------------------------------------------------------
# Pipeline steps
# ---------------------------------------------------------------------------


def step1_find_prospects(client: Anthropic, store: ProgressStore) -> list[dict[str, Any]]:
    """Generate 25 realistic ICP-matched prospect companies from Claude's knowledge."""
    existing = store.prospects
    if len(existing) >= TARGET_PROSPECT_COUNT:
        print(f"[skip] Already have {len(existing)} prospects in progress.json")
        return existing[:TARGET_PROSPECT_COUNT]

    all_prospects: list[dict[str, Any]] = list(existing)
    batch_num = len(all_prospects) // BATCH_SIZE

    while len(all_prospects) < TARGET_PROSPECT_COUNT:
        batch_num += 1
        need = min(BATCH_SIZE, TARGET_PROSPECT_COUNT - len(all_prospects))
        exclude = ", ".join(p["company_name"] for p in all_prospects) or "none yet"

        print(f"[{len(all_prospects) + 1}/{TARGET_PROSPECT_COUNT}] Generating prospects (batch {batch_num})...")

        prompt = f"""You are a B2B sales researcher for Pronto Networks, which provides WiFi, LTE, 5G, and HaLow networking infrastructure for connected businesses.

From your knowledge, generate exactly {need} REAL US companies that match this ICP:
- Industries: hospitality, retail, healthcare, POS systems, kiosks, or smart cities
- Employee count: approximately 50–500 employees
- Need reliable WiFi/LTE/5G networking for stores, venues, devices, or IoT
- Similar to Pronto customers: {", ".join(PRONTO_CUSTOMERS)}
- US headquarters preferred

Use only well-known real companies you are confident exist. Do NOT invent fictional company names.

Do NOT include companies already listed: {exclude}

Return ONLY a JSON array of {need} objects with these exact keys:
- company_name (string)
- website (string, full URL)
- industry (string)
- headquarters (string, city + state)
- employee_count (string, e.g. "150" or "200-300")
- why_networking (string, 1-2 sentences on why they need networking infrastructure)

No markdown, no explanation — JSON array only."""

        raw = call_claude(client, prompt, max_tokens=1500)
        batch = parse_json_payload(raw)
        if not isinstance(batch, list):
            raise ValueError("Expected JSON array of prospects")

        for item in batch:
            if isinstance(item, dict) and item.get("company_name"):
                all_prospects.append(_normalize_prospect(item))

        store.prospects = all_prospects
        print(f"  → {len(all_prospects)}/{TARGET_PROSPECT_COUNT} prospects collected")

    store.data["step"] = "enrichment"
    store.save()
    return all_prospects[:TARGET_PROSPECT_COUNT]


def _normalize_prospect(p: dict[str, Any]) -> dict[str, Any]:
    """Ensure consistent keys on a prospect record."""
    return {
        "company_name": str(p.get("company_name", "")).strip(),
        "website": str(p.get("website", "")).strip(),
        "industry": str(p.get("industry", "")).strip(),
        "headquarters": str(p.get("headquarters", p.get("headquarters_location", ""))).strip(),
        "employee_count": str(p.get("employee_count", p.get("estimated_employee_count", ""))).strip(),
        "why_networking": str(p.get("why_networking", p.get("why_they_need_networking_infrastructure", ""))).strip(),
        "decision_maker": "",
        "pain_points": [],
        "pronto_product": "",
        "tech_stack": "",
        "best_outreach_timing": "",
        "fit_score": 0,
        "score_reason": "",
        "email_subject": "",
        "email_body": "",
    }


def step2_enrich(client: Anthropic, store: ProgressStore) -> None:
    """Deep enrichment for each prospect."""
    prospects = store.prospects
    for i, company in enumerate(prospects):
        if store.is_enriched(i):
            continue
        name = company["company_name"]
        print(f"[{i + 1}/{len(prospects)}] Enriching: {name}...")

        prompt = f"""Using your knowledge of this company and industry, enrich the sales intelligence profile.

Company: {name}
Website: {company.get("website", "")}
Industry: {company.get("industry", "")}
Headquarters: {company.get("headquarters", "")}
Employees: {company.get("employee_count", "")}
Context: {company.get("why_networking", "")}

Pronto Networks sells: WiFi, LTE, 5G, and HaLow networking for hospitality, retail, healthcare, POS, and kiosk deployments.
Reference customers: {", ".join(PRONTO_CUSTOMERS)}

Return ONLY a JSON object with these keys:
- decision_maker (string, title to target e.g. "VP of IT")
- pain_points (array of exactly 3 strings about connectivity/networking pain)
- pronto_product (string: best fit among WiFi, LTE, 5G, HaLow — pick one primary)
- tech_stack (string, educated guess on their current tech)
- best_outreach_timing (string, when to reach out and why)

JSON only, no markdown."""

        try:
            raw = call_claude(client, prompt, max_tokens=1500)
            data = parse_json_payload(raw)
            if isinstance(data, dict):
                company["decision_maker"] = str(data.get("decision_maker", ""))
                company["pain_points"] = list(data.get("pain_points", []))[:3]
                company["pronto_product"] = str(data.get("pronto_product", ""))
                company["tech_stack"] = str(data.get("tech_stack", ""))
                company["best_outreach_timing"] = str(data.get("best_outreach_timing", ""))
            store.mark_enriched(i)
        except Exception as exc:
            print(f"  [warn] Enrichment failed for {name}: {exc}")

    store.data["step"] = "scoring"
    store.save()


def step3_score(client: Anthropic, store: ProgressStore) -> None:
    """ICP fit scoring 1–10 for each company."""
    prospects = store.prospects

    for batch_start in range(0, len(prospects), BATCH_SIZE):
        batch_indices = list(range(batch_start, min(batch_start + BATCH_SIZE, len(prospects))))
        if all(store.is_scored(i) for i in batch_indices):
            continue

        companies_payload = []
        for i in batch_indices:
            if store.is_scored(i):
                continue
            p = prospects[i]
            companies_payload.append(
                {
                    "index": i,
                    "company_name": p["company_name"],
                    "industry": p["industry"],
                    "employee_count": p["employee_count"],
                    "headquarters": p["headquarters"],
                    "why_networking": p["why_networking"],
                    "pronto_product": p.get("pronto_product", ""),
                }
            )

        if not companies_payload:
            continue

        names = ", ".join(c["company_name"] for c in companies_payload)
        print(f"[scoring batch] {names}...")

        prompt = f"""Score each company 1-10 for Pronto Networks ICP fit.

Scoring criteria (higher = better):
- Industry match: hospitality/retail/healthcare/POS/kiosk = higher
- Company size: 50-500 employees = sweet spot (10), outside range = lower
- Likely networking needs (stores, devices, venues, IoT)
- US geographic presence
- Similarity to Pronto customers: {", ".join(PRONTO_CUSTOMERS)}

Companies to score:
{json.dumps(companies_payload, indent=2)}

Return ONLY a JSON array with one object per company:
- index (int, same as input)
- fit_score (int 1-10)
- score_reason (string, one sentence)

JSON array only."""

        try:
            raw = call_claude(client, prompt, max_tokens=1500)
            scores = parse_json_payload(raw)
            if isinstance(scores, list):
                for item in scores:
                    if not isinstance(item, dict):
                        continue
                    idx = item.get("index")
                    if idx is None or not (0 <= idx < len(prospects)):
                        continue
                    prospects[idx]["fit_score"] = int(item.get("fit_score", 5))
                    prospects[idx]["score_reason"] = str(item.get("score_reason", ""))
                    store.mark_scored(idx)
            store.prospects = prospects
        except Exception as exc:
            print(f"  [warn] Scoring batch failed: {exc}")
            for c in companies_payload:
                idx = c["index"]
                if not store.is_scored(idx):
                    prospects[idx]["fit_score"] = 5
                    prospects[idx]["score_reason"] = "Default score — scoring API call failed"
                    store.mark_scored(idx)

    store.data["step"] = "emails"
    store.save()


def step4_emails(client: Anthropic, store: ProgressStore) -> None:
    """Personalized cold emails for top 10 by fit score."""
    prospects = sorted(store.prospects, key=lambda p: p.get("fit_score", 0), reverse=True)
    top = prospects[:TOP_EMAIL_COUNT]
    emails_done: dict[str, Any] = store.data.get("emails", {})

    for rank, company in enumerate(top, start=1):
        name = company["company_name"]
        if name in emails_done:
            company["email_subject"] = emails_done[name].get("subject", "")
            company["email_body"] = emails_done[name].get("body", "")
            continue

        print(f"[email {rank}/{TOP_EMAIL_COUNT}] Writing for: {name}...")

        pains = company.get("pain_points", [])
        pain_text = "\n".join(f"- {p}" for p in pains) if pains else "- connectivity at scale"

        prompt = f"""Write a personalized B2B cold email for Pronto Networks (WiFi, LTE, 5G, HaLow infrastructure).

Prospect:
- Company: {name}
- Industry: {company.get("industry", "")}
- Decision maker: {company.get("decision_maker", "IT leader")}
- Pain points:
{pain_text}
- Best Pronto product: {company.get("pronto_product", "WiFi")}
- Why they need networking: {company.get("why_networking", "")}

Reference ONE relevant Pronto customer as social proof: {", ".join(PRONTO_CUSTOMERS)}

Requirements:
- 4-5 sentences max in the body
- Human, conversational tone (not robotic)
- Reference their industry and a specific pain point
- Clear CTA: 15-minute call
- Include subject line

Return ONLY JSON:
{{"subject": "...", "body": "..."}}

JSON only."""

        try:
            raw = call_claude(client, prompt, max_tokens=1500)
            data = parse_json_payload(raw)
            if isinstance(data, dict):
                subject = str(data.get("subject", f"Quick idea for {name}'s network"))
                body = str(data.get("body", ""))
                company["email_subject"] = subject
                company["email_body"] = body
                emails_done[name] = {"subject": subject, "body": body}
                store.data["emails"] = emails_done
                store.save()
        except Exception as exc:
            print(f"  [warn] Email generation failed for {name}: {exc}")

    # Sync email fields back to main prospect list
    email_map = store.data.get("emails", {})
    for p in store.prospects:
        cname = p["company_name"]
        if cname in email_map:
            p["email_subject"] = email_map[cname]["subject"]
            p["email_body"] = email_map[cname]["body"]

    store.data["step"] = "output"
    store.save()


# ---------------------------------------------------------------------------
# Output generation
# ---------------------------------------------------------------------------


CSV_FIELDS = [
    "rank",
    "company_name",
    "website",
    "industry",
    "headquarters",
    "employee_count",
    "why_networking",
    "decision_maker",
    "pain_point_1",
    "pain_point_2",
    "pain_point_3",
    "pronto_product",
    "tech_stack",
    "best_outreach_timing",
    "fit_score",
    "score_reason",
    "email_subject",
    "email_body",
]


def ranked_prospects(prospects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(prospects, key=lambda p: p.get("fit_score", 0), reverse=True)


def save_csv(prospects: list[dict[str, Any]]) -> None:
    ranked = ranked_prospects(prospects)
    with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for rank, p in enumerate(ranked, start=1):
            pains = p.get("pain_points", []) + ["", "", ""]
            writer.writerow(
                {
                    "rank": rank,
                    "company_name": p.get("company_name", ""),
                    "website": p.get("website", ""),
                    "industry": p.get("industry", ""),
                    "headquarters": p.get("headquarters", ""),
                    "employee_count": p.get("employee_count", ""),
                    "why_networking": p.get("why_networking", ""),
                    "decision_maker": p.get("decision_maker", ""),
                    "pain_point_1": pains[0],
                    "pain_point_2": pains[1],
                    "pain_point_3": pains[2],
                    "pronto_product": p.get("pronto_product", ""),
                    "tech_stack": p.get("tech_stack", ""),
                    "best_outreach_timing": p.get("best_outreach_timing", ""),
                    "fit_score": p.get("fit_score", 0),
                    "score_reason": p.get("score_reason", ""),
                    "email_subject": p.get("email_subject", ""),
                    "email_body": p.get("email_body", ""),
                }
            )
    print(f"  Saved CSV → {CSV_FILE}")


def save_emails_txt(prospects: list[dict[str, Any]]) -> None:
    top = ranked_prospects(prospects)[:TOP_EMAIL_COUNT]
    lines = [
        "PRONTO NETWORKS — TOP 10 COLD EMAILS",
        f"Generated: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}",
        "=" * 60,
        "",
    ]
    for i, p in enumerate(top, start=1):
        lines.extend(
            [
                f"--- #{i} {p.get('company_name', '')} (Fit: {p.get('fit_score', 0)}/10) ---",
                f"To: {p.get('decision_maker', 'Decision Maker')}",
                f"Subject: {p.get('email_subject', '')}",
                "",
                p.get("email_body", ""),
                "",
                "=" * 60,
                "",
            ]
        )
    EMAILS_FILE.write_text("\n".join(lines), encoding="utf-8")
    print(f"  Saved emails → {EMAILS_FILE}")


def _industry_badge_class(industry: str) -> str:
    key = industry.lower()
    mapping = {
        "hospitality": "badge-hospitality",
        "retail": "badge-retail",
        "healthcare": "badge-healthcare",
        "pos": "badge-pos",
        "kiosk": "badge-kiosk",
        "smart": "badge-smart",
    }
    for prefix, cls in mapping.items():
        if prefix in key:
            return cls
    return "badge-default"


def _score_bar_color(score: int) -> str:
    if score >= 8:
        return "bg-emerald-500"
    if score >= 5:
        return "bg-amber-400"
    return "bg-red-500"


def generate_dashboard(prospects: list[dict[str, Any]]) -> None:
    """Build self-contained HTML dashboard with embedded prospect data."""
    ranked = ranked_prospects(prospects)
    top10 = ranked[:TOP_EMAIL_COUNT]
    generated = datetime.now().strftime("%B %d, %Y")
    avg_score = round(sum(p.get("fit_score", 0) for p in prospects) / max(len(prospects), 1), 1)

    industries = [p.get("industry", "Other") for p in prospects]
    top_industry = max(set(industries), key=industries.count) if industries else "N/A"
    emails_count = sum(1 for p in top10 if p.get("email_body"))

    # Embed data for client-side sort/filter
    table_json = json.dumps(
        [
            {
                "rank": i,
                "company_name": p.get("company_name", ""),
                "website": p.get("website", ""),
                "industry": p.get("industry", ""),
                "employee_count": p.get("employee_count", ""),
                "fit_score": p.get("fit_score", 0),
                "score_reason": p.get("score_reason", ""),
                "decision_maker": p.get("decision_maker", ""),
                "pronto_product": p.get("pronto_product", ""),
            }
            for i, p in enumerate(ranked, start=1)
        ]
    )

    top_cards_html = ""
    for i, p in enumerate(top10, start=1):
        pains = p.get("pain_points", [])
        pain_lis = "".join(f"<li>{html.escape(str(pt))}</li>" for pt in pains)
        email_block = html.escape(p.get("email_body", ""))
        subject = html.escape(p.get("email_subject", ""))
        top_cards_html += f"""
        <div class="card rounded-xl border border-slate-700/80 bg-slate-900/60 p-6 shadow-lg">
          <div class="flex flex-wrap items-start justify-between gap-3 mb-4">
            <div>
              <span class="text-orange-400 font-bold text-sm">#{i} · Score {p.get('fit_score', 0)}/10</span>
              <h3 class="text-xl font-semibold text-white mt-1">{html.escape(p.get('company_name', ''))}</h3>
              <p class="text-slate-400 text-sm">{html.escape(p.get('industry', ''))} · {html.escape(p.get('headquarters', ''))}</p>
            </div>
            <a href="{html.escape(p.get('website', '#'))}" target="_blank" rel="noopener"
               class="text-sm text-orange-400 hover:text-orange-300">Visit site →</a>
          </div>
          <div class="grid md:grid-cols-2 gap-4 text-sm text-slate-300 mb-4">
            <div><span class="text-slate-500">Target:</span> {html.escape(p.get('decision_maker', ''))}</div>
            <div><span class="text-slate-500">Product fit:</span> <span class="text-orange-300">{html.escape(p.get('pronto_product', ''))}</span></div>
            <div><span class="text-slate-500">Employees:</span> {html.escape(p.get('employee_count', ''))}</div>
            <div><span class="text-slate-500">Best timing:</span> {html.escape(p.get('best_outreach_timing', ''))}</div>
            <div class="md:col-span-2"><span class="text-slate-500">Tech stack:</span> {html.escape(p.get('tech_stack', ''))}</div>
            <div class="md:col-span-2"><span class="text-slate-500">Why networking:</span> {html.escape(p.get('why_networking', ''))}</div>
          </div>
          <p class="text-xs text-slate-500 uppercase tracking-wide mb-2">Pain points</p>
          <ul class="list-disc list-inside text-slate-300 text-sm mb-5 space-y-1">{pain_lis}</ul>
          <p class="text-xs text-slate-500 uppercase tracking-wide mb-2">Cold email</p>
          <p class="text-sm text-orange-200 mb-2"><strong>Subject:</strong> {subject}</p>
          <div class="relative">
            <textarea readonly id="email-{i}"
              class="w-full h-36 rounded-lg bg-slate-950 border border-slate-700 text-slate-200 text-sm p-4 font-mono resize-y">{email_block}</textarea>
            <button onclick="copyEmail('email-{i}', this)"
              class="absolute top-2 right-2 px-3 py-1 text-xs rounded bg-orange-500 hover:bg-orange-400 text-slate-900 font-semibold">
              Copy
            </button>
          </div>
        </div>"""

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Pronto Networks — GTM Intelligence</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <style>
    body {{ background: #0a1628; }}
    .badge-hospitality {{ background:#1e3a5f; color:#93c5fd; }}
    .badge-retail {{ background:#4c1d95; color:#c4b5fd; }}
    .badge-healthcare {{ background:#14532d; color:#86efac; }}
    .badge-pos {{ background:#7c2d12; color:#fdba74; }}
    .badge-kiosk {{ background:#134e4a; color:#5eead4; }}
    .badge-smart {{ background:#164e63; color:#67e8f9; }}
    .badge-default {{ background:#334155; color:#cbd5e1; }}
    th.sortable {{ cursor: pointer; user-select: none; }}
    th.sortable:hover {{ color: #fb923c; }}
  </style>
</head>
<body class="text-slate-200 min-h-screen">
  <header class="border-b border-slate-800 bg-[#0d1f3c]">
    <div class="max-w-7xl mx-auto px-4 py-8 sm:px-6">
      <div class="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4">
        <div>
          <h1 class="text-3xl font-bold text-white tracking-tight">
            Pronto <span class="text-orange-500">Networks</span>
          </h1>
          <p class="text-slate-400 mt-1">Enterprise WiFi · LTE · 5G · HaLow for connected businesses</p>
        </div>
        <p class="text-sm text-slate-400">GTM Intelligence Report — Generated {generated}</p>
      </div>
      <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mt-8">
        <div class="rounded-lg bg-slate-900/80 border border-slate-700 p-4">
          <p class="text-xs text-slate-500 uppercase">Prospects found</p>
          <p class="text-2xl font-bold text-white">{len(prospects)}</p>
        </div>
        <div class="rounded-lg bg-slate-900/80 border border-slate-700 p-4">
          <p class="text-xs text-slate-500 uppercase">Average fit score</p>
          <p class="text-2xl font-bold text-orange-400">{avg_score}</p>
        </div>
        <div class="rounded-lg bg-slate-900/80 border border-slate-700 p-4">
          <p class="text-xs text-slate-500 uppercase">Top industry</p>
          <p class="text-lg font-semibold text-white truncate">{html.escape(top_industry)}</p>
        </div>
        <div class="rounded-lg bg-slate-900/80 border border-slate-700 p-4">
          <p class="text-xs text-slate-500 uppercase">Emails generated</p>
          <p class="text-2xl font-bold text-white">{emails_count}</p>
        </div>
      </div>
    </div>
  </header>

  <main class="max-w-7xl mx-auto px-4 py-10 sm:px-6">
    <section class="mb-12">
      <div class="flex flex-col sm:flex-row sm:items-center gap-4 mb-6">
        <h2 class="text-xl font-semibold text-white">All prospects</h2>
        <div class="flex flex-wrap gap-3 sm:ml-auto">
          <input id="search" type="search" placeholder="Search company..."
            class="rounded-lg bg-slate-900 border border-slate-700 px-4 py-2 text-sm focus:outline-none focus:border-orange-500 w-full sm:w-48" />
          <select id="industry-filter"
            class="rounded-lg bg-slate-900 border border-slate-700 px-4 py-2 text-sm focus:outline-none focus:border-orange-500">
            <option value="">All industries</option>
          </select>
        </div>
      </div>
      <div class="overflow-x-auto rounded-xl border border-slate-700/80">
        <table class="w-full text-sm text-left" id="leads-table">
          <thead class="bg-[#0d1f3c] text-slate-400 uppercase text-xs">
            <tr>
              <th class="px-4 py-3 sortable" data-sort="rank">Rank</th>
              <th class="px-4 py-3 sortable" data-sort="company_name">Company</th>
              <th class="px-4 py-3 sortable" data-sort="industry">Industry</th>
              <th class="px-4 py-3 sortable" data-sort="employee_count">Employees</th>
              <th class="px-4 py-3 sortable" data-sort="fit_score">Fit</th>
              <th class="px-4 py-3">Score reason</th>
              <th class="px-4 py-3">Decision maker</th>
              <th class="px-4 py-3 sortable" data-sort="pronto_product">Product</th>
            </tr>
          </thead>
          <tbody id="table-body" class="divide-y divide-slate-800 bg-slate-900/40"></tbody>
        </table>
      </div>
    </section>

    <section>
      <h2 class="text-xl font-semibold text-white mb-6">Top 10 — Ready to send</h2>
      <div class="grid lg:grid-cols-2 gap-6">
        {top_cards_html}
      </div>
    </section>
  </main>

  <footer class="border-t border-slate-800 mt-16 py-6 text-center text-slate-500 text-sm">
    Pronto Networks GTM Intelligence · Powered by Claude
  </footer>

  <script>
    const leads = {table_json};

    function badgeClass(industry) {{
      const k = (industry || '').toLowerCase();
      if (k.includes('hospitality')) return 'badge-hospitality';
      if (k.includes('retail')) return 'badge-retail';
      if (k.includes('healthcare') || k.includes('health')) return 'badge-healthcare';
      if (k.includes('pos')) return 'badge-pos';
      if (k.includes('kiosk')) return 'badge-kiosk';
      if (k.includes('smart')) return 'badge-smart';
      return 'badge-default';
    }}

    function scoreColor(score) {{
      if (score >= 8) return 'bg-emerald-500';
      if (score >= 5) return 'bg-amber-400';
      return 'bg-red-500';
    }}

    function renderTable(data) {{
      const tbody = document.getElementById('table-body');
      tbody.innerHTML = data.map(row => `
        <tr class="hover:bg-slate-800/50">
          <td class="px-4 py-3 font-mono text-orange-400">${{row.rank}}</td>
          <td class="px-4 py-3 font-medium text-white">
            <a href="${{row.website}}" target="_blank" rel="noopener" class="hover:text-orange-400">${{row.company_name}}</a>
          </td>
          <td class="px-4 py-3">
            <span class="px-2 py-1 rounded text-xs font-medium ${{badgeClass(row.industry)}}">${{row.industry}}</span>
          </td>
          <td class="px-4 py-3 text-slate-300">${{row.employee_count}}</td>
          <td class="px-4 py-3">
            <div class="flex items-center gap-2 min-w-[100px]">
              <div class="flex-1 h-2 bg-slate-700 rounded-full overflow-hidden">
                <div class="h-full ${{scoreColor(row.fit_score)}}" style="width:${{row.fit_score * 10}}%"></div>
              </div>
              <span class="text-xs font-bold w-6">${{row.fit_score}}</span>
            </div>
          </td>
          <td class="px-4 py-3 text-slate-400 max-w-xs">${{row.score_reason}}</td>
          <td class="px-4 py-3 text-slate-300">${{row.decision_maker}}</td>
          <td class="px-4 py-3 text-orange-300">${{row.pronto_product}}</td>
        </tr>
      `).join('');
    }}

    // Industry filter options
    const industries = [...new Set(leads.map(l => l.industry).filter(Boolean))].sort();
    const sel = document.getElementById('industry-filter');
    industries.forEach(ind => {{
      const o = document.createElement('option');
      o.value = ind; o.textContent = ind;
      sel.appendChild(o);
    }});

    let filtered = [...leads];
    let sortKey = 'rank';
    let sortAsc = true;

    function applyFilters() {{
      const q = document.getElementById('search').value.toLowerCase();
      const ind = sel.value;
      filtered = leads.filter(l =>
        l.company_name.toLowerCase().includes(q) &&
        (!ind || l.industry === ind)
      );
      sortData();
    }}

    function sortData() {{
      filtered.sort((a, b) => {{
        let va = a[sortKey], vb = b[sortKey];
        if (sortKey === 'fit_score' || sortKey === 'rank') {{
          va = Number(va); vb = Number(vb);
        }} else {{
          va = String(va).toLowerCase(); vb = String(vb).toLowerCase();
        }}
        if (va < vb) return sortAsc ? -1 : 1;
        if (va > vb) return sortAsc ? 1 : -1;
        return 0;
      }});
      renderTable(filtered);
    }}

    document.getElementById('search').addEventListener('input', applyFilters);
    sel.addEventListener('change', applyFilters);
    document.querySelectorAll('th.sortable').forEach(th => {{
      th.addEventListener('click', () => {{
        const key = th.dataset.sort;
        if (sortKey === key) sortAsc = !sortAsc;
        else {{ sortKey = key; sortAsc = true; }}
        sortData();
      }});
    }});

    function copyEmail(id, btn) {{
      const ta = document.getElementById(id);
      ta.select();
      navigator.clipboard.writeText(ta.value).then(() => {{
        const orig = btn.textContent;
        btn.textContent = 'Copied!';
        setTimeout(() => btn.textContent = orig, 2000);
      }});
    }}

    applyFilters();
  </script>
</body>
</html>"""

    DASHBOARD_FILE.write_text(page, encoding="utf-8")
    print(f"  Saved dashboard → {DASHBOARD_FILE}")


def print_terminal_summary(prospects: list[dict[str, Any]]) -> None:
    """Print ASCII summary table to terminal."""
    ranked = ranked_prospects(prospects)
    print("\n" + "=" * 90)
    print("  PRONTO NETWORKS — GTM INTELLIGENCE SUMMARY")
    print("=" * 90)
    print(f"  {'Rank':<5} {'Company':<28} {'Industry':<18} {'Score':<6} {'Product':<8}")
    print("-" * 90)
    for i, p in enumerate(ranked, start=1):
        name = (p.get("company_name", "")[:26] + "..") if len(p.get("company_name", "")) > 28 else p.get("company_name", "")
        ind = (p.get("industry", "")[:16] + "..") if len(p.get("industry", "")) > 18 else p.get("industry", "")
        print(
            f"  {i:<5} {name:<28} {ind:<18} {p.get('fit_score', 0):<6} {p.get('pronto_product', '')[:8]}"
        )
    avg = sum(p.get("fit_score", 0) for p in prospects) / max(len(prospects), 1)
    print("-" * 90)
    print(f"  Total: {len(prospects)} prospects | Avg score: {avg:.1f}/10 | Top 10 emails in output/")
    print("=" * 90 + "\n")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def main() -> None:
    print("\n" + "=" * 60)
    print("  PRONTO NETWORKS — GTM LEAD INTELLIGENCE SYSTEM")
    print("  Model:", MODEL)
    print("=" * 60 + "\n")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if PROGRESS_FILE.exists():
        PROGRESS_FILE.unlink()
        print("  Cleared previous progress.json — starting fresh.\n")
    client = get_client()
    store = ProgressStore(PROGRESS_FILE)

    step = store.data.get("step", "prospects")
    print(f"Resume state: step={step}, prospects={len(store.prospects)}\n")

    # Step 1 — Prospect generation
    if step == "prospects" or len(store.prospects) < TARGET_PROSPECT_COUNT:
        prospects = step1_find_prospects(client, store)
    else:
        prospects = store.prospects

    # Step 2 — Enrichment
    if store.data.get("step") in ("enrichment", "prospects") or len(store.data.get("enriched_indices", [])) < len(prospects):
        step2_enrich(client, store)

    # Step 3 — Scoring
    if store.data.get("step") in ("scoring", "enrichment") or len(store.data.get("scored_indices", [])) < len(prospects):
        step3_score(client, store)

    # Step 4 — Emails for top 10
    step4_emails(client, store)
    prospects = store.prospects

    # Step 5 & 6 — Outputs
    print("\n[output] Writing files...")
    save_csv(prospects)
    save_emails_txt(prospects)
    generate_dashboard(prospects)

    store.data["completed"] = True
    store.data["step"] = "complete"
    store.save()

    print_terminal_summary(prospects)
    print("Done! Open output/pronto_leads_dashboard.html in your browser.\n")


if __name__ == "__main__":
    main()
