# Status pages

Private Claude artifacts show this repo's stf state in a browser. All of them are **read-only views**. The truth stays in
`specs/` and `.stf/export/`, and every change still goes through the `stf_*` tools.

**Start at the hub.** It's pinned to the claude.ai sidebar and links to every other page. Every page title starts with
`STF ·`, so they also sort and search together in the gallery (claude.ai/code/artifacts) and in `/artifacts`. Artifacts have no
folders or groups; the hub and the shared prefix stand in for them.

| Page | Shows | Built by | Local file (gitignored) |
|---|---|---|---|
| **Hub** (`STF · devsecops-pipeline`) | plane totals, each spec's phase, links to every page below, recent events | `render_hub.py` (stdlib only) | `.stf/hub.html` |
| Plane dashboard | every spec's phase, tasks, open questions, decisions, handoffs, memories, runs, recent events | `stf dashboard` (the plugin's CLI) | `.stf/dashboard.html` |
| Spec page (one per spec) | spec / plan / research / tasks rendered, trace markers, linked FR/D/A refs, decisions | `render_spec.py` | `.stf/spec-page-NNN.html` |

The artifact URLs live in [`pages.json`](pages.json). The pages are private, so only their owner, or people it's shared with
from the page's Share menu, can open them. Record URLs **without** the `?sk=…` share key; this repo is public.

## How a refresh happens

Only Claude can publish an artifact, so a refresh has two steps: **rebuild** the local HTML, then **republish** it to the
recorded URL.

1. **Rebuild (automatic).** The project `PostToolUse` hook in `.claude/settings.json` runs [`hook.py`](hook.py) after every
   stf plane write (`stf_advance_phase`, `stf_capture_*`, `stf_import_tasks`, `stf_set_task_status`, `stf_checkpoint`,
   `stf_complete_run`, `stf_handoff_*`, `stf_verify`, …). It rebuilds the dashboard, the affected spec page and the hub, then tells
   Claude which files changed and which URLs to republish them to.
2. **Republish (Claude, once per phase or task boundary).** Claude publishes each rebuilt file to its recorded URL:
   - Artifact publish `file_path=.stf/hub.html`, `url=<pages.json hub>`
   - Artifact publish `file_path=.stf/dashboard.html`, `url=<pages.json dashboard>`
   - Artifact publish `file_path=.stf/spec-page-001.html`, `url=<pages.json specs.1>`

   In a new conversation Claude first reads the artifact (Artifact `read` with the URL), then publishes with `url`.
   Publishing without `url` creates a new page instead of updating the recorded one.

## Refresh by hand

Use this after running the `stf` CLI yourself (for example `stf verify` or `stf import-tasks`), which doesn't fire the hook:

```
make status-pages      # rebuilds the hub, the dashboard and every spec page, prints what to republish
```

Then ask Claude, for example: *"republish the status pages"*. The individual commands are:

```
python3 scripts/status-pages/render_hub.py                                         # hub
stf dashboard .stf/dashboard.html                                                   # plane dashboard
uv run --no-project --with markdown==3.7 python scripts/status-pages/render_spec.py --seq 1   # spec page for spec 001
```

## Adding a page

- **A new spec** gets its spec page rebuilt automatically. After Claude's first publish of `.stf/spec-page-NNN.html` (title
  `STF · Spec NNN <slug>`), add its URL under `specs` in `pages.json`. Later sessions then update that page instead of
  creating another, and the hub links to it on its next rebuild.
- **Another repo** needs its own copy of this folder and hook. Planes are per repo, and nothing syncs between them (factory
  decision D-004), so a page shows only the repo it was built from.

## Scope and safety

- The hook is defined only in this repo's `.claude/settings.json`, and its matcher only fires on the stf plugin's
  plane-write tools. The script also exits silently unless the session's project directory is this repo.
- It never fails a tool call. Errors show as a one-line `status-pages hook failed: …` notice.
- The pages contain spec text and plane records only. Never put credentials in the plane; the security rules already forbid it.
- To switch the hook off, remove the `PostToolUse` entry from `.claude/settings.json`, or review it in `/hooks`.
