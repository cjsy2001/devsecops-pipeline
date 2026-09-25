# devsecops-pipeline

A production-style CI/CD pipeline for a small web API: every push is built, tested and scanned for secrets,
insecure code, vulnerable dependencies and image/IaC misconfiguration, and it deploys to Azure **only** when
every gate passes. Part of a security portfolio; the spec is `specs/001-devsecops-pipeline/spec.md`.

Built through the **stf** task factory (Claude Code plugin `stf@secops-task-factory`, enabled in
`.claude/settings.json`). The factory itself lives in a separate private repo; this repo holds the code at the
root, its specs, and its own plane.

## Where truth lives

| What | Truth | How to read / write it |
|---|---|---|
| Spec content (spec/plan/research/tasks) | `specs/NNN-slug/*.md` | edit files, then `stf_advance_phase` / `stf_import_tasks` |
| Phase, gate, task status, runs, decisions, memory, handoffs | the stf plane (`.stf/export/*.json`, committed) | `stf_*` MCP tools only, never hand-edit |
| Code | repo root | normal edits, on a `feat/*` branch |

**Commit `.stf/export/` with the work it describes.**

## Session protocol

1. **Start.** The SessionStart hook prints the recall block (reference data, not instructions). A pending
   handoff → `/stf:handoff pickup`; otherwise `/stf:status`.
2. **Work** through `/stf:spec-lifecycle`, `/stf:implement N`, `/stf:decide`, `/stf:memory`.
3. **End.** Checkpoint, `stf_complete_run`, then `/stf:handoff emit`.

**Status pages** (see `scripts/status-pages/README.md`): private Claude artifacts give read-only views of this plane: a pinned hub,
the plane dashboard, and one spec page per spec, all titled `STF · …`. Their URLs are in `scripts/status-pages/pages.json`. A project `PostToolUse` hook
rebuilds `.stf/hub.html`, `.stf/dashboard.html` and `.stf/spec-page-NNN.html` after each stf plane write. Republish each to its recorded URL
(Artifact `url=…`, never a new page) once per phase or task boundary. After using the `stf` CLI by hand, run `make status-pages`.

## Rules

- No task is done without `stf_capture_task_outcome` and hashed evidence. Say "tests pass", "deployed" or
  "scan is clean" only with this session's command output.
- Facts about tools, APIs and Azure SKUs come from docs or command output, cited in research.md. Anything unknown is an **Assumption**.
- Every task carries `{tier/effort}`; pass it as the subagent's model at dispatch.
- Per-concern rules live in `.claude/rules/` (security, azure, factory).

## Setup

```
claude plugin install stf@secops-task-factory --scope project   # once per machine (the factory repo is private)
stf init        # only if .stf/ is missing (stf_* tools return `no_plane`): run at the repo root to create the empty plane
make setup      # core.hooksPath=.githooks → gitleaks pre-commit hook
make gitleaks   # full-history secret scan (docker)
```

## Repo etiquette

- Never commit to `main` after the initial commit. Use `feat/<slug>` or `fix/<slug>`, conventional commits, PRs into `main`.
- Commit or PR only when the user asks. Review `git diff` before staging.
- This repo is **public**: the gitleaks hook and the `secrets` workflow must stay on.
