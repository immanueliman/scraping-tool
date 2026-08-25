#!/usr/bin/env bash
# Install + start the 24/7 systemd service. Run from the repo root:
#   bash deploy/install-service.sh
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
sudo cp "$REPO/deploy/leadscraper.service" /etc/systemd/system/leadscraper.service
# point the unit at wherever the repo actually lives
sudo sed -i "s#/home/ubuntu/scraping-tool#$REPO#g" /etc/systemd/system/leadscraper.service
sudo sed -i "s#^User=.*#User=$(whoami)#" /etc/systemd/system/leadscraper.service

sudo systemctl daemon-reload
sudo systemctl enable --now leadscraper

echo "==> Service running. Useful commands:"
echo "    sudo systemctl status leadscraper     # is it alive?"
echo "    journalctl -u leadscraper -f          # watch live"
echo "    ls -lt $REPO/exports/                 # the CSVs it writes"
