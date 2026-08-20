"""Extract NAMED decision-makers (name + title + email + phone + LinkedIn).

Two passes, most-accurate first:
  1. Structured data (JSON-LD schema.org Person / Organization.founder/employee)
     — self-declared by the site, so name->title->email->LinkedIn is unambiguous.
  2. Heuristic "person cards" — repeated containers on /team, /leadership pages,
     associating signals ONLY within one person's card (nearest-common-ancestor),
     so one person's email/LinkedIn is never stapled to another's name.

Pure requests + beautifulsoup4; phone parsing uses `phonenumbers` if installed.
Never fetches linkedin.com — it only collects /in/ URLs a company links itself.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from bs4 import BeautifulSoup

from . import emails as em
from . import grading

try:
    import phonenumbers
    _HAS_PHONE = True
except Exception:
    _HAS_PHONE = False

NAME_RE = re.compile(r"^(?:Mr|Ms|Mrs|Dr|Prof)?\.?\s*"
                     r"([A-Z][a-z'’]+(?:\s+[A-Z][a-z'’.]+){1,2})$")
LINKEDIN_IN_RE = re.compile(r"linkedin\.com/in/[\w\-%]+", re.I)


@dataclass
class Person:
    full_name: str = ""
    title: str = ""
    email: str = ""
    phone: str = ""
    linkedin: str = ""
    source: str = "site"

    def is_useful(self) -> bool:
        return bool(self.email) and (bool(self.full_name) or bool(self.title))


# ── phone ───────────────────────────────────────────────────────────────────
def _phone_from(text: str, region: str = "IN") -> str:
    if not _HAS_PHONE or not text:
        return ""
    try:
        for m in phonenumbers.PhoneNumberMatcher(text, region,
                                                 leniency=phonenumbers.Leniency.VALID):
            return phonenumbers.format_number(m.number, phonenumbers.PhoneNumberFormat.E164)
    except Exception:
        pass
    return ""


def _linkedin_from(node) -> str:
    a = node.select_one("a[href*='linkedin.com/in']") if hasattr(node, "select_one") else None
    if a and a.get("href"):
        m = LINKEDIN_IN_RE.search(a["href"])
        if m:
            return "https://" + m.group(0)
    return ""


# ── 1. JSON-LD structured data ──────────────────────────────────────────────
def _people_from_jsonld(html: str) -> list[Person]:
    people: list[Person] = []
    soup = BeautifulSoup(html, "lxml")
    for tag in soup.find_all("script", type="application/ld+json"):
        raw = tag.string or tag.get_text() or ""
        try:
            data = json.loads(raw)
        except Exception:
            continue
        for node in _walk_jsonld(data):
            people.append(node)
    return people


def _walk_jsonld(data) -> list[Person]:
    out: list[Person] = []

    def person_of(obj) -> Person | None:
        name = obj.get("name") or " ".join(
            x for x in [obj.get("givenName"), obj.get("familyName")] if x)
        email = (obj.get("email") or "").replace("mailto:", "").strip().lower()
        title = obj.get("jobTitle") or ""
        phone = (obj.get("telephone") or "").strip()
        same = obj.get("sameAs") or []
        if isinstance(same, str):
            same = [same]
        linkedin = next((s for s in same if "linkedin.com/in" in str(s).lower()), "")
        if name or email:
            return Person(full_name=str(name or "").strip(), title=str(title),
                          email=email, phone=str(phone), linkedin=str(linkedin),
                          source="jsonld")
        return None

    def recurse(obj):
        if isinstance(obj, list):
            for i in obj:
                recurse(i)
            return
        if not isinstance(obj, dict):
            return
        t = obj.get("@type", "")
        types = t if isinstance(t, list) else [t]
        if "Person" in types:
            p = person_of(obj)
            if p:
                out.append(p)
        # Organization -> founder / employee / member
        for key in ("founder", "founders", "employee", "employees", "member",
                    "members", "legalRepresentative"):
            if key in obj:
                recurse(obj[key])
        if "@graph" in obj:
            recurse(obj["@graph"])

    recurse(data)
    return out


# ── 2. heuristic person cards ───────────────────────────────────────────────
_CARD_SELECTORS = (".team-member, .team_member, .staff, .person, .member, "
                   ".leader, .leadership, .profile, .bio, "
                   "[class*=team], [class*=member], [class*=staff], "
                   "[class*=leader], [class*=profile], li, article, tr")


def _title_from(card) -> str:
    """Find the title inside its OWN element, not the whole card text."""
    # 1. dedicated child elements
    for el in card.find_all(["p", "span", "h4", "h5", "h6", "li", "small",
                             "em", "div"], limit=20):
        txt = el.get_text(" ", strip=True)
        if 2 <= len(txt) <= 50:
            grade, _, _ = grading.grade_title(txt)
            if grade is not None and not str(grade).startswith("0"):
                return txt
    # 2. fall back to short delimiter-split lines of the card text
    for line in re.split(r"[\n|•·,/]| - |—|–", card.get_text("\n", strip=True)):
        line = line.strip()
        if 2 <= len(line) <= 45:
            grade, _, _ = grading.grade_title(line)
            if grade is not None and not str(grade).startswith("0"):
                return line
    return ""


def _name_in(node) -> str:
    for h in node.find_all(["h1", "h2", "h3", "h4", "h5", "strong", "b"], limit=6):
        txt = h.get_text(" ", strip=True)
        m = NAME_RE.match(txt)
        if m:
            return m.group(1)
    return ""


def _people_from_cards(html: str, domain: str) -> list[Person]:
    soup = BeautifulSoup(html, "lxml")
    people: list[Person] = []
    seen_emails: set[str] = set()
    for card in soup.select(_CARD_SELECTORS):
        card_html = str(card)
        card_text = card.get_text(" ", strip=True)
        if len(card_text) > 600:      # too big to be one person's card
            continue
        emails = {e for e in em.extract(card_html)
                  if e.split("@")[-1] == domain or domain in e.split("@")[-1]}
        name = _name_in(card)
        title = _title_from(card)
        if not (name and (title or emails)):
            continue
        email = ""
        for e in emails:
            if e not in seen_emails:
                email = e
                break
        if email:
            seen_emails.add(email)
        people.append(Person(
            full_name=name, title=title, email=email,
            phone=_phone_from(card_text), linkedin=_linkedin_from(card),
            source="card"))
    return people


def extract_people(html: str, domain: str) -> list[Person]:
    """All named people found on one page, JSON-LD first then cards. Deduped."""
    people = _people_from_jsonld(html) + _people_from_cards(html, domain)
    out: list[Person] = []
    seen: set[str] = set()
    for p in people:
        key = p.email or f"{p.full_name}|{p.title}"
        if key and key not in seen:
            seen.add(key)
            out.append(p)
    return out
