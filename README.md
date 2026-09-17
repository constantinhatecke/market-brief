# market-brief

LLM-backed FastAPI service that produces a twice-weekly stock and commodity brief and emails it.
A deterministic screen ranks a universe on technical, fundamental, relative and risk metrics; an
LLM with tool use investigates the shortlist and returns a schema-validated JSON brief; the brief is
rendered to a six-minute email with links. Runs on a GitHub Actions cron for free.

```
data (yfinance) -> indicators + fundamentals + regime -> cross-sectional score
   -> LLM analyst (tool use: get_ticker_detail, get_news, submit_brief) -> Pydantic Brief
   -> HTML/text email -> SMTP
```

## What it measures (V1)

| Group | Fields |
|---|---|
| Technical | 20/40/100DMA and distance to each, RSI14, ATR14 (and % of price), 20-day high and distance, relative volume vs 20-day average, 20/40-day momentum, MA stack |
| Fundamental | EPS growth (current quarter, current year, next year), EPS estimate revisions, revenue estimate revisions, trailing P/E vs 4-year median P/E |
| Relative | 20/40-day momentum minus sector ETF, minus SPY |
| Risk | 20-day realised volatility, market regime (SPY vs 50/200DMA, VIX, sector breadth), liquidity (20-day average dollar volume) |

Revisions: Yahoo publishes current consensus but no revenue-revision history, so every run snapshots
estimates into `state/estimates.json` and computes the revision against the entry that is at least 21
days old. Until the snapshot is that old, EPS revision falls back to Yahoo's 30-day EPS trend and revenue
revision is empty. After three weeks of runs both are real.

## Run it today

### 1. Local (5 minutes)

```bash
git clone https://github.com/<you>/market-brief && cd market-brief
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # fill in keys (see below)
python -m brief portfolio add MSFT 5 --cost 410
python -m brief run             # prints the brief, writes outputs/brief_<date>.html
python -m brief run --send      # emails it
pytest                          # 18 tests, no network needed
```

Keys:
- `ANTHROPIC_API_KEY` from console.anthropic.com. Without it the pipeline still runs using a rule-based
  brief, which is useful for testing the plumbing.
- Gmail: turn on 2-step verification, then create an App Password at myaccount.google.com/apppasswords.
  Put it in `SMTP_PASSWORD`, your address in `SMTP_USER` and `EMAIL_TO`.

### 2. Forever, free: GitHub Actions

1. Push the repo to GitHub (public repo = unlimited Actions minutes; private = 2,000 min/month, a run
   uses about 5).
2. Settings > Secrets and variables > Actions > New repository secret:
   `ANTHROPIC_API_KEY`, `SMTP_USER`, `SMTP_PASSWORD`, `EMAIL_FROM`, `EMAIL_TO`.
3. Settings > Actions > General > Workflow permissions: "Read and write" (the job commits `state/`).
4. Actions tab > market-brief > Run workflow to send the first one now.

The schedule in `.github/workflows/brief.yml` is Monday and Thursday 05:30 UTC. GitHub can delay cron by
some minutes and disables schedules on repos with no commits for 60 days; the bot's own state commits
keep it alive.

Cost: the only paid part is the model call. With `claude-sonnet-4-6` a run is a few cents, so well under
one euro a month. Set the repo variable `BRIEF_MODEL` to `claude-haiku-4-5` if you want it cheaper.

### 3. As a service (Docker)

```bash
docker build -t market-brief .
docker run --env-file .env -p 8000:8000 -v $(pwd)/config:/app/config -v $(pwd)/state:/app/state market-brief
```

Endpoints (docs at `/docs`):

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | liveness |
| GET | `/portfolio` | current positions |
| PUT | `/portfolio` | replace the portfolio |
| POST | `/portfolio/positions` | add or update one position `{"ticker":"NVDA","shares":4,"cost_basis":120}` |
| DELETE | `/portfolio/positions/{ticker}` | remove a position |
| POST | `/brief/run?send=false&background=false` | generate a brief now, returns the structured JSON |
| GET | `/brief/latest` | last brief (JSON, without HTML) |
| GET | `/metrics/{ticker}` | live technical and risk fields for any ticker |

Set `BRIEF_API_TOKEN` and send it as `X-API-Token` to protect the write endpoints. Free hosts for the
service: Render or Fly.io free tiers, then trigger `/brief/run` from cron-job.org if you would rather
not use GitHub Actions. Note that on Actions the portfolio is read from the repo, so edits made via the
API only persist where the API runs; the simplest workflow is editing `config/portfolio.yaml` and pushing.

## Updating the portfolio

Three equivalent ways:
- edit `config/portfolio.yaml` and push (this is what the scheduled run reads);
- `python -m brief portfolio add TICKER SHARES --cost PRICE` / `remove TICKER` / `show`;
- `POST /portfolio/positions` on the running service.

Add tickers to `config/universe.yaml` to change what gets screened. Any ticker Yahoo knows works,
including ETFs (`XLE`, `GLD`), ADRs (`ASML`, `TSM`) and futures (`CL=F`).

## How the LLM step works

`brief/analyst.py` sends the model a compact JSON context: regime, portfolio rows with metrics, the
top and bottom names from the screen, commodities. Three tools are exposed:

- `get_ticker_detail(ticker)`: the full metric dictionary
- `get_news(ticker)`: five recent headlines with URLs
- `submit_brief(brief)`: input schema is `Brief.model_json_schema()`

The loop runs until `submit_brief` is called; if the payload fails Pydantic validation the error is
returned as a tool result and the model resubmits. The system prompt caps the brief at about 1,250 words
(six minutes at 220 wpm), forbids numbers not in the data, and asks for levels rather than instructions.

## Layout

```
brief/
  config.py        settings, paths, sector ETF map, commodity list
  data.py          yfinance download and news (the only network module besides fundamentals)
  indicators.py    DMA, RSI, ATR, momentum, volatility, setup tags
  fundamentals.py  Yahoo estimates, historical P/E, revision snapshot
  regime.py        SPY trend, VIX, sector breadth -> label
  scoring.py       z-score composite ranking and candidate selection
  analyst.py       tool-use loop and offline fallback
  render.py        HTML/text rendering, reading time
  mailer.py        SMTP
  pipeline.py      orchestration
  api.py           FastAPI
  cli.py           python -m brief ...
templates/email.html
config/portfolio.yaml, config/universe.yaml
state/estimates.json, state/last_brief.json   (written by runs, committed by the Action)
tests/             indicators, scoring, regime, fundamentals, tool loop, API, end-to-end with mocked data
```

## Limits worth knowing

- Yahoo data is free and unofficial; fields occasionally come back empty and the code degrades to `n/a`
  rather than failing. If yfinance breaks on a Yahoo change, `pip install -U yfinance` usually fixes it.
- Estimate revisions need the snapshot to age (see above).
- Historical P/E uses annual diluted EPS, so it is a 3 to 4 point history, good for "rich or cheap vs its
  own past", not for precise valuation work.
- Output is information, not advice. The prompt is written to describe setups and levels, not to tell
  anyone what to trade.

## CV line

**LLM-backed market brief service**, Independent, Sep 2026. Python, FastAPI, Anthropic API, pandas, Docker, GitHub Actions.
Built a REST service and scheduled pipeline that screens 90 equities and 8 commodity futures on 20 technical,
fundamental, relative and risk metrics, has an LLM investigate the shortlist via tool calls and return a
schema-validated JSON brief, and emails a six-minute report twice a week; tested end to end with mocked data.
