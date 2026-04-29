# AGENTS.md - Donkey Punch Phone OSINT Tool

## Quick Start
```bash
python dp.py
```
No virtual environment or package installation instructions exist. Required packages: `phonenumbers`, `requests`, `beautifulsoup4`.

## Architecture
- **dp.py** - CLI entry point with single/batch analysis modes, exports to JSON/TXT/CSV/HTML
- **phone_analyzer.py** - Core `PhoneNumberAnalyzer` class with 14 analysis modules (OSINT, VoIP, breach checks, reputation, etc.)
- **phone_data.py** - Static databases: carriers, country rules, suspicious patterns, VoIP providers, premium rate ranges
- **dp_utils.py** - Utilities: logging to `dp_analysis.log`, parallel execution via ThreadPoolExecutor, HTTP requests with rate-limit handling

## Key Facts
- Reports saved as `reporte_{number}_{timestamp}.{json|txt|html}` in root directory
- Batch mode exports combined CSV and JSON reports
- Google searches include randomized User-Agent rotation and rate-limit handling (429 detection with exponential backoff)
- VoIP detection checks against known providers: Google Voice, Skype, Twilio, WhatsApp Business, Telegram
- Premium rate verification for US/ES/GB/MX number ranges
- No tests, no linter, no type checker configured

## Quirks
- Windows-only clear screen (`os.system('cls')`) - fails on Unix
- Parallel checks sleep 0.5-1.5s between submissions to avoid blocks
- Phone number validation relies on `phonenumbers` library; invalid numbers return early with error dicts
- All analysis runs in parallel via `parallel_check()` in dp_utils.py:100

## No Existing Instruction Files
No README, no requirements.txt, no CI config, no .opencode.json. This file is the only instruction source.
