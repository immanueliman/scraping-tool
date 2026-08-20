# leadscraper

A **keyless** tool that finds real **HR / recruiter / founder / CEO** emails from
the web, verifies them, and keeps only accurate, deduped leads. No API keys, no
paid services, no accounts.

It searches DuckDuckGo + job boards + company sites, then runs every address
through an accuracy filter: drop noise, classify the role, MX-verify the domain,
and dedupe. You get a clean CSV you can use for outreach or job applications.

> Scrapers can only find **published** emails. If a company publishes none, no
> free tool can invent one — use `find-person` (name → guess) for those.

## Install
```bash
pip install -r requirements.txt
python -m leadscraper init
```

## Use
```bash
# Auto-discover, runs forever (Ctrl+C to stop). New leads print live.
python -m leadscraper crawl
python -m leadscraper crawl --once        # one cycle, to test

# Target a specific company
python -m leadscraper find razorpay.com

# Guess a named person's email
python -m leadscraper find-person --name "Priya Sharma" --domain razorpay.com

# Load an old CSV of leads (cleaned + deduped on import)
python -m leadscraper import-csv old_leads.csv

# Export a clean, verified CSV
python -m leadscraper export              # -> exports/leads_<timestamp>.csv
python -m leadscraper export --role hr,founder,ceo

python -m leadscraper status
```

## Target whoever you want — edit `leadscraper/config.py`
The searches are built from `CITIES`, `KEYWORDS`, and `SECTORS`. Broaden them for
more coverage (more roles / cities => more leads per run). `KEEP_ROLES` controls
which roles survive the filter (default: hr, founder, ceo, cto).

## Run 24/7 on a server (later, optional)
**Laptop:** `nohup python -m leadscraper crawl > crawl.log 2>&1 &` (Mac/Linux)
or `Start-Process -WindowStyle Hidden python -ArgumentList "-m","leadscraper","crawl"` (Windows).

**VPS / AWS EC2 — systemd:**
```ini
# /etc/systemd/system/leadscraper.service
[Unit]
Description=leadscraper
After=network-online.target
[Service]
WorkingDirectory=/home/ubuntu/scraping-tool
ExecStart=/home/ubuntu/scraping-tool/.venv/bin/python -m leadscraper crawl
Restart=always
RestartSec=30
[Install]
WantedBy=multi-user.target
```
```bash
sudo systemctl enable --now leadscraper
journalctl -u leadscraper -f
```

## Named decision-makers + seniority grade (the quality upgrade)
Instead of just grabbing `careers@`, `find` and the crawler parse `/team`,
`/leadership`, `/about` pages (structured JSON-LD first, then "person cards") to
capture **name + title + email + phone + LinkedIn together**, and grade every
contact by decision power:

| Grade | Meaning |
|---|---|
| G6 | Founder / Owner |
| G5 | C-suite / MD (CEO, CHRO, CTO…) |
| G4 | VP / Head / Director / GM |
| G3 | Sr Manager / AGM / DGM / AVP |
| G2 | Manager |
| G1 | Executive / Officer / Recruiter (junior) |
| 0d/0h/0g/0x | unnamed mailbox: ceo@ > hr@/careers@ > info@ > noreply@/sales@ |

Every lead gets a **rank_score (0–100)** and the CSV is sorted by it, so
decision-makers and real named people come first. Indian titles are handled
(GM/DGM/AGM, "Executive"/"Officer" = junior, AVP = mid). Set `TARGET_PERSONA`
in `config.py` to `hr` / `exec` / `eng` to boost that function.

## Accuracy — how leads stay clean
- **Noise dropped**: `info@`, `support@`, `noreply@`, image files, tracking domains.
- **Role-classified + token-aware**, so `hr` never false-matches inside a word.
- **Cloudflare-obfuscated emails decoded** (`data-cfemail` XOR), plus HTML-entity,
  `[at]/[dot]`, and `u003e`-artifact de-obfuscation — recovers emails naive regex misses.
- **MX-verified** (dead domains excluded); **disposable domains dropped**;
  optional **catch-all detection** (`--smtp-probe`) so guessed addresses on
  accept-all domains aren't trusted.
- **Deduped**, and already-sent addresses **suppressed**.

## Sources (all keyless)
DuckDuckGo dorks (built from `config.py` cities/keywords/sectors) · RemoteOK ·
WeWorkRemotely · Remotive / Arbeitnow / Jobicy JSON feeds · each company's own
site (team/leadership/about/contact). Deep-research notes on further sources
(gov open data, ATS APIs, OpenStreetMap, directories) are in the code comments
and can be added as connectors.

> **Named exec *emails* appear only when a company publishes them.** Big firms
> usually publish name+title (captured + graded) but not exec emails; smaller
> firms/agencies often publish both. For a named person with no public email,
> use `find-person` to guess + verify.

## Legal
Cold outreach is your responsibility (India DPDP / GDPR / CAN-SPAM): identify
yourself, keep it relevant, honor opt-outs. Don't scrape sites that forbid it,
and don't use LinkedIn scrapers.
