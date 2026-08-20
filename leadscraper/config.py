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
# Cities / locations to target.
CITIES = ["hyderabad", "bangalore", "bengaluru", "vizag", "visakhapatnam",
          "pune", "chennai", "remote india"]

# Tech / role keywords — broaden for more coverage.
KEYWORDS = [
    "software engineer", "full stack", ".net core", "java", "python",
    "react", "node", "devops", "data engineer", "ai engineer",
    "machine learning", "backend", "frontend",
]

# The kind of companies you want (startups hire + interview a lot).
SECTORS = ["startup", "software company", "it services", "product company"]

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

# ── crawl pacing (be polite; avoid rate-limits) ─────────────────────────────
QUERY_SLEEP = (8, 15)     # seconds between search queries
PAGE_SLEEP = (1.5, 3)     # seconds between page fetches
CYCLE_SLEEP = (900, 1200) # seconds between full crawl cycles (15-20 min)


def build_dorks() -> list[str]:
    """Compose search queries from the config above."""
    dorks: list[str] = []
    contact = '"hr@" OR "careers@" OR "talent@" OR "recruit@" OR "founder@"'
    for city in CITIES:
        for kw in KEYWORDS[:8]:            # cap so cycles stay reasonable
            dorks.append(f'"{city}" "{kw}" hiring {contact}')
        for sector in SECTORS:
            dorks.append(f'"{sector}" "{city}" hiring {contact} email')
        dorks.append(f'inurl:careers "{city}" hiring "apply" email')
    # founder / CEO discovery (decision-makers at startups)
    dorks += [
        '"we\'re hiring" startup india "founder@" OR "careers@" OR "hr@"',
        '"join our team" startup india engineer "hr@" OR "careers@"',
        'inurl:careers startup india "apply" "hr@" OR "jobs@"',
    ]
    return dorks
