# Deploy leadscraper 24/7 on AWS EC2 (free tier)

## 1. Launch a server
- EC2 → Launch instance → **Ubuntu 24.04**, type **t3.micro** (free tier), 8 GB disk.
- Security group: allow **SSH (22)** from your IP. (No inbound web port needed.)
- Download the key `.pem`.

## 2. Connect + set up
```bash
ssh -i your-key.pem ubuntu@<EC2-PUBLIC-IP>
git clone https://github.com/immanueliman/scraping-tool.git
cd scraping-tool
bash deploy/setup.sh
```

## 3. Run it 24/7
```bash
bash deploy/install-service.sh
```
That installs a `systemd` service that:
- starts on every boot, auto-restarts on crash,
- crawls the priority list (India first → then the world) across all sectors,
- writes a fresh CSV to `exports/` **every 6 hours**.

Check it:
```bash
sudo systemctl status leadscraper      # alive?
journalctl -u leadscraper -f           # watch live
ls -lt exports/                        # the CSVs
```

## 4. Get the leads onto your laptop
From your laptop (not the server):
```bash
scp -i your-key.pem "ubuntu@<EC2-PUBLIC-IP>:~/scraping-tool/exports/*.csv" .
```
Or generate one on demand over SSH:
```bash
.venv/bin/python -m leadscraper export && ls -lt exports/
```

## Tuning (optional)
- **Who/where to target:** edit `leadscraper/config.py` (sectors) and
  `leadscraper/locations.py` (states/cities/countries — order = priority).
- **CSV frequency:** change `--export-every 6` in `deploy/leadscraper.service`.
- **Coverage:** `python -m leadscraper status` shows how far through the
  priority list the crawl has walked.

## Notes
- Free tier is enough to start; after 12 months a t3.micro is ~₹600-700/mo.
- The DB (`leads.db`) and `exports/` are git-ignored — they live only on the
  server. Back them up with `scp` if needed.
- Cold outreach is your responsibility (DPDP/GDPR/CAN-SPAM): identify yourself,
  stay relevant, honor opt-outs.
