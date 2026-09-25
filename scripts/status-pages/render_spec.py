"""Render one spec's markdown artefacts + the committed stf plane export into a single read-only HTML page.

Usage: uv run --no-project --with markdown==3.7 python scripts/status-pages/render_spec.py [--seq N] [--out PATH]
Default output: .stf/spec-page-NNN.html (gitignored). Reads only; never writes to specs/ or .stf/export/.
"""
import argparse
import html
import json
import re
import subprocess
from pathlib import Path

import markdown
from markdown.extensions.toc import slugify as default_slugify

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
EXPORT = REPO / ".stf/export"

# (tab key, label, file relative to the spec dir); tabs appear only for files that exist
DOCS = [
    ("spec", "Spec", "spec.md"),
    ("plan", "Plan", "plan.md"),
    ("research", "Research", "research.md"),
    ("datamodel", "Data model", "data-model.md"),
    ("tasks", "Tasks", "tasks.md"),
]
REF_RE = re.compile(r"\b(FR|NFR|SC|D|ALT|A|Q|OQ)-(\d{3})\b|\bUS(\d)\b|\bR-(\d{2})\b|\bT(\d{3})\b")
PHASES = ["specify", "clarify", "plan", "tasks", "analyze"]


def load(name):
    p = EXPORT / name
    return json.loads(p.read_text()) if p.exists() else []


def ref_target(m):
    kind, num, us, r, t = m.groups()
    if r:
        return f"r-{r}", "R"
    if us:
        return f"us{us}", "US"
    if t:
        return f"t{t}", "T"
    return f"{kind.lower()}-{num}", kind


def linkify(fragment):
    """Wrap ID references in text nodes (outside code/pre/a) with in-page links."""
    out, depth = [], 0
    for part in re.split(r"(<[^>]+>)", fragment):
        if part.startswith("<"):
            tag = re.match(r"</?\s*(\w+)", part)
            if tag and tag.group(1).lower() in ("code", "pre", "a"):
                depth += -1 if part.startswith("</") else 1
            out.append(part)
        elif depth > 0:
            out.append(part)
        else:
            def repl(m):
                target, kind = ref_target(m)
                return f'<a class="ref ref-{kind}" href="#{target}">{m.group(0)}</a>'

            out.append(REF_RE.sub(repl, part))
    return "".join(out)


def render(key, text):
    md = markdown.Markdown(
        extensions=["tables", "fenced_code", "toc", "sane_lists"],
        extension_configs={"toc": {"slugify": lambda v, s: f"{key}-" + default_slugify(v, s), "toc_depth": "2-3"}},
    )
    body = md.convert(text)
    toc = md.toc_tokens

    # mermaid fences -> native <pre class="mermaid">
    body = re.sub(
        r'<pre><code class="language-mermaid">(.*?)</code></pre>',
        lambda m: f'<div class="diagram"><pre class="mermaid">{m.group(1)}</pre></div>',
        body,
        flags=re.S,
    )

    # <!-- Source: … --> trace markers -> visible "Traces to" line
    def trace(m):
        chips = " ".join(f"<span>{html.escape(r.strip())}</span>" for r in m.group(1).split(","))
        return f'<p class="trace"><span class="trace-label">Traces to</span> {chips}</p>'

    body = re.sub(r"<!--\s*Source:\s*(.*?)\s*-->", trace, body)
    # anchors on definitions: list items starting with a bold ID, R-NN / US headings, inline assumptions, tasks
    body = re.sub(
        r"<li>(<p>)?<strong>((?:FR|NFR|SC|A|Q)-\d{3})([^<]*)</strong>",
        lambda m: f'<li id="{m.group(2).lower()}">{m.group(1) or ""}<strong>{m.group(2)}{m.group(3)}</strong>',
        body,
    )
    for level, pat in (("h2", r"R-\d{2}"), ("h3", r"US\d")):
        body = re.sub(
            rf'<{level} id="([^"]+)">({pat})',
            lambda m, lv=level: f'<{lv} id="{m.group(2).lower()}"><span class="anchor-alias" id="{m.group(1)}"></span>{m.group(2)}',
            body,
        )
    body = re.sub(
        r"<strong>Assumption (A-\d{3})",
        lambda m: f'<strong id="{m.group(1).lower()}">Assumption {m.group(1)}',
        body,
    )
    body = re.sub(
        r"<li>(<p>)?\[( |x|X)\] (T\d{3})",
        lambda m: f'<li id="{m.group(3).lower()}" class="task task-{"done" if m.group(2).strip() else "open"}">'
        f'{m.group(1) or ""}<span class="box">{"✓" if m.group(2).strip() else ""}</span> {m.group(3)}',
        body,
    )
    body = body.replace("<table>", '<div class="tablewrap"><table>').replace("</table>", "</table></div>")
    # the page header carries the doc's own H1 + meta line
    body = re.sub(r"^<h1[^>]*>.*?</h1>\s*", "", body, count=1, flags=re.S)
    body = re.sub(r"^<blockquote>\s*<p>seq:.*?</blockquote>\s*", "", body, count=1, flags=re.S)
    return linkify(body), toc


def toc_html(tokens):
    return '<ol class="toc">' + "".join(
        f'<li><a href="#{t["id"]}">{html.escape(html.unescape(t["name"]))}</a></li>' for t in tokens
    ) + "</ol>"


def git_branch():
    try:
        return subprocess.run(
            ["git", "-C", str(REPO), "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seq", type=int, default=1)
    ap.add_argument("--out")
    args = ap.parse_args()

    spec_row = next((s for s in load("specs.json") if s.get("seq") == args.seq), None)
    if spec_row is None:
        raise SystemExit(f"spec seq {args.seq} not found in {EXPORT}/specs.json")
    rel_dir = f"specs/{args.seq:03d}-{spec_row['slug']}"
    spec_dir = REPO / rel_dir
    out = Path(args.out) if args.out else REPO / f".stf/spec-page-{args.seq:03d}.html"

    decisions = [d for d in load("decisions.json") if d.get("seq") == args.seq]
    alts = {a["local_id"]: a for a in load("alternatives.json") if a.get("seq") == args.seq}
    questions = [q for q in load("questions.json") if q.get("seq") == args.seq]
    hashes = {}
    for phase_files in (spec_row.get("artefacts") or {}).values():
        for path, digest in phase_files.items():
            hashes[Path(path).name] = digest  # later phases overwrite earlier ones

    docs = list(DOCS)
    for report in sorted((spec_dir / "analysis").glob("*.md")) if (spec_dir / "analysis").is_dir() else []:
        docs.append(("analysis", "Analysis", f"analysis/{report.name}"))

    tabs, panels = [], []
    for key, label, fname in docs:
        src = spec_dir / fname
        if not src.exists():
            continue
        body, toc = render(key, src.read_text())
        digest = hashes.get(Path(fname).name, "")
        meta = f'<code title="sha256 recorded by stf_advance_phase">sha256 {digest[:12]}…</code>' if digest else ""
        tabs.append(f'<a class="tab" role="tab" href="#{key}" data-panel="{key}">{label}</a>')
        panels.append(
            f'<section class="panel" id="{key}" data-panel="{key}" role="tabpanel">'
            f'<aside class="side"><p class="side-file">{rel_dir}/<b>{fname}</b></p>{meta}{toc_html(toc)}</aside>'
            f'<article class="doc">{body}</article></section>'
        )

    cards = []
    for d in decisions:
        rej = "".join(
            f'<li id="{a.lower()}"><b>{a}</b> {html.escape(alts[a]["option"])}</li>'
            for a in d.get("rejects", [])
            if a in alts
        )
        res = ", ".join(d.get("resolves", []))
        cards.append(
            f'<article class="decision" id="{d["local_id"].lower()}">'
            f'<header><span class="did">{d["local_id"]}</span><h3>{html.escape(d["title"])}</h3>'
            f'<span class="pill pill-{d["status"]}">{d["status"]}</span></header>'
            f'<p class="statement">{linkify(html.escape(d["statement"]))}</p>'
            f'<dl><dt>Why</dt><dd>{linkify(html.escape(d["rationale"]))}</dd>'
            + (f'<dt>Consequences</dt><dd>{linkify(html.escape(d["consequences"]))}</dd>' if d.get("consequences") else "")
            + (f"<dt>Resolves</dt><dd>{res}</dd>" if res else "")
            + (f'<dt>Rejected</dt><dd><ul class="alts">{rej}</ul></dd>' if rej else "")
            + "</dl></article>"
        )
    used = {a for d in decisions for a in d.get("rejects", [])}
    orphans = [a for k, a in alts.items() if k not in used]
    orphan_html = (
        '<h2 id="other-alternatives">Alternatives not tied to a decision</h2><ul class="alts">'
        + "".join(
            f'<li id="{a["local_id"].lower()}"><b>{a["local_id"]}</b> {html.escape(a["option"])} '
            f'<span class="pill pill-{a["verdict"]}">{a["verdict"]}</span>: {linkify(html.escape(a.get("rationale") or ""))}</li>'
            for a in orphans
        )
        + "</ul>"
        if orphans
        else ""
    )
    qrows = "".join(
        f'<tr id="{q["local_id"].lower()}"><td><code>{q["local_id"]}</code></td><td>{q.get("spec_ref") or ""}</td>'
        f'<td>{html.escape(q["question"])}</td><td><span class="pill pill-{q["status"]}">{q["status"]}</span></td></tr>'
        for q in questions
    )
    tabs.append('<a class="tab" role="tab" href="#decisions" data-panel="decisions">Decisions</a>')
    panels.append(
        '<section class="panel" id="decisions" data-panel="decisions" role="tabpanel">'
        '<aside class="side"><p class="side-file">.stf/export/<b>decisions.json</b></p>'
        f'<p class="side-note">{len(decisions)} decisions · {len(alts)} alternatives · {len(questions)} questions, '
        "read from the committed plane export.</p></aside>"
        '<article class="doc"><h2 id="decisions-list">Decisions</h2><div class="decisions">'
        + "".join(cards)
        + '</div><h2 id="questions-list">Open questions</h2><div class="tablewrap"><table><thead><tr><th>ID</th>'
        "<th>Spec ref</th><th>Question</th><th>Status</th></tr></thead><tbody>"
        + qrows
        + "</tbody></table></div>"
        + orphan_html
        + "</article></section>"
    )

    cur = spec_row.get("phase", "specify")
    cur_i = PHASES.index(cur) if cur in PHASES else len(PHASES)  # "done" marks every phase complete
    steps = "".join(
        f'<li class="step step-{"done" if i < cur_i else ("next" if i == cur_i else "todo")}"><span class="dot"></span>{p}</li>'
        for i, p in enumerate(PHASES)
    )

    page = (
        (HERE / "template.html").read_text()
        .replace("{{TITLE}}", html.escape(spec_row.get("title", spec_row["slug"])))
        .replace("{{SUMMARY}}", html.escape(spec_row.get("summary", "")))
        .replace("{{SEQ}}", f"{args.seq:03d}")
        .replace("{{SLUG}}", html.escape(spec_row["slug"]))
        .replace("{{SPEC_DIR}}", rel_dir)
        .replace("{{BRANCH}}", html.escape(git_branch()))
        .replace("{{STEPS}}", steps)
        .replace("{{PHASE}}", html.escape(cur))
        .replace("{{UPDATED}}", html.escape(spec_row.get("updated_at", "")))
        # document content goes in last so text inside the docs is never treated as a placeholder
        .replace("{{TABS}}", "".join(tabs))
        .replace("{{PANELS}}", "".join(panels))
    )
    out.write_text(page)
    print(json.dumps({"out": str(out), "seq": args.seq, "phase": cur, "tabs": [t for t, *_ in docs if (spec_dir / _[1]).exists()]}))


if __name__ == "__main__":
    main()
