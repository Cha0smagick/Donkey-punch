# 🔍 Donkey Punch Phone Recognizer

![Python](https://img.shields.io/badge/python-3.9%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey)
![Network](https://img.shields.io/badge/network-optional%20(--no--net)-informational)

**A Swiss-army knife for phone-number OSINT**: line type and carrier identification, reputation heuristics, VoIP / premium-rate / toll-free detection, public web presence, filtered email cross-referencing, advanced dorks and a consolidated risk score — built on public sources only, with technical honesty about what each module can and cannot prove.

> ⚠️ **Passive reconnaissance only.** There is no "GPS ping" and no operator lookup: everything here is public-source heuristics. Phone-number ownership **cannot** be proven with OSINT, and no module in this tool claims to. Use responsibly — see [Ethical & Legal Use](#-ethical--legal-use).

---

## 📑 Table of Contents

- [Features](#-features)
- [What it does NOT do](#-what-it-does-not-do)
- [Installation](#-installation)
- [Usage](#-usage)
  - [CLI](#cli)
  - [Batch mode](#batch-mode)
  - [As a Python library](#as-a-python-library)
- [Example output](#-example-output)
- [Analysis modules](#-analysis-modules)
- [The web search engine](#-the-web-search-engine)
- [Risk score](#-risk-score)
- [Configuration & environment variables](#-configuration--environment-variables)
- [Outputs & artifacts](#-outputs--artifacts)
- [Project structure](#-project-structure)
- [Troubleshooting](#-troubleshooting)
- [Ethical & legal use](#-ethical--legal-use)
- [Contributing](#-contributing)
- [License](#-license)

## ✨ Features

- **20 analysis modules** orchestrated in parallel with a **shared search budget** per number (default: 8 web queries total, no matter how many modules run).
- **Multi-engine web search** (DuckDuckGo HTML → DuckDuckGo Lite → Bing → Mojeek) with automatic failover, per-host throttling, on-disk caching (24 h TTL) and **zero API keys required**.
- **Ground truth line types**: VoIP, premium-rate and toll-free detection via `phonenumbers.number_type()` — never fragile prefix regexes. Verified live: a UK mobile is geolocated where the old approach excluded it; US toll-free and ES premium numbers are correctly skipped.
- **Honest mobile geolocation**: mobiles only; reports an explicit precision level (Low / Low-Medium / Medium-Low) and labels speculative IPs as speculative.
- **Noise-free email cross-referencing**: harvested emails are accepted only if they are actually linked to the number (digits in the local part, or adjacency in the page text) + Gravatar avatar checks (`?d=404`).
- **Consolidated risk score** 0–10 with signals and recommendations.
- **Multiple export formats**: TXT / JSON / CSV / HTML into `reports/`.
- **Offline mode** (`--no-net`): fully local analysis with zero network requests.
- **Optional enrichment** via numverify / Twilio when API keys are present in the environment.
- **Clean encoding everywhere**: UTF-8 output on Windows cp1252 consoles, BOM'd CSV for Excel, escaped HTML.

## 🚫 What it does NOT do

| Claim | Reality |
|-------|---------|
| "Get the GPS location of a phone" | Impossible without the carrier + a court order. This tool gives a city/region estimate for mobiles and says so. |
| "Check if a number has WhatsApp" | `wa.me` returns HTTP 200 for **any** number. The tool provides the contact link only and never claims verification. |
| "Find the owner's Telegram" | `t.me/<digits>` only reveals whether a **numeric alias** exists; Telegram aliases are chosen by users. Not ownership. |
| "Find the owner's email" | Patterns are **hypotheses**; harvested emails are strictly filtered and Gravatar only proves an avatar exists. |
| "Query the carrier's subscriber database" | No. Carrier data is range metadata and may be invalidated by number portability. |

## 📦 Installation

```bash
git clone https://github.com/Cha0smagick/Donkey-punch.git
cd Donkey-punch

# (recommended) virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1        # Windows PowerShell
# source .venv/bin/activate         # Linux / macOS

pip install -r requirements.txt
```

Optional — install as a global command:

```bash
pip install -e .
dp --help
```

**Requirements:** Python ≥ 3.9, plus `phonenumbers`, `requests`, `beautifulsoup4` (pulled in automatically by `requirements.txt` / `pyproject.toml`).

## 🚀 Usage

### CLI

```bash
python dp.py                      # interactive mode
python -m dp                      # equivalent, via the package
python dp.py -n +34612345678      # single number
python dp.py -n +34... -n +52...  # several numbers
python dp.py -n +34612345678 --no-net       # offline, local modules only
python dp.py -n +34612345678 --max-queries 4 --workers 2
```

| Flag | Description |
|------|-------------|
| `-n, --numero` | Number to analyze, international format (e.g. `+34612345678`). Repeatable. |
| `-b, --batch FILE` | Text file with one number per line (`#` lines are comments). |
| `--region ISO` | Fallback region for numbers without `+` (e.g. `ES`). |
| `--no-net` | Local modules only; zero network requests. |
| `--max-queries N` | Web-search budget per number (default: 8). |
| `--workers N` | Parallel analysis threads (default: 4). |

Run with no arguments to enter the interactive menu (single or batch analysis).

### Batch mode

```bash
python dp.py -b examples/lote_ejemplo.txt --no-net
```

The batch file takes one number per line; blank lines and `#` comments are ignored. Batch runs generate per-number reports plus a combined CSV (`reports/batch_report_*.csv`) and JSON.

### As a Python library

```python
from dp import PhoneNumberAnalyzer

analyzer = PhoneNumberAnalyzer("+34612345678", no_net=True)
data = analyzer.analyze_all()

print(data["Resumen_de_riesgo"]["calificación"])   # risk rating
print(data["Información_básica"]["Operadora"])     # carrier
```

> **Note:** JSON report keys and module names are in Spanish (e.g. `Búsqueda_web`, `Detección_VoIP`) — they are stable identifiers you can rely on programmatically.

Constructor options: `PhoneNumberAnalyzer(number, region=None, search_client=None, no_net=False, max_queries=8)`.

## 📊 Example output

Real output from a verified run (report labels are in Spanish):

```
========================= RISK SUMMARY ==========================
• Score: 1.0/10 (Low)
  - Suspicious patterns in the number (1)

========================= BASIC INFO =========================
• Country: España
• Carrier: Syma
• Type: Móvil
• Valid: True
• Timezone: Atlantic/Canary, Europe/Madrid
• Local format: 612 34 56 78
```

Batch summary (same run, `--no-net`):

```
• +34612345678: España - Syma - Risk: Low - Geo: España
• +447911123456: Guernsey - JT - Risk: Low - Geo: Guernsey      ← UK mobile, correctly geolocated
• +18005551234: Desconocido - Risk: Low                         ← toll-free, geolocation skipped
• +34806123456: España - Risk: Critical                         ← premium rate, warned
```

## 🧩 Analysis modules

| # | Module | What it does (and doesn't) |
|---|--------|----------------------------|
| 1 | Basic info | Formats, country, timezone, validity |
| 2 | Approximate location | Region/country via geocoder; low precision for mobiles |
| 3 | **Mobile geolocation** | Mobiles only: city + probable postal code + public signals; **no GPS** |
| 4 | Web search | Multi-engine public presence, per-host detections |
| 5 | Social media | Manual search links + people-search (mostly US) — no fake verifications |
| 6 | Messaging | wa.me = contact link only (always 200); Telegram = numeric alias only |
| 7 | Carrier info | Range metadata; portability may contradict it |
| 8 | Reputation | Heuristic suspicious-pattern scoring |
| 9 | Blacklists | Manual lookup links |
| 10 | Format variations | E.164, national, RFC3966, last digits… |
| 11 | VoIP detection | Line type + carrier-name heuristic |
| 12 | Toll-free | Line type + per-country prefixes |
| 13 | Premium rate | Line type + national prefixes; cost warning |
| 14 | Breach databases | Correct links (HIBP `/phone/`) + web mentions |
| 15 | **Email cross-reference** | Strictly filtered harvest + Gravatar (`?d=404`) |
| 16 | Email patterns | Probable-address hypotheses |
| 17 | Google dorks | Up to 3 executed via own engine + manual Google links |
| 18 | Carrier footprint | Prefixes & network type (indicative, portability caveat) |
| 19 | API enrichment | numverify / Twilio **only with env keys** |
| 20 | **Risk summary** | Score 0–10, signals, recommendations |

## 🔎 The web search engine

The v1 tool scraped Google directly and spent its life collecting timeouts and 429s. v2 ships its own engine (`dp/search.py`):

- **Failover chain**: DuckDuckGo HTML (POST) → DuckDuckGo Lite → Bing → Mojeek. A blocked or anomalous engine is marked and skipped for the rest of the session.
- **Shared budget**: every module draws from the same `max_queries` pool, so a full analysis stays bounded regardless of thread count.
- **Per-host throttle** with jitter — the polite way to avoid real 429s (unlike sleeping between task *submissions*).
- **Disk cache** in `dp_cache/search/` (TTL 24 h): re-analyses of the same number are instant.
- **Never throws**: results, errors and blocked-engine lists are returned in the result dict (`motor_usado`, `error`, `stats()`).
- **Verified against live anti-bot behavior**: DDG's intermittent **202 soft-block** is detected and routed around; Bing's `bing.com/ck/a?...&u=a1<base64url>` redirect wrapping is unwrapped (without this, Bing silently yields 0 results).

## 🚦 Risk score

The consolidated summary (`Resumen_de_riesgo`) folds every module's signals into a 0–10 score:

| Rating | Meaning |
|--------|---------|
| **Low** (0–2.9) | No significant signals; manual verification still suggested for sensitive decisions. |
| **Moderate** (3–4.9) | Some heuristics matched. |
| **High** (5–6.9) | Multiple signals (e.g. VoIP + patterns + indexed presence). |
| **Critical** (7–10) | Strong signals, e.g. premium-rate line (calling it may cost you money). |

It's heuristic and non-binding — not an identity verification.

## ⚙️ Configuration & environment variables

```bash
cp .env.example .env    # fill in what you have; without keys the module is skipped
```

| Variable | Service | Effect |
|----------|---------|--------|
| `DP_NUMVERIFY_KEY` | [numverify](https://numverify.com/) | Enriched carrier/line lookup (free tier: 100 req/month) |
| `DP_TWILIO_SID` + `DP_TWILIO_TOKEN` | [Twilio Lookup](https://www.twilio.com/docs/lookup) | Enriched lookup via HTTP Basic auth |

All keys are optional. With none set, the *Enrichment* module reports the reason and everything else works normally.

## 📁 Outputs & artifacts

| Artifact | Path |
|----------|------|
| Per-number reports | `reports/reporte_{number}_{timestamp}.txt` / `.json` / `.html` |
| Batch combined | `reports/batch_report_{timestamp}.json` + `reports/batch_report_{timestamp}.csv` |
| Detailed log | `dp_analysis.log` (UTF-8) |
| Search cache | `dp_cache/search/` (TTL 24 h) |

JSON/TXT/HTML exports include the full output of all 20 modules; the CSV flattens key fields (country, carrier, risk rating, detected city, VoIP/premium flags, found emails…).

## 🗂 Project structure

```
├── dp.py                  # compatibility launcher (python dp.py)
├── dp/                    # main package
│   ├── __init__.py        # public API: PhoneNumberAnalyzer
│   ├── __main__.py        # entry point for python -m dp
│   ├── cli.py             # CLI: argparse, display, batch, exports
│   ├── analyzer.py        # core: 19 modules + risk summary
│   ├── search.py          # multi-engine search, budget, cache
│   ├── utils.py           # logging, throttled HTTP, parallelism, exports
│   └── data.py            # static DB: carriers, prefixes, templates, APIs
├── examples/
│   └── lote_ejemplo.txt   # sample batch file
├── reports/               # generated reports (gitignored)
├── requirements.txt
├── pyproject.toml
├── CHANGELOG.md
├── LICENSE
└── .env.example
```

## 🛠 Troubleshooting

- **"Sin resultados o todos los motores bloqueados"** (no results / all engines blocked): search engines rate-limit datacenter IPs aggressively. Wait a few minutes, lower `--max-queries`, or run with `--no-net`. The cache makes retries cheap. If *every* engine returns 0 hits persistently, their HTML selectors likely changed — the parsers live in `dp/search.py` and are deliberately defensive.
- **Mojibake / broken accents in the console**: shouldn't happen (stdout is forced to UTF-8), but on very old terminals set `PYTHONIOENCODING=utf-8`.
- **Number parses as invalid**: use full international format (`+34612345678`) or pass `--region ES` for national formats.
- **"Presupuesto de busquedas agotado"** (search budget exhausted): you hit `--max-queries`. Raise the value or let the cache work for you on re-runs.
- **Enrichment module says "Sin claves"**: that's the expected behavior without env keys — see [Configuration](#-configuration--environment-variables).

## ⚖️ Ethical & legal use

This tool **only queries public sources** and is intended for:

- Security research and defensive OSINT
- Vetting suspicious numbers (fraud, spam, premium-rate scams)
- CTFs and reconnaissance labs

**Do not use it** for harassment, doxxing, impersonation, or any illegal purpose. Line ownership **cannot be established** with OSINT, and this tool never claims it. You are responsible for how you use the results and for complying with the law in your jurisdiction (GDPR, data-protection statutes, etc.).

## 🤝 Contributing

Issues and PRs are welcome. Good first contributions:

- More search-engine parsers (the failover chain makes them cheap to add)
- More per-country premium-rate/toll-free prefix data in `dp/data.py`
- A test suite and type checking (currently none — see `AGENTS.md`)

Please keep the tool's honesty contract: no module may claim a verification it doesn't perform.

## 📄 License

[MIT](LICENSE) — © 2026 Cha0smagick

## 🔄 Changelog

See [CHANGELOG.md](CHANGELOG.md) for the full v1 → v2 audit history (enum-based line-type detection, multi-engine search, filtered email cross-referencing, encoding fixes, packaging).
