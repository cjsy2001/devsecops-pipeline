# devsecops-pipeline

A CI/CD pipeline for a small web API where security is enforced automatically and fails closed: every push is
built, unit-tested, and scanned for leaked secrets, insecure code, vulnerable dependencies and image/IaC
misconfiguration, and it deploys to Azure only when every gate passes. Each gate can be demonstrated with a
deliberately vulnerable commit that gets blocked.

**Status:** specification. See [`specs/001-devsecops-pipeline/spec.md`](specs/001-devsecops-pipeline/spec.md).

## Planned gates

| Gate | Tool |
|---|---|
| Secrets | Gitleaks (+ TruffleHog verified-only) |
| SAST | Semgrep → GitHub code scanning (SARIF) |
| Dependencies | Trivy fs, Dependabot |
| Image | Trivy image, before push |
| IaC | Trivy config / Checkov |
| Deploy | Azure via GitHub OIDC, only on `main`, only when every gate passes |

## Local setup

```
make setup          # enable the gitleaks pre-commit hook
make gitleaks       # full-history secret scan (docker)
make status-pages   # rebuild the private STF hub, plane dashboard and spec pages (see scripts/status-pages/README.md)
```
