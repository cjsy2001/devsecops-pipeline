---
paths: [".stf/**", "specs/**"]
---
# Factory (stf plane) rules

- `.stf/export/` is written only by the stf server/CLI. Never hand-edit it. A hand edit to a handoff is
  detected as tampering; an edit elsewhere is simply a lie in git history.
- Identity is `seq` (spec) + `localId` (task). IDs like D-/OQ-/ALT-/EV-/MEM-/H- are minted by the server.
- The tasks.md grammar is strict (see the `stf:spec-lifecycle` skill). If the parser rejects a line, fix the line.
- Plugin bugs are fixed in the factory repo (cjsy2001/secops-task-factory), not worked around here.
