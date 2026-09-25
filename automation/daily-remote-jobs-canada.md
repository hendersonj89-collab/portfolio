# Daily remote jobs (Canada) digest

A scheduled Claude Code routine that runs every morning, pulls remote jobs in
Canada posted in the last 48 hours from structured feeds, ranks them against my
profile, and emails a short digest.

- **Schedule:** daily at 14:00 UTC (7 am Pacific / 8 am Mountain / 10 am Eastern)
- **Runs as:** a fresh Claude Code session per day (no repo changes, no connectors)
- **Sources:** `jobs_digest.py` (this folder) fetches LinkedIn's guest job search
  with the remote-in-Canada filter, the CPA Ontario Career Centre RSS feed, and
  Job Bank Canada sorted by date. Stdlib only, no API keys. The routine curls it
  from this branch on GitHub, so edits here take effect on the next run.
- **Needs:** the environment's network access set to full internet (or
  www.linkedin.com, mycareer.cpaontario.ca, www.jobbank.gc.ca and
  raw.githubusercontent.com allowlisted). Web search alone returns only stale
  aggregator pages.
- **Delivery:** push notification + email with the session summary; open the
  session for the full list
- **Manage it:** claude.ai/code → Routines (pause, edit schedule, edit prompt, delete)

## What it looks for

Profile: CPA, CA with accounting, financial reporting and corporate tax
background; CPA program facilitator and case marker; learning ML on financial
data.

Target roles, in priority order:

1. Senior Accountant, Financial Reporting Manager, Controller / Assistant Controller
2. Corporate tax senior/manager, tax analyst
3. FP&A, Financial Analyst, Finance Business Partner
4. Finance data analyst, financial systems, fintech roles open to CPAs
5. CPA education: facilitator, instructor, marker, curriculum or exam development

Hard filters: fully remote within Canada only (no hybrid, no US-only), posted
in the last 1 to 3 days (never older than 7), no agency duplicates or
commission-only listings.

## Output format

Top 10 max, ranked into **Strong fit** and **Worth a look**. Each entry is one
line (title, company, remote status, salary, posted date, apply link) plus one
"why it fits" line. Ends with a count of postings reviewed.

## Tuning

Edit the keyword lists and exclusion regexes at the top of `jobs_digest.py` to
change what gets fetched. Edit the routine prompt to change ranking priorities
or add salary floors. Run locally with `python3 jobs_digest.py --hours 48`. Change the cron expression to shift the
time or limit to weekdays (`0 14 * * 1-5`).
