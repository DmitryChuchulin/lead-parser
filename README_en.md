# Lead Parser

Daily parser for commercial IT development tenders.  
Goal: lead generation — find a tender → evaluate → submit a proposal.

---

## What it does

- Parses tenders from **workspace.ru** via RSS (`/tenders/rss/`)
- Filters by category: website development, mobile apps, CRM/software
- Filters by date (not older than 2 days)
- Appends results to Google Sheets without duplicates
- Sends a detailed Telegram notification broken down by category

---

## File structure

```
lead-parser/
├── workspace_parser.py    # workspace.ru tender parser
├── sheets_writer.py       # Google Sheets writer
├── run.sh                 # Shell script with Telegram notification
├── requirements.txt       # Python dependencies
├── .env                   # Secrets (not in git)
└── .github/
    └── workflows/
        └── daily_parse.yml  # GitHub Actions (disabled — workspace.ru blocks their IPs)
```

---

## Why not GitHub Actions

workspace.ru returns **HTTP 471** for requests from GitHub Actions IP addresses (cloud server blocking). The parser runs on a netangels VPS whose IP is not blocked.

---

## How the workspace parser works

1. Makes a single HTTP request to RSS `https://workspace.ru/tenders/rss/`
2. Gets the latest 10 tenders with fields: title, link, date, description
3. Parses from description (HTML in CDATA): organizer, budget, deadline, required service
4. Filters by keywords in the "Required service" field:
   - `apps-development`: мобильн, приложен
   - `crm`: crm, erp
   - `web-development`: сайт, разработка
5. Filters by date
6. Writes to Google Sheets, sends Telegram notification

Run time: ~5-10 seconds.

---

## Google Sheets

| Spreadsheet | ID | Sheet |
|---|---|---|
| Lead Parser | `1NE1KD9YQ2lzJGKN5-c7Z3Ug9PFAEF7-4yomsMww9aPI` | `Workspace` |

Columns: `Title | Organizer | Budget | Deadline | URL | Platform | Published Date`

---

## Telegram notification format

**Success:**
```
✅ workspace.ru
🌐 Websites: 2
📱 Mobile: 0
⚙️ CRM: 1
```

**Error:**
```
❌ workspace.ru: error!
```

---

## Environment variables (.env)

```env
GOOGLE_SHEET_ID=1NE1KD9YQ2lzJGKN5-c7Z3Ug9PFAEF7-4yomsMww9aPI
GOOGLE_CREDENTIALS_JSON=/opt/service-account.json
TELEGRAM_BOT_TOKEN=<@ElgrowsBot token>
TELEGRAM_CHAT_ID=<Dmitry's chat_id>
```

---

## Manual run

```bash
# Via shell script (with Telegram notification)
/opt/lead-parser/run.sh

# Direct run (no notification)
cd /opt/lead-parser
set -a && source .env && set +a
.venv/bin/python workspace_parser.py --sheets

# Test run without writing to Sheets
.venv/bin/python workspace_parser.py
```

---

## Server schedule (cron)

Server: `213.189.220.225` (netangels VPS)

```
0 6  * * *   Workspace parser   → 09:00 MSK
0 11 * * *   Workspace parser   → 14:00 MSK
0 15 * * *   Workspace parser   → 18:00 MSK
```

View cron: `crontab -l`  
Edit cron: `crontab -e`

---

## Infrastructure

- **Server:** netangels VPS, Debian 12, 8GB RAM
- **Python:** 3.11, venv at `/opt/lead-parser/.venv/`
- **Google:** Service Account `tenchat-parser@tenchat-parser.iam.gserviceaccount.com`
- **Credentials file:** `/opt/service-account.json`
- **Telegram:** bot @ElgrowsBot

---

## Dependencies

```
requests>=2.31
beautifulsoup4>=4.12
feedparser>=6.0.0
gspread>=6.0.0
google-auth>=2.0.0
```

---

## Platforms planned

- **bizdaar.com** — commercial tenders (account registered, need to find API via DevTools after login)
- tender.pro
- b2b-center.ru

**Not parsing:** government procurement (44-FZ, 223-FZ) — separate process requiring digital signatures.

---

## Known limitations

- workspace.ru RSS only returns the latest 10 tenders
- Organizer in RSS = type ("legal entity"), not company name — name is hidden until proposal submission
