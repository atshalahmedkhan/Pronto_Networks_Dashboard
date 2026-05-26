# Pronto Networks Dashboard

AI-powered GTM Lead Intelligence System for Pronto Networks. Uses the Claude API to find, enrich, score, and generate personalized cold emails for ICP-fit prospects in hospitality, retail, healthcare, and POS.

## Quick start

```bash
cd pronto_gtm
pip install -r requirements.txt
# Add ANTHROPIC_API_KEY to .env (see .env.example)
python pronto_gtm_system.py
```

Open the dashboard:

```bash
cd output
python -m http.server 8080
```

Then visit `http://localhost:8080`

## Outputs

- `output/index.html` — Interactive lead dashboard
- `output/pronto_leads.csv` — Full prospect data
- `output/pronto_emails.txt` — Top outreach emails
- `output/pronto_leads_dashboard.html` — Pipeline-generated report
