# Racing App — Knowledge Transfer (KT)

---

## Project Overview

A horse/harness racing companion app that:
- Scrapes live odds & results from Ladbrokes (AU)
- Tracks jockey/driver challenges with live point standings
- Provides AI-powered price comparisons
- Tracks bets and meeting history

**Stack:** Django (BE) + React (FE) + SQLite

---

## Backend

### Entry Point
```
backend/
├── manage.py               # Django management
├── racing/
│   ├── models.py           # All DB models
│   ├── views.py            # All API endpoints
│   ├── urls.py             # URL routing
│   ├── serializers.py      # DRF serializers
│   ├── scraper.py          # Main Ladbrokes scraper (Playwright)
│   ├── auto_results.py     # Auto race result fetcher + background runner
│   ├── live_tracker.py     # In-memory live tracker logic
│   ├── results_fetcher.py  # GitHub Actions results fetcher
│   └── pointsbet_fix.py    # Odds fix utility
```

### Key Models (`models.py`)

| Model | Purpose |
|-------|---------|
| `Meeting` | Stores scraped meeting data (jockeys, odds, AI prices) |
| `Bet` | User's placed bets with result tracking |
| `PointsLedger` | Per-race points (P1=3pts, P2=2pts, P3=1pt) |
| `LiveTrackerState` | Persistent live tracker per meeting (DB-backed) |
| `AutoFetchConfig` | Config for background auto-fetch per meeting |
| `OddsHistory` | Historical odds snapshots |

### API Endpoints (`urls.py`)

#### Core
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/ai-prices/` | GET | AI price comparisons |
| `/api/jockey-challenges/` | GET | Live jockey challenge data |
| `/api/driver-challenges/` | GET | Live driver challenge data |
| `/api/refresh/` | POST | Trigger manual scrape |
| `/api/receive-scrape/` | POST | Receive data from GitHub Actions scraper |

#### Bets
| Endpoint | Description |
|----------|-------------|
| `/api/bets/` | List all bets |
| `/api/bets/add/` | Add new bet |
| `/api/bets/update/` | Mark bet result (win/lose) |
| `/api/bets/delete/` | Delete bet |
| `/api/bets/summary/` | P&L summary |

#### Live Tracker (In-Memory)
| Endpoint | Description |
|----------|-------------|
| `/api/live-tracker/init/` | Start a new tracker |
| `/api/live-tracker/update/` | Record race result |
| `/api/live-tracker/<meeting>/` | Get tracker state |
| `/api/live-tracker/auto-update/` | Auto-scrape & update |

#### Auto Fetch
| Endpoint | Description |
|----------|-------------|
| `/api/auto-fetch/start/` | Start background fetcher |
| `/api/auto-fetch/stop/` | Stop background fetcher |
| `/api/auto-fetch/status/` | Check runner status |
| `/api/auto-fetch/trigger/` | Manual trigger for one meeting |

#### Points Ledger
| Endpoint | Description |
|----------|-------------|
| `/api/points-ledger/` | View all points |
| `/api/points-ledger/record/` | Manually record race points |

#### v2 Persistent Live Tracker (DB-backed)
| Endpoint | Description |
|----------|-------------|
| `/api/v2/live-tracker/init/` | Init persistent tracker |
| `/api/v2/live-tracker/<meeting>/` | Get persistent tracker |

---

### Auto Results System (`auto_results.py`)

**Flow:**
```
AutoFetchRunner (background thread)
    → polls AutoFetchConfig every 30s
    → calls fetch_and_update_meeting()
        → AutoResultsFetcher.fetch_results()  (Playwright scrape)
        → match_jockey()                       (fuzzy name match)
        → PointsLedger.update_or_create()     (save points)
        → LiveTrackerState.update()            (update live standings)
        → AutoFetchConfig.last_race_fetched++ (track progress)
```

**Points System:**
- P1 = 3 pts, P2 = 2 pts, P3 = 1 pt
- Dead heat: total points shared equally between tied jockeys

**Name Matching (`match_jockey`):**
1. Exact match
2. Last name match (if >2 chars)
3. Partial substring match

---

### Scraping Architecture

Two scraping methods:
1. **Playwright (primary)** — `scraper.py` / `auto_results.py` — headless Chromium, scrapes Ladbrokes AU
2. **GitHub Actions (fallback)** — `results_fetcher.py` — external cron job sends data via `/api/receive-scrape/`

Playwright may not be available in all environments — graceful fallback to mock data.

---

## Frontend

### Structure
```
frontend/src/
├── App.js                  # Root — tab routing, global state
├── services/api.js         # All API calls (Axios)
├── components/
│   ├── Header.js           # Top nav + refresh button
│   ├── PricesTab.js        # AI prices view
│   ├── LiveTracker.jsx     # Live jockey challenge tracker
│   ├── BetTracker.js       # Bet management
│   ├── CalendarTab.js      # Meeting calendar
│   ├── HistoryTab.js       # Past meetings
│   ├── MeetingCard.js      # Single meeting display
│   ├── CountryFilter.js    # Filter by country/region
│   ├── MarginSlider.js     # Odds margin adjustment
│   ├── StatCard.js         # Stats display widget
│   └── LoadingShimmer.js   # Skeleton loader
```

### Tab Structure (`App.js`)
| Tab | Component | Description |
|-----|-----------|-------------|
| Prices | `PricesTab` | AI price comparisons + odds |
| Live | `LiveTracker` | Real-time jockey challenge tracker |
| Bets | `BetTracker` | Bet slip & history |
| Calendar | `CalendarTab` | Upcoming/past meetings |
| History | `HistoryTab` | Meeting results archive |

### API Service (`services/api.js`)
Single file for all backend calls. Base URL configured here.
All components import from this file — never call `fetch`/`axios` directly in components.

---

## Data Flow

```
Ladbrokes AU website
    ↓ (Playwright scrape)
scraper.py / auto_results.py
    ↓
Django models (SQLite)
    ↓
DRF views + serializers
    ↓ (REST API)
api.js (Axios)
    ↓
React components
```

---

## Running Locally

```bash
# Backend
cd backend
source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver

# Frontend
cd frontend
npm install
npm start
```

Playwright browsers (for scraping):
```bash
playwright install chromium
```

---

## Environment Notes

- **DB:** SQLite (`db.sqlite3`) — no external DB needed
- **Scraping:** Requires Playwright + Chromium OR GitHub Actions runner
- **Hosting:** `passenger_wsgi.py` present → cPanel/Passenger deployment
- **CORS:** Configured in Django settings for FE dev server

---

## Known Gotchas

1. **Playwright on server** — May not work on shared hosting; GitHub Actions fallback exists
2. **Name matching** — Jockey names from Ladbrokes can have suffixes like `(a3)` — stripped before matching
3. **Dead heats** — Points split; fractional points possible (e.g. 2.5)
4. **AutoFetchRunner** — Global singleton; only one instance per Django process
5. **In-memory tracker** — Resets on server restart; use v2 DB-backed endpoints for persistence
