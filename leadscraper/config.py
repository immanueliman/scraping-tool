"""Tunable knobs — edit this file to change WHO you target.

Everything the crawler searches for is built from these lists. Broaden them to
cover more companies (more roles / cities / keywords => more leads per run).
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "leads.db"

# ── WHO you want to reach ───────────────────────────────────────────────────
# Roles we keep (everything else is treated as noise and dropped).
KEEP_ROLES = {"hr", "founder", "ceo", "cto"}

# Which function to rank highest. One of: hr | exec | eng | sales | None.
# 'hr' surfaces recruiters/HR heads first; 'exec' surfaces founders/CEOs first.
TARGET_PERSONA = "hr"

# ── WHAT to search for (used to build search queries) ───────────────────────
# Sectors in PRIORITY order — tech first, then services, then non-IT.
# Companies that hire + interview are the target (JHires = interview product).
SECTORS = [
    # tech (highest priority)
    "software company", "it services company", "product company", "saas company",
    "tech startup", "fintech", "edtech", "ai company", "software services",
    # IT-enabled services
    "bpo", "bpm", "kpo", "call center", "it consulting", "software consulting",
    "staffing company", "recruitment agency",
    # non-IT that still hire + interview at scale
    "engineering company", "manufacturing company", "pharma company",
    "healthcare company", "ecommerce company", "logistics company",
    "financial services", "consulting firm",
]

# Contact terms that surface HR/careers/founder addresses on a page.
CONTACT_TERMS = '"hr@" OR "careers@" OR "talent@" OR "recruit@" OR "founder@"'

# Mailboxes worth keeping even without a person's name (careers@, jobs@, hr@…).
USEFUL_GENERIC = {"careers", "jobs", "hr", "hiring", "recruitment", "talent",
                  "recruit", "recruiting", "people", "hiring", "join"}

# Domains that are never a real company contact.
IGNORE_DOMAINS = {
    "example.com", "test.com", "sentry.io", "wixpress.com", "google.com",
    "googleapis.com", "gstatic.com", "facebook.com", "instagram.com",
    "twitter.com", "x.com", "t.co", "w3.org", "schema.org", "cloudflare.com",
    "amazonaws.com", "azurewebsites.net", "linkedin.com", "github.com",
    "youtube.com", "apple.com", "microsoft.com", "mozilla.org", "gravatar.com",
}

# Free-mail hosts (a person, not a company mailbox — kept only if role matches).
FREE_MAIL = {
    "gmail.com", "yahoo.com", "yahoo.co.in", "outlook.com", "hotmail.com",
    "live.com", "icloud.com", "rediffmail.com", "protonmail.com", "aol.com",
}

# How many queries one crawl cycle processes (from the saved cursor). The full
# location x sector list is huge; a cycle does a batch, then the cursor advances
# so a 24/7 run covers everything over time and loops back.
DORKS_PER_CYCLE = 40

# ── crawl pacing (be polite; avoid rate-limits) ─────────────────────────────
QUERY_SLEEP = (8, 15)     # seconds between search queries
PAGE_SLEEP = (1.5, 3)     # seconds between page fetches
CYCLE_SLEEP = (600, 900)  # seconds between crawl cycles (10-15 min)


def build_dorks() -> list[tuple[str, str]]:
    """PRIORITY-ordered [(query, 'City, Country')] — India first, then world.

    For each location (in priority order) we sweep the sectors (tech first),
    plus a careers-page dork. The crawler walks this list via a saved cursor.
    """
    from .locations import priority_locations
    dorks: list[tuple[str, str]] = []
    for city, label in priority_locations():
        for sector in SECTORS:
            dorks.append((f'"{city}" "{sector}" hiring {CONTACT_TERMS} email', label))
        dorks.append((f'inurl:careers "{city}" hiring "apply" email', label))
        dorks.append((f'"{city}" startup hiring "founder@" OR "careers@" OR "hr@"', label))
    return dorks
