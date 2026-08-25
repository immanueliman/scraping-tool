"""Export clean leads to CSV."""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path

from .config import ROOT

EXPORT_DIR = ROOT / "exports"

# One predicate shared by export AND the status "exportable" count so they agree.
# rank_score >= 20 keeps every named person (>=29) plus decision/HR mailboxes
# (0d=55, 0h=25+) and drops generic (0g=12-18) and noise (0x=3) mailboxes.
BASE_WHERE = ("rank_score >= 20 AND verify != 'invalid' "
              "AND status NOT IN ('invalid', 'sent') "
              "AND email NOT IN (SELECT email FROM suppression)")
FRESH_WHERE = " AND verify IN ('valid', 'risky', 'unknown')"


def export_leads(conn, *, out: str | None = None, fresh: bool = True,
                 role: str = "any") -> tuple[Path, int]:
    where = [BASE_WHERE]
    params: list = []
    if role != "any":
        buckets = [r.strip() for r in role.split(",") if r.strip()]
        where.append("role IN (%s)" % ",".join("?" * len(buckets)))
        params += buckets
    if fresh:
        where.append(FRESH_WHERE.strip().removeprefix("AND ").strip())

    dbcols = ("company", "full_name", "title", "grade", "grade_label", "function",
              "email", "phone", "location", "linkedin", "domain", "rank_score",
              "verify", "source")
    # rank_score already encodes seniority; don't tiebreak on the TEXT grade
    # column (where 'None'/'0h' would sort lexically above '6').
    rows = conn.execute(
        f"SELECT {', '.join(dbcols)} FROM contacts "
        f"WHERE {' AND '.join(where)} "
        f"ORDER BY rank_score DESC, domain", params).fetchall()

    # Clean, filter-friendly header. Missing values are written as "".
    header = ["sno", "company_name", "name", "title", "grade", "grade_label",
              "function", "email", "phone", "location", "linkedin", "website",
              "rank_score", "verify", "source"]

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = Path(out) if out else EXPORT_DIR / f"leads_{stamp}.csv"
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        for i, r in enumerate(rows, 1):
            website = f"https://{r['domain']}" if r["domain"] else ""
            w.writerow([
                i, r["company"] or "", r["full_name"] or "", r["title"] or "",
                r["grade"] or "", r["grade_label"] or "", r["function"] or "",
                r["email"] or "", r["phone"] or "", r["location"] or "",
                r["linkedin"] or "", website, r["rank_score"] or 0,
                r["verify"] or "", r["source"] or "",
            ])
    return path, len(rows)


def import_csv(conn, path: str) -> int:
    """Load an existing CSV of leads (needs at least an 'email' column)."""
    from . import db, emails as em, grading
    added = 0
    with open(path, encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        keymap = {k.lower().strip(): k for k in (reader.fieldnames or [])}
        ekey = keymap.get("email")
        if not ekey:
            raise ValueError("CSV needs an 'email' column")
        # accept our own export headers (company_name / website / name) as well
        ckey = (keymap.get("company") or keymap.get("company_name")
                or keymap.get("domain") or keymap.get("website"))
        nkey = keymap.get("name") or keymap.get("full_name")
        skey = keymap.get("status")
        existing_before = conn.execute("SELECT COUNT(*) FROM contacts").fetchone()[0]
        for row in reader:
            email = (row.get(ekey) or "").strip().lower()
            if not email or "@" not in email:
                continue
            keep, role = em.worth_keeping(email)
            if not keep:
                continue
            status = (row.get(skey) or "").strip().lower() if skey else ""
            if status == "sent":
                db.suppress(conn, email, reason="imported-sent")
                continue
            company = (row.get(ckey) or "").strip() if ckey else ""
            if company.startswith("http") or "." in company or "@" in company or em.is_free_mail(email):
                company = "" if em.is_free_mail(email) else email.split("@")[-1].split(".")[0].title()
            title = (row.get(keymap.get("title")) or "").strip() if keymap.get("title") else ""
            name = (row.get(nkey) or "").strip() if nkey else ""
            v = em.verify(email)
            g = grading.grade_contact(email=email, title=title or None,
                                      is_named=bool(name), mx_ok=(v != "invalid"))
            cid = db.upsert_contact(conn, email=email, company=company,
                                    domain=email.split("@")[-1], role=role,
                                    full_name=name or None, title=title or None,
                                    grade=g["grade"], grade_label=g["grade_label"],
                                    function=g["function"], rank_score=g["rank_score"],
                                    source="import")
            if cid is not None:
                db.set_verify(conn, cid, v)
    added = conn.execute("SELECT COUNT(*) FROM contacts").fetchone()[0] - existing_before
    return added
