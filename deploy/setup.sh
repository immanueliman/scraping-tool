#!/usr/bin/env bash
# One-command setup on a fresh Ubuntu server (AWS EC2 / any VPS).
#   git clone https://github.com/immanueliman/scraping-tool.git
#   cd scraping-tool && bash deploy/setup.sh
set -euo pipefail

echo "==> Installing system packages"
sudo apt-get update -y
sudo apt-get install -y python3-pip python3-venv git

cd "$(dirname "$0")/.."
echo "==> Creating virtualenv + installing requirements"
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

echo ""
echo "==> Done. Quick test (one cycle):"
echo "    .venv/bin/python -m leadscraper crawl --once"
echo ""
echo "==> To run 24/7 as a service (auto-start on boot, auto-restart on crash):"
echo "    bash deploy/install-service.sh"
