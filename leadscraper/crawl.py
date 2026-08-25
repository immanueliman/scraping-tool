"""The pipeline: discover -> clean -> classify -> verify -> store."""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from urllib.parse import urlparse

from . import db, emails as em, extract, grading, sources
from .config import DORKS_PER_CYCLE, QUERY_SLEEP, TARGET_PERSONA, build_dorks


@dataclass
class Report:
    seen: int = 0
    kept: int = 0
    dead: int = 0
    dropped: int = 0
    dup: int = 0


def store_email(conn, email: str, source: str, *, company: str = "",
                industry: str = "", location: str = "") -> str:
    """Run one bare email through the accuracy + grading pipeline."""
    keep, role = em.worth_keeping(email)
    if not keep:
        return "dropped"
    if db.is_suppressed(conn, email):
        return "dup"
    domain = email.split("@")[-1]
    if not company:
        company = "" if em.is_free_mail(email) else domain.split(".")[0].title()
    verdict = em.verify(email)                     # free MX check
    g = grading.grade_contact(email=email, mx_ok=(verdict != "invalid"),
                              target_persona=TARGET_PERSONA)
    cid = db.upsert_contact(conn, email=email, company=company, domain=domain,
                            role=role, grade=g["grade"], grade_label=g["grade_label"],
                            function=g["function"], rank_score=g["rank_score"],
                            industry=industry or None, location=location or None,
                            source=source)
    if cid is None:
        return "dup"
    db.set_verify(conn, cid, verdict)
    return "dead" if verdict == "invalid" else "kept"


def store_person(conn, person, source: str, *, company: str = "",
                 industry: str = "", location: str = "") -> str:
    """Store a NAMED contact (name+title+email+phone+linkedin) with a real grade."""
    email = (person.email or "").lower().strip()
    if not email:
        return "dropped"
    keep, role = em.worth_keeping(email)
    if not keep and not person.title:
        return "dropped"
    if db.is_suppressed(conn, email):
        return "dup"
    domain = email.split("@")[-1]
    if not company:
        company = "" if em.is_free_mail(email) else domain.split(".")[0].title()
    verdict = em.verify(email)
    g = grading.grade_contact(email=email, title=person.title, is_named=bool(person.full_name),
                              has_phone=bool(person.phone), has_linkedin=bool(person.linkedin),
                              mx_ok=(verdict != "invalid"), target_persona=TARGET_PERSONA)
    cid = db.upsert_contact(conn, email=email, company=company, domain=domain,
                            role=role if role != "other" else g["function"],
                            full_name=person.full_name or None, title=person.title or None,
                            phone=person.phone or None, linkedin=person.linkedin or None,
                            grade=g["grade"], grade_label=g["grade_label"],
                            function=g["function"], rank_score=g["rank_score"],
                            industry=industry or None, location=location or None,
                            source=source)
    if cid is None:
        return "dup"
    db.set_verify(conn, cid, verdict)
    return "dead" if verdict == "invalid" else "kept"


def run_cycle(conn, *, on_new=None) -> Report:
    rep = Report()
    sess = sources.session()

    def record(outcome, label):
        rep.seen += 1
        conn.commit()                    # release lock per contact
        if outcome == "kept":
            rep.kept += 1
            if on_new:
                on_new(label)
        elif outcome == "dead":
            rep.dead += 1
        elif outcome == "dropped":
            rep.dropped += 1
        else:
            rep.dup += 1

    def handle_emails(email_set, source, location=""):
        for email in email_set:
            record(store_email(conn, email, source, location=location), email)

    def handle_page(html, url, source, location=""):
        """Named-person extraction FIRST, then any leftover role mailboxes."""
        domain = urlparse(url).netloc.removeprefix("www.")
        claimed: set[str] = set()
        for person in extract.extract_people(html, domain):
            if not person.email:
                continue
            claimed.add(person.email)
            label = f"{person.full_name or person.email} ({person.title})" if person.title else person.email
            record(store_person(conn, person, source, location=location), label)
        for email in em.extract(html):
            if email not in claimed:
                record(store_email(conn, email, source, location=location), email)

    # 1. keyless job boards + JSON feeds (no location tag)
    handle_emails(sources.board_remoteok(sess), "remoteok")
    handle_emails(sources.board_weworkremotely(sess), "weworkremotely")
    handle_emails(sources.board_feeds(sess), "jobfeed")

    # 2. DuckDuckGo dorks — walk the PRIORITY list from a saved cursor so a
    #    24/7 run covers India first, then the world, then loops back.
    all_dorks = build_dorks()
    total = len(all_dorks)
    cursor = int(db.get_state(conn, "dork_cursor", "0") or "0") % max(1, total)
    batch = all_dorks[cursor:cursor + DORKS_PER_CYCLE]
    for query, location in batch:
        results = sources.ddg(query, max_results=15)
        for _url, snippet in results:
            handle_emails(em.extract(snippet), "ddg-snippet", location)
        for url, _ in results[:5]:
            page = sources.fetch(sess, url)
            if page:
                handle_page(page, url, "ddg-page", location)
            time.sleep(random.uniform(*sources.PAGE_SLEEP))
        time.sleep(random.uniform(*QUERY_SLEEP))
    # advance cursor (wrap around when the whole world is covered)
    db.set_state(conn, "dork_cursor", str((cursor + DORKS_PER_CYCLE) % max(1, total)))
    conn.commit()

    return rep


def harvest_company(conn, domain: str, *, on_new=None) -> Report:
    """Deep-scrape ONE company: team/leadership/about/contact pages for named
    decision-makers (name+title+email+phone+linkedin), graded and stored."""
    from urllib.parse import urljoin
    rep = Report()
    sess = sources.session()
    domain = domain.lower().removeprefix("www.")

    def tally(outcome, label):
        rep.seen += 1
        conn.commit()
        if outcome == "kept":
            rep.kept += 1
            if on_new:
                on_new(label)
        elif outcome == "dead":
            rep.dead += 1
        elif outcome == "dropped":
            rep.dropped += 1
        else:
            rep.dup += 1

    for path in sources.CONTACT_PATHS:
        html = sources.fetch(sess, urljoin(f"https://{domain}", path))
        if not html:
            continue
        claimed: set[str] = set()
        for person in extract.extract_people(html, domain):
            if not person.email:
                continue
            claimed.add(person.email)
            label = f"{person.full_name or person.email} ({person.title})" if person.title else person.email
            tally(store_person(conn, person, "site"), label)
        for email in em.extract(html):
            if email not in claimed:
                tally(store_email(conn, email, "site"), email)
        time.sleep(random.uniform(*sources.PAGE_SLEEP))
    return rep


def crawl(*, once: bool = False, cycles: int = 0, on_new=None):
    from .config import CYCLE_SLEEP
    n = 0
    while True:
        n += 1
        with db.session() as conn:
            rep = run_cycle(conn, on_new=on_new)
        yield n, rep
        if once or (cycles and n >= cycles):
            return
        time.sleep(random.uniform(*CYCLE_SLEEP))
