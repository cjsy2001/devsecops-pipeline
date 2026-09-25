# DevSecOps Pipeline

> seq: 001 · devsecops-pipeline · status: draft · 2026-09-25

## Overview

**Problem.** Security checks bolted on after the fact get skipped, run late, or fail open. This project shows the
opposite: a CI/CD pipeline for a small web API where every security gate runs on every push, blocks on
findings, fails closed when a scanner itself errors, and is the only path to production on Azure.

**Who it's for.** Reviewers of a security portfolio (hiring managers, security engineers), and the author as a
reusable reference pipeline.

**Portfolio-ready means:** a reader can clone the repo, read the README, open the Actions tab and see green
runs on `main`, open a `demo/*` pull request per gate and see it blocked with the finding surfaced (PR check,
SARIF in code scanning), hit the deployed API's health endpoint, and tear the Azure footprint down with one
documented command.

## User Scenarios

### US1: Every push is built, tested and scanned (P1)
- **Given** a developer pushes a commit or opens a PR against `main`,
- **When** the pipeline runs,
- **Then** the API is built, its unit tests run, and every security gate (secrets, SAST, dependencies, image,
  IaC) runs and reports a pass/fail status check on the commit.

### US2: A vulnerable change is blocked (P1)
- **Given** a PR that introduces a fake leaked secret, an insecure code pattern, a vulnerable dependency, an
  image with a known-vulnerable package, or a misconfigured Terraform resource,
- **When** the pipeline runs,
- **Then** the matching gate fails, the PR cannot be merged (required status checks), and the finding is visible
  in the PR checks and, where the tool emits SARIF, in GitHub code scanning.

### US3: Only a fully green `main` deploys to Azure (P1)
- **Given** a commit lands on `main` and every gate passed,
- **When** the deploy job runs,
- **Then** it authenticates to Azure via GitHub OIDC (no stored credentials), applies the Terraform, deploys the
  scanned image, and the API's health endpoint returns 200.
- **And given** any gate failed, **then** the deploy job does not run.

### US4: A scanner error fails closed (P2)
- **Given** a scanner step errors (tool crash, download failure, bad config) rather than reporting findings,
- **When** the pipeline runs,
- **Then** that gate's job fails and deploy is blocked; nothing is silently skipped.

### US5: The Azure footprint is cheap and disposable (P2)
- **Given** the stack is deployed,
- **When** the owner runs the documented teardown command,
- **Then** every resource of this spec is removed (single resource group), and the README states the idle-month cost.

## Functional Requirements

- **FR-001** The repo MUST contain a small HTTP API with at least a `GET /health` endpoint and one business endpoint, plus unit tests for both.
- **FR-002** The pipeline MUST build the API and run its unit tests on every push and on every PR to `main`; a failing test MUST fail the pipeline.
- **FR-003** A secrets gate MUST scan the full git history with Gitleaks on every push/PR and fail on any finding; the local pre-commit hook MUST stay enabled.
- **FR-004** A SAST gate MUST run Semgrep on every push/PR, upload SARIF to GitHub code scanning, and fail on findings at or above the blocking severity (see FR-012).
- **FR-005** A dependency gate MUST scan the API's dependency manifest/lockfile with Trivy (fs mode) and fail on vulnerabilities at or above the blocking severity; Dependabot MUST be configured for the app ecosystem and GitHub Actions.
- **FR-006** The container image MUST be built from a pinned base image, run as non-root, and be scanned by Trivy (image mode) **before** it is pushed to a registry; a failing scan MUST prevent the push.
- **FR-007** An IaC gate MUST scan the Terraform (and Dockerfile) for misconfiguration with Trivy config and/or Checkov and fail on findings at or above the blocking severity.
- **FR-008** Infrastructure MUST be defined in Terraform ≥ 1.6 with remote state in an Azure Storage backend (blob-lease locking) and a committed provider lockfile.
- **FR-009** Deployment MUST run only on `main`, only after every gate job succeeded (job dependency), and authenticate via GitHub OIDC federated credentials to an identity scoped to the spec's resource group.
- **FR-010** After deploy, a smoke test MUST call the deployed `GET /health` and fail the pipeline on a non-200 response.
- **FR-011** For each gate (secrets, SAST, dependencies, image, IaC) the repo MUST provide a demo defect on a `demo/*` branch or patch that makes exactly that gate fail; any demo "secret" MUST be an obviously fake value, and no demo defect may reach `main`.
- **FR-012** Blocking severity per gate MUST be defined in one place and applied consistently: findings of severity **HIGH or CRITICAL** block. Trivy vulnerability scans ignore unfixed vulnerabilities, and any other suppression needs a justified ignore-file entry (D-002).
- **FR-013** Every security step MUST fail closed: no `continue-on-error`, no `|| true`, and a tool error exits non-zero.
- **FR-014** `main` MUST be protected: PRs required, and every gate job plus build/test registered as a required status check.
- **FR-015** All Azure resources MUST live in one resource group named per the decided convention and carry the tags `project`, `spec` and `owner`. Region **eastus**, the owner's personal pay-as-you-go subscription, naming prefix `stf`, resource group `rg-stf-devsecops-pipeline`. Subscription, tenant and client IDs live only in GitHub secrets/variables (D-001).
- **FR-016** The README MUST document setup, the gate table, how to run each demo, the idle-month cost and a one-command teardown.
- **FR-017** The production deploy trigger MUST follow the decided policy: deploy **automatically** on push to `main` once every gate job succeeds, with no manual-approval environment. Images go to GitHub Container Registry only after the image scan passes, and are deployed by digest (D-003).

## Non-Functional Requirements

- **NFR-001 (Security)** No secrets in code, tests, docs, commits or workflow files; CI uses OIDC and GitHub secrets/variables only. Workflows declare least-privilege `permissions:`.
- **NFR-002 (Supply chain)** First-party GitHub Actions pinned to at least a major tag, third-party actions pinned to a full commit SHA; base images pinned by tag (by digest for the deployed image).
- **NFR-003 (Least privilege)** The container runs as non-root, with a read-only root filesystem where the platform allows it. The deploy identity has no Owner or Contributor role at subscription scope.
- **NFR-004 (Cost)** The idle-month cost of the deployed stack SHOULD be under USD 5, and it MUST be recorded in plan.md before the first deploy.
- **NFR-005 (Speed)** A full PR pipeline run (build, test, all gates, no deploy) SHOULD finish in under 10 minutes on GitHub-hosted runners.
- **NFR-006 (Operability)** Teardown removes every resource of this spec except the Terraform state backend, which has its own documented teardown.

## Success Criteria

- **SC-001** `gh run list --branch main --workflow <ci> --limit 1 --json conclusion` returns `success` on the final `main` commit.
- **SC-002** For each of the 5 gates, its `demo/*` PR shows that gate's check as `failure` and deploy `skipped` (`gh pr checks <n>`): 5/5.
- **SC-003** `curl -s -o /dev/null -w '%{http_code}' https://<app-fqdn>/health` returns `200` after deploy.
- **SC-004** `grep -rnE 'continue-on-error|\|\| *true' .github/workflows/` returns no match on a security step.
- **SC-005** `make gitleaks` exits 0 on `main` (full history clean).
- **SC-006** `az role assignment list --assignee <deploy-client-id> --all` shows no role at subscription scope.
- **SC-007** `gh api repos/{owner}/{repo}/branches/main/protection` lists every gate job and build/test as required checks.
- **SC-008** After the teardown command, `az group exists -n <rg>` returns `false`.
- **SC-009** Deliberately breaking a scanner (for example an invalid config path on a demo branch) makes that gate's job fail, not pass or skip.

## Key Entities

None. The API is stateless with no persistent data store.

## Out of Scope

- DAST (ZAP) and runtime protection. A possible follow-up spec.
- Multiple environments (dev/staging/prod). There is one deployed environment.
- Custom domain, TLS certificate management beyond the platform default, and WAF.
- Signing and SBOM attestation (cosign/SLSA). A possible follow-up spec.
- Self-hosted runners.

## Assumptions

- **A-001** The API is Python 3.12 with FastAPI, tested with pytest and dependencies locked (`requirements.txt` with hashes, or uv lock). Chosen for brevity. The pipeline, not the app, is the subject.
- **A-002** The compute target is Azure Container Apps on the consumption plan (per `.claude/rules/azure.md`: prefer low tiers). Pricing is to be verified in research.md.
- **A-003** ~~Images go to GitHub Container Registry.~~ Superseded by D-003 (clarify). What remains an assumption is how Container Apps pulls from GHCR, which is to be verified in research.md.
- **A-004** CI/CD is GitHub Actions on GitHub-hosted `ubuntu-latest` runners, and the repo is public (so code scanning/SARIF is free).
- **A-005** Terraform state lives in a separate, pre-created storage account (bootstrap script) outside the spec's resource group, so the teardown doesn't destroy its own state.
- **A-006** The IaC gate uses Trivy config as the primary scanner. Checkov is optional if Trivy's coverage proves sufficient (to be decided in plan).
- **A-007** Owner tag value = repo owner handle; `spec` tag = `001-devsecops-pipeline`; `project` tag = `devsecops-pipeline`.

## Open Questions

- **Q-001** Azure region, subscription and naming prefix (FR-015). Resolved: D-001.
- **Q-002** Blocking severity threshold for SAST, dependency, image and IaC gates (FR-012). Resolved: D-002.
- **Q-003** Production deploy trigger (FR-017), plus the image registry. Resolved: D-003.

## Clarifications

### Session 2026-09-25

- Q: Which Azure region? → A: eastus. Resource group `rg-stf-devsecops-pipeline`, prefix `stf` (source: user; D-001)
- Q: Which subscription? → A: personal pay-as-you-go. IDs only in GitHub secrets/variables (source: user; D-001)
- Q: Which severities block the SAST/dependency/image/IaC gates? → A: HIGH + CRITICAL (source: user; D-002)
- Q: Deploy trigger and image registry? → A: auto deploy on green `main`, images on GHCR (source: user; D-003)
