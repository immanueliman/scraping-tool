"""leadscraper — keyless HR / founder / CEO / recruiter email finder.

    python -m leadscraper init
    python -m leadscraper crawl            # auto-discover, runs forever
    python -m leadscraper crawl --once     # one cycle then stop
    python -m leadscraper find company.com # scrape one company's contacts
    python -m leadscraper find-person --name "Priya Sharma" --domain acme.com
    python -m leadscraper import-csv old_leads.csv
    python -m leadscraper export           # clean CSV
    python -m leadscraper status
"""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from . import crawl as crawler, db, emails as em, export as exporter, grading, sources

app = typer.Typer(add_completion=False, help=__doc__)
console = Console()


def _norm(domain: str) -> str:
    return (domain.lower().strip().removeprefix("http://").removeprefix("https://")
            .split("/")[0].removeprefix("www."))


@app.command()
def init():
    """Create the leads database."""
    console.print(f"[green]Ready:[/green] {db.init()}")


@app.command()
def crawl(once: bool = typer.Option(False, "--once", help="One cycle then stop"),
          cycles: int = typer.Option(0, help="Stop after N cycles (0 = forever)"),
          export_every: float = typer.Option(
              6.0, help="Write a fresh CSV every N hours (0 = never). Default 6h.")):
    """Auto-discover HR/CEO/founder leads worldwide — no key, no input.

    Walks a priority list (India first, then the world) x all sectors, grading
    and de-duplicating as it goes, and drops a timestamped CSV every few hours.
    """
    import time
    db.init()
    if not sources.search_available():
        console.print("[red]Search library missing:[/red] pip install ddgs")
        raise typer.Exit(1)
    console.print("[green]Crawling…[/green] Ctrl+C to stop. New leads print live.")
    last_export = time.monotonic()

    def do_export():
        with db.session() as conn:
            path, n = exporter.export_leads(conn, fresh=True)
        console.print(f"[cyan]CSV written[/cyan]: {n} leads -> {path}")

    try:
        for n, rep in crawler.crawl(
                once=once, cycles=cycles,
                on_new=lambda e: console.print(f"  [green]+ {e}[/green]")):
            console.print(f"[bold]Cycle {n}[/bold]: {rep.kept} kept, {rep.dead} dead, "
                          f"{rep.dropped} noise, {rep.dup} dup (of {rep.seen} seen)")
            if export_every and (time.monotonic() - last_export) >= export_every * 3600:
                do_export()
                last_export = time.monotonic()
            if not once and not cycles:
                console.print("[dim]sleeping ~10-15 min…[/dim]")
    except KeyboardInterrupt:
        console.print("\n[yellow]Stopped.[/yellow] Leads saved.")
    do_export()
    _status()


@app.command()
def find(domain: str = typer.Argument(..., help="Company domain to scrape")):
    """Deep-scrape one company for NAMED HR/CEO/founder contacts + title + phone."""
    db.init()
    dom = _norm(domain)
    with db.session() as conn:
        rep = crawler.harvest_company(
            conn, dom, on_new=lambda label: console.print(f"  [green]+ {label}[/green]"))
    console.print(f"[bold]{rep.kept} kept[/bold], {rep.dead} dead, {rep.dropped} noise "
                  f"(of {rep.seen} seen). Export with: leadscraper export")


@app.command("find-person")
def find_person(name: str = typer.Option(..., help="Full name"),
                domain: str = typer.Option(..., help="Company domain"),
                title: str = typer.Option("", help="Their title (optional)"),
                smtp_probe: bool = typer.Option(False, help="SMTP probe (slow)")):
    """Guess a named person's email from name + domain."""
    dom = _norm(domain)
    guesses = em.guess_emails(name, dom)
    if not guesses:
        console.print("[red]Could not build guesses.[/red]")
        raise typer.Exit(1)
    best = None
    t = Table(title=f"{name} @ {dom}")
    t.add_column("email"); t.add_column("mx?"); t.add_column("verify")
    for g in guesses:
        v = em.verify(g, smtp_probe=smtp_probe)
        mx = "yes" if em.has_mx(g.split("@")[-1]) else "no"
        t.add_row(g, mx, v)
        if best is None and v != "invalid":
            best = g
    console.print(t)
    if best:
        v = em.verify(best, smtp_probe=smtp_probe)
        g = grading.grade_contact(email=best, title=title, is_named=True,
                                  mx_ok=(v != "invalid"))
        with db.session() as conn:
            cid = db.upsert_contact(conn, email=best, domain=dom,
                                    company=dom.split(".")[0].title(),
                                    role=em.classify_role(best, title),
                                    full_name=name, title=title or None,
                                    grade=g["grade"], grade_label=g["grade_label"],
                                    function=g["function"], rank_score=g["rank_score"],
                                    source="guess")
            if cid:
                db.set_verify(conn, cid, v)
        console.print(f"[green]Saved:[/green] {best}  [dim]grade {g['grade']} "
                      f"({g['grade_label']}), rank {g['rank_score']}[/dim]")


@app.command("import-csv")
def import_csv(path: str = typer.Argument(..., help="CSV with an 'email' column")):
    """Load an existing CSV of leads (cleaned + deduped on import)."""
    db.init()
    with db.session() as conn:
        added = exporter.import_csv(conn, path)
    console.print(f"[green]Imported {added} usable leads[/green]")
    _status()


@app.command()
def export(out: str = typer.Option("", help="Output CSV path"),
           role: str = typer.Option("any", help="hr,founder,ceo,cto or any"),
           fresh: bool = typer.Option(True, help="Only leads not yet sent")):
    """Export a clean, verified CSV."""
    with db.session() as conn:
        path, n = exporter.export_leads(conn, out=out or None, role=role, fresh=fresh)
    if n == 0:
        console.print("[yellow]Nothing to export. Crawl or import first.[/yellow]")
    else:
        console.print(f"[green]Exported {n} leads[/green] -> {path}")


def _status():
    with db.session() as conn:
        total = conn.execute("SELECT COUNT(*) FROM contacts").fetchone()[0]
        sent = conn.execute("SELECT COUNT(*) FROM suppression").fetchone()[0]
        named = conn.execute("SELECT COUNT(*) FROM contacts WHERE full_name != '' "
                             "AND full_name IS NOT NULL").fetchone()[0]
        by_grade = conn.execute(
            "SELECT grade, grade_label, COUNT(*) c FROM contacts "
            "WHERE grade IS NOT NULL GROUP BY grade ORDER BY c DESC").fetchall()
        frow = conn.execute(
            "SELECT COUNT(*) FROM contacts WHERE role IN ('hr','founder','ceo','cto') "
            "AND verify != 'invalid' AND status NOT IN ('invalid','sent') "
            "AND email NOT IN (SELECT email FROM suppression)").fetchone()[0]
        cursor = int(db.get_state(conn, "dork_cursor", "0") or "0")
    from .config import build_dorks
    total_dorks = len(build_dorks())
    pct = (cursor / total_dorks * 100) if total_dorks else 0
    t = Table(title="leadscraper status")
    t.add_column("metric"); t.add_column("count", justify="right")
    t.add_row("total contacts", str(total))
    t.add_row("named (name + title)", str(named))
    t.add_row("already sent", str(sent))
    for r in by_grade:
        t.add_row(f"  grade {r['grade']}: {r['grade_label']}", str(r["c"]))
    t.add_row("[bold]exportable fresh leads[/bold]", f"[bold]{frow}[/bold]")
    t.add_row("location coverage", f"{cursor}/{total_dorks} queries ({pct:.0f}%)")
    console.print(t)


@app.command()
def status():
    """Show counts."""
    _status()


if __name__ == "__main__":
    app()
