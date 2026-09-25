# Azure rules

- Auth from CI uses GitHub OIDC federated credentials (`azure/login` with client-id, tenant-id and subscription-id).
  No client secrets or publish profiles.
- Terraform ≥ 1.6 (or OpenTofu). The local machine has 0.13.7, so install a current version as a Setup task. State lives in
  an Azure Storage backend with a Blob lease lock, never in git.
- Tag every resource with `project`, `spec` and `owner`, and put everything in per-spec resource groups (`rg-stf-<slug>`) so a spec can be destroyed cleanly.
- Cost: prefer free or low tiers (Container Apps consumption, Functions consumption), and document a
  teardown command in the README. Before deployment, the plan records what an idle month costs.
- Region, subscription and naming prefix are decided at clarify time and recorded as `D-NNN`. Don't guess them.
