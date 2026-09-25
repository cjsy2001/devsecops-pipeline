# Security rules (this is a security portfolio: the repo itself must pass its own gates)

- **Secrets:** never in code, tests, docs, commits, the plane, or memories. Use GitHub Actions secrets or OIDC,
  Azure Key Vault, and `.env` files (gitignored, with a committed `.env.example` holding placeholders). The gitleaks
  pre-commit hook and the CI job must stay on. Never bypass them with `--no-verify`.
- **Demo defects (FR-011):** a deliberately leaked "secret" must be a fake that is obviously not a live credential,
  and lives only on a `demo/*` branch or patch, never on `main`.
- **Least privilege:** containers run as non-root with a read-only rootfs where possible, dropped capabilities,
  and `no-new-privileges`. Azure identities get scoped roles, never Owner or Contributor at subscription scope.
- **Pin versions:** GitHub Actions pinned to a major tag at minimum (a SHA for third-party actions), base
  images pinned by tag (a digest for release builds), and a Terraform provider lockfile committed.
- **Gates fail closed:** a scanner that errors must fail the job, not skip it. No `continue-on-error` on security steps.
