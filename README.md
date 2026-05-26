# Pronto Networks — GTM Lead Intelligence System

**Built by Atshal Ahmed Khan** | [atshalah@buffalo.edu](mailto:atshalah@buffalo.edu) | [github.com/atshalahmedkhan](https://github.com/atshalahmedkhan)

---

## What This Is

A fully automated GTM (Go-To-Market) lead intelligence pipeline built specifically for **Pronto Networks** — a B2B WiFi/LTE/5G networking company serving hospitality, retail, healthcare, and POS industries.

Instead of sending a cover letter, I built the tool.

---

## What It Does

### Pipeline Overview
```
Daily Trigger → Fetch ICP Companies → Enrich with Claude AI → Score & Rank Leads → Generate Cold Emails → Export Dashboard
```

### Step by Step

| Step | What Happens |
|------|-------------|
| **1. Prospect Generation** | Claude AI identifies 25 real companies matching Pronto's ICP across hospitality, retail, healthcare, and POS |
| **2. Deep Enrichment** | Each company enriched with decision maker title, top pain points, and best-fit Pronto product line |
| **3. ICP Scoring** | Every prospect scored 1–10 based on industry match, company size, networking needs, and similarity to existing Pronto customers |
| **4. Email Generation** | Personalized cold emails written for the top 10 prospects — referencing specific pain points and Pronto social proof |
| **5. Dashboard Export** | Interactive HTML dashboard with filters, search, score bars, and one-click copy emails |

---

## Tech Stack

- **Claude API** (`claude-haiku-4-5`) — prospect generation, enrichment, scoring, email writing
- **Python** — pipeline orchestration, batch processing, rate limit handling
- **n8n** — visual workflow automation (see workflow screenshot below)
- **HTML/CSS/JavaScript + GSAP** — animated interactive dashboard
- **python-dotenv** — environment variable management

---

## Output

### Dashboard
An interactive dashboard showing all 25 prospects with:
- Fit score visualized as color-coded progress bars (green = strong fit)
- Industry filters and live search
- Decision maker targets and pain points
- One-click copyable cold emails for top 10 prospects

### Files Generated
```
output/
  pronto_leads_dashboard.html   # Interactive dashboard
  pronto_leads.csv              # All 25 prospects with enrichment data
  pronto_emails.txt             # Top 10 cold emails ready to send
```

---

## n8n Workflow

The same pipeline is also built as a visual n8n automation workflow:

```
Daily Trigger → Fetch ICP Companies → Enrich with Claude AI → Score & Rank Leads → Generate Cold Emails → Export Dashboard
```

This allows non-technical team members to trigger, monitor, and modify the pipeline without touching code.

---

## Setup

```bash
# Clone the repo
git clone https://github.com/atshalahmedkhan/pronto-gtm
cd pronto-gtm

# Install dependencies
pip install anthropic python-dotenv

# Add your API key
echo "ANTHROPIC_API_KEY=your_key_here" > .env

# Run the pipeline
python pronto_gtm_system.py
```

### View the Dashboard
```bash
cd output
python -m http.server 8080
# Open http://localhost:8080 in Chrome
```

---

## Sample Results

```
Rank  Company                   Industry          Score
----  -------                   --------          -----
1     Shift4 Payments           POS Systems       9/10
2     TouchBistro               Hospitality POS   9/10
3     Clover (Fiserv)           POS Systems       9/10
4     Heartland Payment Systems POS Systems       9/10
5     Micros Systems (Oracle)   Hospitality POS   9/10
...
25 prospects | Avg score: 7.7/10 | 10 emails generated
```

---

## Why I Built This

Pronto's job post mentioned Claude, n8n, and GTM automation. Instead of describing what I could build, I built it — using their exact stack, for their exact use case, with their actual ICP.

This pipeline could run daily to continuously surface new prospects, score them, and put personalized outreach in a sales rep's hands before their morning standup.

---

*Built in one night · May 2026 · Powered by Claude AI*
