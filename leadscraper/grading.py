"""Seniority grading — rank contacts by decision-making power.

Two axes:
  * grade  G6 Founder/Owner > G5 C-suite/MD > G4 VP/Head/Director/GM >
           G3 Sr Manager/AGM/DGM > G2 Manager > G1 IC/junior
  * mailbox sub-grade for UNNAMED role addresses:
           0d ceo@/founder@ > 0h hr@/careers@ > 0g info@ > 0x noreply@/sales@
  * function: hr | exec | eng | sales | finance | ops | product | other

Everything is local, keyless. India-aware: 'Executive'/'Officer' are junior here,
AVP is a mid BFSI grade, GM/DGM/AGM are real functional owners, and a bare
'Director' at a tiny company often means owner. Resolution is ORDERED
longest-match on a normalized title, so 'Assistant General Manager' never
collapses to 'Manager' and 'VP HR' never collapses to 'HR'.
"""

from __future__ import annotations

import re

# ── grade ladder ────────────────────────────────────────────────────────────
GRADE_LABEL = {
    6: "Founder/Owner", 5: "C-Suite/MD", 4: "VP/Head/Director/GM",
    3: "Sr Manager/AGM/DGM", 2: "Manager", 1: "IC/Junior",
    "0d": "Mailbox: decision-maker", "0h": "Mailbox: HR/recruiting",
    "0g": "Mailbox: generic", "0x": "Mailbox: noise", None: "Unknown",
}
BASE_SCORE = {6: 95, 5: 90, 4: 75, 3: 60, 2: 45, 1: 30,
              "0d": 55, "0h": 25, "0g": 12, "0x": 3, None: 15}

# ── title normalization (Indian abbreviations) ──────────────────────────────
_ABBREV = {
    "sr": "senior", "jr": "junior", "dy": "deputy", "asst": "assistant",
    "astt": "assistant", "mgr": "manager", "gm": "general manager",
    "dgm": "deputy general manager", "agm": "assistant general manager",
    "md": "managing director", "vp": "vice president",
    "avp": "assistant vice president", "svp": "senior vice president",
    "evp": "executive vice president", "ta": "talent acquisition",
    "hrbp": "hr business partner", "hod": "head of department",
    "l&d": "learning and development", "&": "and",
}


def normalize_title(title: str) -> str:
    # hyphens/dots -> spaces so 'vice-president' == 'vice president', 'co-founder'
    # == 'co founder' (else the VP negative-lookbehind and rules mis-fire).
    t = (title or "").lower().replace(".", " ").replace("-", " ")
    t = re.sub(r"[^a-z0-9& ]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    tokens = [_ABBREV.get(tok, tok) for tok in t.split(" ")]
    return " ".join(tokens)


# ── ordered (pattern, grade, function) — most senior/specific FIRST ─────────
# function: hr exec eng sales finance ops product other
_RULES: list[tuple[str, object, str]] = [
    # G6 founder / owner
    (r"\b(founder|co ?founder|co ?owner|owner|proprietor|promoter|founding (partner|member))\b", 6, "exec"),
    # G5 C-suite / MD  (test 'chief * officer' and 'executive director' before junior 'officer'/'executive')
    (r"\bchro\b|chief (human resources|people|talent) officer", 5, "hr"),
    (r"\bcto\b|chief (technology|technical) officer", 5, "eng"),
    (r"\bceo\b|chief executive officer", 5, "exec"),
    (r"\bc[efoimr]o\b|chief [a-z ]+ officer|cxo", 5, "exec"),
    (r"managing director|whole ?time director|executive director", 5, "exec"),
    (r"\bpresident\b(?<!vice president)", 5, "exec"),
    (r"chair(man|person|woman)|managing partner", 5, "exec"),
    (r"country (head|manager|director)", 5, "exec"),
    (r"chief of staff", 4, "exec"),
    # G3 qualifier tier — MUST be tested before the shorter G4 VP/GM patterns,
    # because 'assistant general manager' contains 'general manager'.
    (r"assistant vice president|assistant general manager|deputy general manager|chief manager|associate (director|vice president)", 3, "exec"),
    # G4 VP / Head / Director / GM
    (r"vice president of (hr|people|talent)|vp (of )?(hr|people|talent)|head of (hr|people|talent)|(hr|people|talent) head", 4, "hr"),
    (r"vice president of (engineering|technology)|vp (of )?(engineering|technology)|head of (engineering|technology|platform)|director of engineering|engineering director", 4, "eng"),
    (r"senior vice president|executive vice president|\bvice president\b", 4, "exec"),
    (r"head of [a-z ]+|general manager|\b[a-z]+ head\b|\bhead\b", 4, "exec"),
    (r"\b(senior |associate )?director\b", 4, "exec"),
    # G3 Sr Manager / Principal
    (r"(senior|group) manager|principal|(zonal|circle|cluster) (head|manager)", 3, "exec"),
    # G2 Manager
    (r"talent acquisition manager|recruitment manager|hiring manager|hr manager|people (ops|operations) manager|hr business partner", 2, "hr"),
    (r"engineering manager|dev(elopment)? manager|tech(nical)? lead|team lead(er)?", 2, "eng"),
    (r"\bmanager\b|supervisor|superintendent|foreman", 2, "other"),
    # G1 IC / junior  (India: 'executive'/'officer' are junior)
    (r"recruiter|sourcer|(hr|talent) (executive|officer|generalist|associate|coordinator|specialist)", 1, "hr"),
    (r"software (engineer|developer)|\bsde\b|developer|programmer|qa engineer|(senior |sr )?engineer", 1, "eng"),
    (r"executive|officer|specialist|generalist|associate|analyst|coordinator|consultant|representative|assistant|trainee|intern|apprentice|fresher|staff", 1, "other"),
]

# function keywords (fallback when the matched rule's function is 'other')
_FUNC = {
    "hr": ("hr", "human resource", "people", "talent", "recruit", "hiring",
           "staffing", "l and d", "learning and development"),
    "eng": ("engineer", "engineering", "developer", "technology", "technical",
            "architect", "devops", "sre", "platform", "data", "ml", "ai", "it"),
    "sales": ("sales", "business development", "account executive", "revenue", "gtm"),
    "finance": ("finance", "accounts", "accounting", "cfo", "controller"),
    "product": ("product", "design", "ux"),
    "ops": ("operations", "operation", "delivery", "supply"),
}


def _function_of(norm_title: str, fallback: str) -> str:
    for fn, kws in _FUNC.items():
        if any(k in norm_title for k in kws):
            return fn
    return fallback


def grade_title(title: str) -> tuple[object, str, str]:
    """Return (grade, grade_label, function) for a person's title."""
    norm = normalize_title(title)
    if not norm:
        return None, GRADE_LABEL[None], "other"
    for pattern, grade, fn in _RULES:
        if re.search(pattern, norm):
            return grade, GRADE_LABEL[grade], _function_of(norm, fn)
    return None, GRADE_LABEL[None], _function_of(norm, "other")


# ── mailbox sub-grading for role addresses (no name) ────────────────────────
_MAILBOX = {
    "0d": {"ceo", "founder", "founders", "cofounder", "md", "managingdirector",
           "owner", "president", "chairman", "promoter", "director"},
    "0h": {"hr", "humanresources", "careers", "career", "jobs", "job", "recruit",
           "recruiting", "recruitment", "hiring", "talent", "people", "resume",
           "resumes", "cv", "apply", "workwithus", "joinus", "hiring"},
    "0g": {"info", "contact", "hello", "hi", "enquiry", "enquiries", "inquiry",
           "inquiries", "admin", "office", "mail", "reachus", "connect", "team"},
    "0x": {"noreply", "no-reply", "donotreply", "do-not-reply", "support", "help",
           "sales", "marketing", "billing", "accounts", "invoice", "webmaster",
           "postmaster", "hostmaster", "abuse", "privacy", "legal",
           "notifications", "alerts", "newsletter", "mailer-daemon"},
}


def grade_mailbox(email: str) -> tuple[object, str]:
    local = email.split("@")[0].split("+")[0].lower()
    # exact role mailbox (ceo, hr, careers, info, noreply…)
    for sub, names in _MAILBOX.items():
        if local in names:
            return sub, GRADE_LABEL[sub]
    # segmented role mailbox: hr.support / talent.acquisition / hr_team / ceo.office
    segs = [s for s in re.split(r"[._\-]", local) if s]
    for sub in ("0d", "0h"):     # rescue only decision / HR inboxes
        if any(s in _MAILBOX[sub] for s in segs):
            return sub, GRADE_LABEL[sub]
    # a firstname.lastname@ pattern with no role segment is a person, not a mailbox
    if re.match(r"^[a-z]+[._][a-z]+$", local):
        return None, GRADE_LABEL[None]
    return "0g", GRADE_LABEL["0g"]


def is_role_email(email: str) -> bool:
    local = email.split("@")[0].split("+")[0].lower()
    return any(local in names for names in _MAILBOX.values())


# ── composite rank_score (0-100) ────────────────────────────────────────────
def rank_score(*, grade, function: str, is_named: bool, personal_email: bool,
               has_contact: bool, mx_ok: bool, target_persona: str | None) -> int:
    score = BASE_SCORE.get(grade, 15)
    if is_named:
        score += 8
    if personal_email:
        score += 6
    if has_contact:          # phone or linkedin present
        score += 4
    if target_persona and function == target_persona:
        score += 5
    if not mx_ok:
        score -= 20
    return max(0, min(100, score))


def grade_contact(*, email: str, title: str | None = None, is_named: bool = False,
                  has_phone: bool = False, has_linkedin: bool = False,
                  mx_ok: bool = True, target_persona: str | None = None) -> dict:
    """One call that grades a contact (named person OR bare mailbox)."""
    if title and title.strip():
        grade, label, fn = grade_title(title)
        if grade is None:                      # title didn't resolve -> try mailbox
            grade, label = grade_mailbox(email)
            fn = "hr" if grade == "0h" else "exec" if grade == "0d" else "other"
    else:
        grade, label = grade_mailbox(email)
        fn = "hr" if grade == "0h" else "exec" if grade == "0d" else "other"

    personal = not is_role_email(email)
    score = rank_score(grade=grade, function=fn, is_named=is_named,
                       personal_email=personal, has_contact=has_phone or has_linkedin,
                       mx_ok=mx_ok, target_persona=target_persona)
    return {"grade": (str(grade) if grade is not None else None),
            "grade_label": label, "function": fn, "rank_score": score}
