# Trader Joe's Price Tracking (Python)

A Python port of [cmoog/traderjoes](https://github.com/cmoog/traderjoes). The original project is a Go/Nix implementation that powers [traderjoesprices.com](https://traderjoesprices.com) — this repo is just a Python rewrite of the price fetching and product search functionality.

## Features

- Search products by name
- Lookup by SKU
- Multi-store support
- SQLite storage for price tracking and history
- Concurrent fetching
- Smart cookie management with automatic Selenium fallback

## Installation (uv)

```bash
uv sync
```

This installs everything (CLI, Selenium webdriver fallback, Anthropic + Braintrust recipe agent, dotenv). Selenium enables automatic cookie retrieval — no manual cookie updates needed.

## Website

A small Vite site now lives in `web/` to explain the current application and its
main surfaces.

Install and run it with:

```bash
cd web
npm install
npm run dev
```

Build a production bundle with:

```bash
cd web
npm run build
```

## Usage

### Search for Products

```bash
uv run traderjoes search "miso crunch"
uv run traderjoes search "pasta sauce"
```

### Lookup by SKU

```bash
uv run traderjoes lookup 073814 077316 060411
```

### Fetch All Store Data

```bash
# Fetch from default stores (Chicago, LA, NYC, Austin)
uv run traderjoes fetch

# Fetch from specific stores
uv run traderjoes fetch --stores 226 701 546
```

### Recipe Agent TUI

This repo now includes a Claude Agent SDK-powered recipe assistant that can
search the Trader Joe's catalog while generating recipe ideas.

All recipe + Selenium dependencies are installed automatically by `uv sync`.

Set your API key:

```bash
export ANTHROPIC_API_KEY="your_api_key"
export BRAINTRUST_API_KEY="your_braintrust_api_key"
export BRAINTRUST_PROJECT="Trader Joes Recipe Agent"  # optional override
```

Launch the TUI:

```bash
uv run recipe-agent-tui
```

Optional flags:

```bash
uv run recipe-agent-tui --store 226 --model claude-haiku-4-5-20251001
```

### Twilio SMS Webhook

This repo now also exposes a simple Twilio SMS webhook for the Trader Joe's
recipe agent.

Install deps:

```bash
uv sync
```

Required env vars:

```bash
export ANTHROPIC_API_KEY="your_api_key"
export TWILIO_AUTH_TOKEN="your_twilio_auth_token"
```

Optional env vars:

```bash
export ANTHROPIC_MODEL="claude-haiku-4-5-20251001"
export DEFAULT_STORE_CODE="226"
export TWILIO_WEBHOOK_URL="https://your-deployment.vercel.app/api/twilio/sms"
```

Run locally:

```bash
uv run uvicorn app:app --reload
```

Webhook endpoint:

```text
POST /api/twilio/sms
```

The endpoint expects Twilio's standard inbound SMS webhook form payload,
validates `X-Twilio-Signature`, runs a single request-scoped recipe agent turn,
and replies with TwiML.

Deploy a preview to Vercel:

```bash
vercel deploy -y
```

After deploy, set the Twilio phone number's incoming message webhook to:

```text
https://<your-vercel-url>/api/twilio/sms
```

TUI commands:

- `/help` shows usage
- `/store 31` changes the default store code
- `/clear` resets the conversation
- `/quit` exits

## Store Codes

- `226` - Default store in API
- `701` - Chicago South Loop
- `31` - Los Angeles
- `546` - NYC East Village
- `452` - Austin Seaholm

## Database

Creates `traderjoes.db` with this schema:

```sql
CREATE TABLE items (
    sku TEXT,
    retail_price TEXT,
    item_title TEXT,
    inserted_at TEXT,
    store_code TEXT,
    availability TEXT,
    item_description TEXT,
    sales_size TEXT,
    sales_uom_description TEXT,
    url_key TEXT
);
```

### Example Queries

```bash
sqlite3 traderjoes.db "SELECT item_title, retail_price FROM items WHERE item_title LIKE '%miso%';"
sqlite3 traderjoes.db "SELECT * FROM items ORDER BY inserted_at DESC LIMIT 10;"
```

## Cookie Management

The tool uses a smart cookie strategy:

1. Starts immediately with a fallback cookie
2. If a 403 occurs, automatically refreshes via Selenium
3. Retries the failed request seamlessly

You can also set a cookie manually:
```bash
export TJ_AFFINITY_COOKIE="your_cookie_value"
```

## Credits

Forked from [cmoog/traderjoes](https://github.com/cmoog/traderjoes). All credit for the original concept, API reverse-engineering, and [traderjoesprices.com](https://traderjoesprices.com) goes to the upstream project.
