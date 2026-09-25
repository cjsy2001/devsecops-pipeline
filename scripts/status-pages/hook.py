"""PostToolUse hook: after an stf plane write, rebuild the local status pages and remind Claude to republish them.

Pages (URLs in pages.json): the hub (render_hub.py), the plane dashboard (`stf dashboard`) and one spec page per spec (render_spec.py).
Wired in this repo's .claude/settings.json only. Never blocks or fails the tool call: every error path exits 0.
Publishing stays with Claude (the Artifact tool); this hook only rebuilds the local HTML files.
"""
import glob
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
PAGES = HERE / "pages.json"  # {"hub": "<url>", "dashboard": "<url>", "specs": {"<seq>": "<url>"}}
TOOL_PREFIX = "mcp__plugin_stf_stf__"
DASHBOARD_OUT = REPO / ".stf/dashboard.html"
HUB_OUT = REPO / ".stf/hub.html"


def emit(context=None, message=None):
    out = {"suppressOutput": True}
    if context:
        out["hookSpecificOutput"] = {"hookEventName": "PostToolUse", "additionalContext": context}
    if message:
        out["systemMessage"] = message
    print(json.dumps(out))
    sys.exit(0)


def stf_binary():
    """The stf CLI this project's plugin install uses; newest cached copy as a fallback."""
    try:
        installs = json.loads(Path("~/.claude/plugins/installed_plugins.json").expanduser().read_text())
        for entry in installs.get("plugins", {}).get("stf@secops-task-factory", []):
            if Path(entry.get("projectPath", "")).resolve() == REPO:
                candidate = Path(entry["installPath"]) / "bin/stf"
                if candidate.exists():
                    return str(candidate)
    except (OSError, ValueError, KeyError, TypeError):
        pass
    cached = sorted(glob.glob(os.path.expanduser("~/.claude/plugins/cache/secops-task-factory/stf/*/bin/stf")), key=os.path.getmtime)
    return cached[-1] if cached else None


def run(cmd, timeout):
    """Run a command in the repo; return (ok, stdout-or-error)."""
    try:
        proc = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    if proc.returncode != 0:
        return False, ((proc.stderr or proc.stdout).strip().splitlines() or ["exit " + str(proc.returncode)])[-1]
    return True, proc.stdout


def target(label, path, url):
    if url:
        return f"{label}: rebuilt {path}; republish with Artifact publish file_path={path} url={url}"
    return f"{label}: rebuilt {path}; no page recorded yet (add its URL to scripts/status-pages/pages.json after the first publish)"


def main():
    manual = sys.argv[1:] == ["--refresh"]  # `make status-pages`: rebuild everything, print plain text
    if manual:
        event = {"tool_name": TOOL_PREFIX + "manual_refresh", "tool_input": {}, "cwd": str(REPO)}
        os.environ["CLAUDE_PROJECT_DIR"] = str(REPO)
    else:
        try:
            event = json.load(sys.stdin)
        except ValueError:
            sys.exit(0)

    # Scope guards: only this repo's plane, only stf tools. Anything else is a silent no-op.
    project = Path(os.environ.get("CLAUDE_PROJECT_DIR") or event.get("cwd") or ".").resolve()
    if project != REPO or not (REPO / ".stf/export/specs.json").exists():
        sys.exit(0)
    tool = event.get("tool_name", "")
    if not tool.startswith(TOOL_PREFIX):
        sys.exit(0)

    tool_input = event.get("tool_input") or {}
    seqs = [tool_input["seq"]] if isinstance(tool_input.get("seq"), int) else None
    if seqs is None:  # e.g. stf_complete_run / stf_charter_spec carry no seq: refresh every spec
        try:
            seqs = [s["seq"] for s in json.loads((REPO / ".stf/export/specs.json").read_text())]
        except (OSError, ValueError, KeyError):
            sys.exit(0)

    try:
        pages = json.loads(PAGES.read_text()) if PAGES.exists() else {}
    except ValueError:
        pages = {}

    lines, errors = [], []

    stf = stf_binary()
    ok, out = run([stf, "dashboard", str(DASHBOARD_OUT)], 60) if stf else (False, "stf CLI not found in the plugin cache")
    if ok:
        # the plugin titles every dashboard "STF Plane Dashboard"; name it per repo so STF pages group in the gallery
        page = DASHBOARD_OUT.read_text()
        DASHBOARD_OUT.write_text(page.replace("<title>STF Plane Dashboard</title>", f"<title>STF · {REPO.name} dashboard</title>", 1))
        lines.append(target("dashboard", DASHBOARD_OUT, pages.get("dashboard")))
    else:
        errors.append(f"dashboard: {out}")

    for seq in seqs:
        ok, out = run(
            ["uv", "run", "--quiet", "--no-project", "--with", "markdown==3.7",
             "python", str(HERE / "render_spec.py"), "--seq", str(seq)],
            90,
        )
        if not ok:
            errors.append(f"spec {seq}: {out}")
            continue
        out_path = json.loads(out.strip().splitlines()[-1])["out"]
        lines.append(target(f"spec {seq:03d}", out_path, (pages.get("specs") or {}).get(str(seq))))

    # the hub links every page above; it is stdlib-only and rebuilt last so it reflects the same plane state
    ok, out = run([sys.executable, str(HERE / "render_hub.py"), "--out", str(HUB_OUT)], 30)
    if ok:
        lines.append(target("hub", HUB_OUT, pages.get("hub")))
    else:
        errors.append(f"hub: {out}")

    context = None
    if lines:
        context = (
            f"stf plane changed ({tool.removeprefix(TOOL_PREFIX)}). Status pages rebuilt:\n- " + "\n- ".join(lines)
            + "\nRepublish once at the next phase or task boundary, not after every write. The pages are private; update the recorded URLs, never publish new ones."
        )
    if manual:
        print("\n".join(lines + [f"FAILED {e}" for e in errors]))
        sys.exit(1 if errors else 0)
    emit(context, f"status-pages hook failed: {'; '.join(errors)}" if errors else None)


if __name__ == "__main__":
    main()
