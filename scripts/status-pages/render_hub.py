"""Render the STF hub: one page that links every status page of this repo and summarises the plane.

Usage: python3 scripts/status-pages/render_hub.py [--out PATH]   (stdlib only; default .stf/hub.html, gitignored)
Reads pages.json and .stf/export/*.json; never writes to specs/ or .stf/export/.
"""
import argparse
import html
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
EXPORT = REPO / ".stf/export"
PHASES = ["specify", "clarify", "plan", "tasks", "analyze"]


def load(name):
    p = EXPORT / name
    if not p.exists():
        return []
    if p.suffix == ".jsonl":
        return [json.loads(line) for line in p.read_text().splitlines() if line.strip()]
    return json.loads(p.read_text())


def git(*args):
    try:
        return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def e(s):
    return html.escape(str(s if s is not None else ""))


def link(url, label):
    if not url:
        return '<span class="nolink">not published yet</span>'
    return f'<a class="open" href="{e(url)}" target="_blank" rel="noopener">{e(label)} <span aria-hidden="true">↗</span></a>'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out")
    args = ap.parse_args()
    out = Path(args.out) if args.out else REPO / ".stf/hub.html"

    pages = json.loads((HERE / "pages.json").read_text()) if (HERE / "pages.json").exists() else {}
    specs = sorted(load("specs.json"), key=lambda s: s["seq"])
    tasks, questions = load("tasks.json"), load("questions.json")
    runs, handoffs, events = load("runs.json"), load("handoffs.json"), load("events.jsonl")

    done = sum(1 for t in tasks if t.get("status") == "done")
    blocked = sum(1 for t in tasks if t.get("status") == "blocked")
    open_q = sum(1 for q in questions if q.get("status") == "open")
    open_runs = [r for r in runs if r.get("status") == "open"]
    pending = [h for h in handoffs if h.get("status") == "sent"]

    stats = [
        (len(specs), "specs", ""),
        (f"{done} / {len(tasks)}", "tasks done", ""),
        (blocked, "tasks blocked", "bad" if blocked else ""),
        (open_q, "open questions", "warn" if open_q else ""),
        (len(open_runs), "open runs", "warn" if open_runs else ""),
        (len(pending), "pending handoffs", "warn" if pending else ""),
    ]
    stats_html = "".join(f'<div class="stat {c}"><span class="n">{e(n)}</span><span class="l">{e(l)}</span></div>' for n, l, c in stats)

    spec_urls = pages.get("specs") or {}
    rows = []
    for s in specs:
        seq = s["seq"]
        cur = PHASES.index(s["phase"]) if s["phase"] in PHASES else len(PHASES)
        track = "".join(
            f'<li class="{"done" if i < cur else ("next" if i == cur else "")}" title="{p}"><i></i><span>{p}</span></li>'
            for i, p in enumerate(PHASES)
        )
        ts = [t for t in tasks if t.get("seq") == seq]
        ts_done = sum(1 for t in ts if t.get("status") == "done")
        q_open = sum(1 for q in questions if q.get("seq") == seq and q.get("status") == "open")
        nxt = next((t for t in sorted(ts, key=lambda t: t.get("ordinal", 0)) if t.get("status") in ("pending", "in_progress")), None)
        handoff = next((h for h in pending if h.get("seq") == seq), None)
        note = (
            f'handoff <code>{e(handoff.get("invocation"))}</code>' if handoff
            else ("fresh session needed for analyze" if s.get("gate") else f'next phase: <b>{e(s["phase"])}</b>')
        )
        rows.append(
            f'<article class="spec"><div class="spec-id"><span class="seq">{seq:03d}</span>'
            f'<span class="slug">{e(s["slug"])}</span></div>'
            f'<h3>{e(s.get("title", s["slug"]))}</h3>'
            f'<ol class="track" aria-label="phase {e(s["phase"])}">{track}</ol>'
            f'<dl><dt>tasks</dt><dd>{f"{ts_done} / {len(ts)} done" if ts else "none yet"}</dd>'
            f'<dt>next task</dt><dd>{e(nxt["local_id"]) if nxt else "—"}</dd>'
            f"<dt>open questions</dt><dd>{q_open}</dd></dl>"
            f'<p class="note">{note}</p>'
            f'<p class="links">{link(spec_urls.get(str(seq)), "Spec page")}</p></article>'
        )

    recent = "".join(
        f'<li><time>{e(ev.get("at", "").replace("T", " ")[:16])}</time><span class="kind">{e(ev.get("kind"))}</span> {e(ev.get("summary"))}</li>'
        for ev in list(reversed(events))[:8]
    )

    page = (HERE / "hub_template.html").read_text()
    for key, val in {
        "{{REPO}}": e(REPO.name),
        "{{BRANCH}}": e(git("rev-parse", "--abbrev-ref", "HEAD")),
        "{{COMMIT}}": e(git("rev-parse", "--short", "HEAD")),
        "{{BUILT}}": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "{{DASHBOARD}}": link(pages.get("dashboard"), "Open dashboard"),
        "{{STATS}}": stats_html,
    }.items():
        page = page.replace(key, val)
    # plane-derived content last, so its text is never treated as a placeholder
    page = page.replace("{{EVENTS}}", recent or '<li class="empty">No events yet.</li>')
    page = page.replace("{{SPECS}}", "".join(rows) or '<p class="empty">No specs chartered yet.</p>')
    out.write_text(page)
    print(json.dumps({"out": str(out), "specs": len(specs)}))


if __name__ == "__main__":
    main()
