"""Export clean leads to CSV."""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path

from .config import KEEP_ROLES, ROOT

EXPORT_DIR = ROOT / "exports"


def export_leads(conn, *, out: str | None = None, fresh: bool = True,
                 role: str = "any") -> tuple[Path, int]:
    where = [
        "role IN (%s)" % ",".join("?" * len(KEEP_ROLES)),
        "verify != 'invalid'",
        "status NOT IN ('invalid', 'sent')",
        "email NOT IN (SELECT email FROM suppression)",
    ]
    params = list(KEEP_ROLES)
    if role != "any":
        buckets = [r.strip() for r in role.split(",") if r.strip()]
        where.append("role IN (%s)" % ",".join("?" * len(buckets)))
        params += buckets
    if fresh:
        where.append("verify IN ('valid', 'risky', 'unknown')")

    dbcols = ("company", "full_name", "title", "grade", "grade_label", "function",
              "email", "phone", "location", "linkedin", "domain", "rank_score",
              "verify", "source")
    rows = conn.execute(
        f"SELECT {', '.join(dbcols)} FROM contacts "
        f"WHERE {' AND '.join(where)} "
        f"ORDER BY rank_score DESC, grade DESC, domain", params).fetchall()

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
        ckey = keymap.get("company") or keymap.get("domain")
        skey = keymap.get("status")
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
            if "." in company or "@" in company or em.is_free_mail(email):
                company = "" if em.is_free_mail(email) else email.split("@")[-1].split(".")[0].title()
            title = (row.get(keymap.get("title")) or "").strip() if keymap.get("title") else ""
            v = em.verify(email)
            g = grading.grade_contact(email=email, title=title or None,
                                      mx_ok=(v != "invalid"))
            cid = db.upsert_contact(conn, email=email, company=company,
                                    domain=email.split("@")[-1], role=role,
                                    title=title or None, grade=g["grade"],
                                    grade_label=g["grade_label"], function=g["function"],
                                    rank_score=g["rank_score"], source="import")
            if cid is not None:
                db.set_verify(conn, cid, v)
                added += 1
    return added
