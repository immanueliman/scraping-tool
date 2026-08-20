"""Accuracy engine: extract, clean, classify role, and verify emails.

This is what keeps leads accurate — noise filtering, role classification, and a
free MX check (plus optional SMTP probe) so dead/irrelevant addresses are
dropped before they reach your list.
"""

from __future__ import annotations

import html as _html
import re
import smtplib
import unicodedata
from functools import lru_cache

import dns.resolver

from .config import FREE_MAIL, IGNORE_DOMAINS, KEEP_ROLES, USEFUL_GENERIC

# Common disposable / temp-mail domains (drop these). Expand as needed.
DISPOSABLE = {
    "mailinator.com", "guerrillamail.com", "10minutemail.com", "tempmail.com",
    "temp-mail.org", "throwawaymail.com", "yopmail.com", "getnada.com",
    "trashmail.com", "sharklasers.com", "maildrop.cc", "dispostable.com",
    "fakeinbox.com", "mailnesia.com", "mohmal.com", "emailondeck.com",
    "1secmail.com", "moakt.com", "tempinbox.com", "spam4.me",
}


def _cf_decode(hex_str: str) -> str | None:
    """Decode a Cloudflare data-cfemail / email-protection hex string."""
    try:
        key = int(hex_str[:2], 16)
        return "".join(chr(int(hex_str[i:i + 2], 16) ^ key)
                       for i in range(2, len(hex_str), 2))
    except Exception:
        return None

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,7}")
SYNTAX_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")

# ── role classification (token-aware so 'hr' doesn't match 'alexhraber') ─────
FOUNDER = ("founder", "co-founder", "cofounder", "owner", "proprietor",
           "managing director", "md", "chairman", "promoter")
CEO = ("ceo", "chief executive", "president", "managing partner")
CTO = ("cto", "chief technology", "vp engineering", "head of engineering",
       "engineering manager", "director of engineering")
HR = ("hr", "chro", "human resource", "people", "talent", "recruit",
      "recruiter", "recruitment", "hiring", "staffing", "sourcer",
      "talent acquisition")


def _matches(text: str, keywords) -> bool:
    tokens = [t for t in re.split(r"[^a-z0-9]+", text.lower()) if t]
    tokenset = set(tokens)
    for kw in keywords:
        if " " in kw:
            if kw in text.lower():
                return True
        elif len(kw) <= 3:
            if kw in tokenset:
                return True
        elif any(t == kw or t.startswith(kw) or kw in t for t in tokens):
            return True
    return False


def mailbox_kind(email: str) -> str:
    local = email.split("@")[0].split("+")[0].lower()
    return "useful_generic" if local in USEFUL_GENERIC else "personal"


def classify_role(email: str, title: str | None = None) -> str:
    text = (title or "").strip() or email.split("@")[0]
    if _matches(text, HR):
        return "hr"
    if _matches(text, CEO):
        return "ceo"
    if _matches(text, FOUNDER):
        return "founder"
    if _matches(text, CTO):
        return "cto"
    # careers@/jobs@/talent@ with no name still = an HR target
    if mailbox_kind(email) == "useful_generic":
        return "hr"
    return "other"


# ── extraction + artifact cleaning ──────────────────────────────────────────
_ARTIFACT_PREFIXES = ("u003e", "u003c", "u0026", "u0022", "u0027", "u0040", "u003d")


def _strip_artifacts(email: str) -> str | None:
    local, _, domain = email.partition("@")
    changed = True
    while changed:
        changed = False
        for pre in _ARTIFACT_PREFIXES:
            if local.startswith(pre) and len(local) > len(pre):
                local, changed = local[len(pre):], True
    return f"{local}@{domain}" if local and domain else None


_CF_RE = re.compile(r'data-cfemail="([0-9a-fA-F]{4,})"'
                    r'|/cdn-cgi/l/email-protection#([0-9a-fA-F]{4,})')


def extract(text: str) -> set[str]:
    out: set[str] = set()
    # 1. Cloudflare-obfuscated emails (invisible to plain regex)
    for m in _CF_RE.finditer(text):
        dec = _cf_decode(m.group(1) or m.group(2))
        if dec and "@" in dec:
            c = _strip_artifacts(dec.lower())
            if c:
                out.add(c)
    # 2. entity + unicode-escape + [at]/[dot] de-obfuscation, then regex
    decoded = _html.unescape(text)
    decoded = (decoded
               .replace("\\u003e", ">").replace("\\u003c", "<")
               .replace("\\u0026", "&").replace("\\u0040", "@")
               .replace("\\u002e", ".").replace("&#64;", "@").replace("&commat;", "@")
               .replace("[at]", "@").replace("(at)", "@").replace(" at ", "@")
               .replace("[dot]", ".").replace("(dot)", ".").replace(" dot ", "."))
    for raw in EMAIL_RE.findall(decoded):
        cleaned = _strip_artifacts(raw.lower())
        if cleaned:
            out.add(cleaned)
    return out


def is_disposable(email: str) -> bool:
    return email.split("@")[-1].lower() in DISPOSABLE


# ── validity + relevance ────────────────────────────────────────────────────
def syntax_ok(email: str) -> bool:
    return bool(SYNTAX_RE.match(email.strip()))


def is_free_mail(email: str) -> bool:
    return email.split("@")[-1].lower() in FREE_MAIL


@lru_cache(maxsize=4096)
def _lowest_mx(domain: str) -> str | None:
    try:
        answers = dns.resolver.resolve(domain, "MX", lifetime=8)
        return str(min(answers, key=lambda r: r.preference).exchange).rstrip(".")
    except Exception:
        return None


def has_mx(domain: str) -> bool:
    return _lowest_mx(domain) is not None


def worth_keeping(email: str) -> tuple[bool, str]:
    """(keep?, role). Drops noise; keeps only HR/founder/CEO/CTO targets."""
    if email.endswith((".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico")):
        return False, "other"
    if not syntax_ok(email):
        return False, "other"
    domain = email.split("@")[-1]
    if domain in IGNORE_DOMAINS or "." not in domain:
        return False, "other"
    if domain in DISPOSABLE:
        return False, "other"
    if email.startswith(("noreply", "no-reply", "donotreply", "postmaster", "bounce", "mailer-daemon")):
        return False, "other"
    role = classify_role(email)
    if role not in KEEP_ROLES:
        return False, role
    # free-mail is only useful if the address itself signals a recruiter
    if is_free_mail(email) and mailbox_kind(email) != "useful_generic" \
            and not _matches(email.split("@")[0], HR):
        return False, "other"
    return True, role


def verify(email: str, *, smtp_probe: bool = False) -> str:
    """'valid' | 'risky' | 'invalid' | 'unknown' — free MX check by default."""
    email = email.strip().lower()
    if not syntax_ok(email):
        return "invalid"
    if not has_mx(email.split("@")[-1]):
        return "invalid"
    if smtp_probe:
        r = _smtp_probe(email)
        if r != "unknown":
            return r
    return "risky" if is_free_mail(email) else "unknown"


def _smtp_probe(email: str, timeout: int = 12) -> str:
    host = _lowest_mx(email.split("@")[-1])
    if not host:
        return "unknown"
    server = smtplib.SMTP(timeout=timeout)
    try:
        server.connect(host, 25)
        server.helo("check.example.com")
        server.mail("check@example.com")
        code, _ = server.rcpt(email)
    except Exception:
        return "unknown"
    finally:
        try:
            server.quit()
        except Exception:
            pass
    if code in (250, 251):
        return "accepted"
    if code in (550, 551, 553, 501, 500):
        return "rejected"
    return "unknown"


@lru_cache(maxsize=2048)
def detect_catch_all(domain: str) -> str:
    """Probe a random mailbox. 'catch_all' if the server 250-OKs a fake address.

    On a catch-all domain, an SMTP 'accepted' for a guessed address is
    meaningless — never trust a guess there. Returns 'catch_all' | 'normal' |
    'unknown' (port 25 blocked / greylisted).
    """
    import random
    rnd = "".join(random.choice("abcdefghijklmnopqrstuvwxyz0123456789") for _ in range(16))
    result = _smtp_probe(f"{rnd}nope@{domain}")
    if result == "accepted":
        return "catch_all"
    if result == "rejected":
        return "normal"
    return "unknown"


# ── name -> email guessing (for find-person) ────────────────────────────────
def _tok(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if c.isalnum() and not unicodedata.combining(c)).lower()


def guess_emails(full_name: str, domain: str) -> list[str]:
    parts = [_tok(p) for p in full_name.replace(".", " ").replace("-", " ").split() if _tok(p)]
    domain = domain.lower().removeprefix("www.")
    if not parts or not domain:
        return []
    first, last = parts[0], (parts[-1] if len(parts) > 1 else "")
    if last:
        fi = first[0]
        locals_ = [f"{first}.{last}", f"{first}{last}", f"{fi}{last}",
                   f"{fi}.{last}", first, f"{first}_{last}", f"{last}.{first}"]
    else:
        locals_ = [first, first[0]]
    seen, out = set(), []
    for lo in locals_:
        if lo and lo not in seen:
            seen.add(lo)
            out.append(f"{lo}@{domain}")
    return out
