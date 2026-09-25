# Research: DevSecOps Pipeline

> seq: 001 · devsecops-pipeline · 2026-09-25 · inputs: spec.md (clarified), D-001…D-003

Facts come from official docs, the Azure Retail Prices API, `gh api` release lookups, or local command output
gathered on 2026-09-25. Anything that could not be verified is marked **Assumption** and has a task that checks it.

## Local environment (command output, 2026-09-25)

| Tool | Local version | Note |
|---|---|---|
| docker | 29.8.0 | runs gitleaks/trivy/semgrep containers locally |
| terraform | **0.13.7** | too old for FR-008 (≥ 1.6). A Setup task installs 1.16.4 |
| az | 2.79.0 | used by the bootstrap and teardown scripts |
| gh | 2.4.0 | old but `gh api` works; used for branch protection |
| uv | 0.9.7 | app toolchain |
| python3 | 3.10.12 | local only; the app targets 3.12 via uv / base image |
| trivy, semgrep | not installed | run as containers (R-03) |

`gh repo view --json nameWithOwner,isPrivate` → `{"isPrivate":false,"nameWithOwner":"cjsy2001/devsecops-pipeline"}`.

---

## R-01 App stack: Python 3.12 + FastAPI + uv lockfile
<!-- Source: spec.md#FR-001, spec.md#FR-005 -->

- **Decision:** FastAPI app, pytest tests, dependencies locked in `uv.lock` (D-005).
- **Rationale:** Trivy reads `uv.lock` including transitive dependencies, whereas for `requirements.txt` "Trivy only
  parses version specifiers with `==` comparison operator" and skips transitive dependencies
  (https://trivy.dev/latest/docs/coverage/language/python/). Dependabot supports `package-ecosystem: "uv"`
  (https://docs.github.com/en/code-security/dependabot/working-with-dependabot/dependabot-options-reference).
  uv's documented Docker pattern is a multi-stage build that runs `uv sync --locked`, copies only `.venv` into the runtime stage, and sets
  `UV_COMPILE_BYTECODE=1` (https://docs.astral.sh/uv/guides/integration/docker/).
- **Alternatives:** requirements.txt with hashes (rejected: weaker transitive scan); poetry (no advantage over uv here).

## R-02 Base image
<!-- Source: spec.md#FR-006, spec.md#NFR-002 -->

- **Decision:** `python:3.12-slim-trixie`, pinned by tag in the Dockerfile and by digest for the deployed build.
  Also `ghcr.io/astral-sh/uv:<pinned version>` in the builder stage only.
- **Fact:** on Docker Hub (2026-09-19), `python:3.12-slim` currently resolves to the same digest as `3.12-slim-trixie`,
  `sha256:2f17fc044b579bab302c2e8054d3a686e2cb9a83de48e70534b94cd8ebbe06a9`. `3.12-slim-bookworm` is still published.
- **Alternatives:** distroless python (rejected: harder uv integration, marginal gain for a demo); alpine (musl wheel issues).

## R-03 Scanners run as pinned containers, not third-party actions
<!-- Source: spec.md#FR-003, spec.md#FR-004, spec.md#FR-005, spec.md#FR-006, spec.md#FR-007, spec.md#NFR-002 -->

- **Decision (D-004):** Gitleaks, Trivy and Semgrep run with `docker run` on official images pinned by digest. No
  `aquasecurity/trivy-action` and no Semgrep action.
- **Rationale:** in 2026-03-19, "a threat actor used compromised credentials to publish a malicious Trivy v0.69.4
  release and force-push 76 of 77 version tags in `aquasecurity/trivy-action` to credential-stealing malware"
  (GHSA-69fq-xp46-6x23 / CVE-2026-33634, https://github.com/aquasecurity/trivy/security/advisories/GHSA-69fq-xp46-6x23).
  GitHub: "Pinning an action to a full-length commit SHA is currently the only way to use an action as an immutable
  release" (https://docs.github.com/en/actions/reference/security/secure-use). Digest-pinned images give the same
  immutability with fewer moving parts, and the repo already runs gitleaks this way (`.github/workflows/secrets.yml`).
- **Versions (from `gh api …/releases/latest`):** Trivy v0.74.0 (2026-08-14); Semgrep v1.178.0 (2026-09-23);
  Gitleaks v8.30.1 (2026-03-21). `zricethezav/gitleaks:v8.30.1` exists, with amd64 digest `sha256:b109bc5f…21dbb`.
- **Assumption A-101:** the images `aquasec/trivy:0.74.0` and `semgrep/semgrep:1.178.0` exist on Docker Hub. The
  Setup task resolves their digests with `docker buildx imagetools inspect`.
- **Alternatives:** `aquasecurity/trivy-action@ed142fd0673e97e23eac54620cfb913e5ce36c25` (v0.36.0, SHA-pinned). Rejected
  (ALT-010): the action wraps the same binary, and its SARIF mode "enforces output of all vulnerabilities regardless of
  configured severities" unless `limit-severities-for-sarif: true` (trivy-action README). That's one more thing to get wrong.

## R-04 Trivy usage: dependency, image and IaC gates
<!-- Source: spec.md#FR-005, spec.md#FR-006, spec.md#FR-007, spec.md#FR-012, spec.md#FR-013 -->

- **Fail closed:** "By default, Trivy exits with code 0 even when security issues are detected. Use the `--exit-code`
  option" (https://trivy.dev/latest/docs/configuration/others/). Every gating call passes `--exit-code 1`.
- **Severity:** `--severity HIGH,CRITICAL` applies to vulnerability and misconfiguration scanning. `--ignore-unfixed`
  applies to vulnerabilities only. `.trivyignore` accepts vulnerability IDs and misconfiguration IDs such as `AVD-DS-0002`
  (https://trivy.dev/latest/docs/configuration/filtering/).
- **IaC:** `trivy config` scans "Terraform, CloudFormation, Azure ARM templates, Helm Charts and Dockerfile"
  (https://trivy.dev/latest/docs/scanner/misconfiguration/).
- **Decision:** each Trivy gate runs **twice**:
  1. A report run: `--format sarif --output …` with no severity filter and exit code 0. It is uploaded to code scanning.
  2. A gate run: `--severity HIGH,CRITICAL --exit-code 1` (plus `--ignore-unfixed` for fs and image).

  This keeps the gate decision independent of SARIF behaviour.
- **Assumption A-102:** `--exit-code` behaves the same for `trivy config` as for vulnerability scans. The docs don't state it
  explicitly. The IaC demo PR (FR-011) proves it.

## R-05 Semgrep (SAST)
<!-- Source: spec.md#FR-004, spec.md#FR-012, spec.md#FR-013 -->

- **Facts** (https://docs.semgrep.dev/cli-reference, https://docs.semgrep.dev/deployment/oss-deployment):
  - `semgrep scan` runs Semgrep Community Edition with no login.
  - `--error` means "Exit 1 if there are findings".
  - `--severity` takes "INFO, WARNING, or ERROR".
  - `--sarif-output` writes a SARIF file.
  - Exit codes: 2 = fatal, 4 = invalid pattern, 5 = YAML parse error, 7 = invalid rules. All are non-zero, so the gate fails closed.
- **Severity mapping:** "`ERROR`, `WARNING` and `INFO` … correspond to High, Medium, and Low"
  (https://docs.semgrep.dev/kb/rules/understand-severities). So HIGH+CRITICAL (D-002) maps to `--severity ERROR`.
- **Decision:** as with Trivy, a report run (`--sarif-output`, all severities) and a gate run (`--config p/python
  --severity ERROR --error`).
- **Assumption A-103:** Semgrep's CLI `--severity` doesn't accept CRITICAL/HIGH directly, and rules labelled Critical
  surface as `ERROR`. The SAST demo PR proves the chosen demo pattern is caught.

## R-06 SARIF upload and code scanning
<!-- Source: spec.md#FR-004, spec.md#US2 -->

- `github/codeql-action/upload-sarif@v4` is the current major. `security-events: write` is "required for all workflows"
  (https://docs.github.com/en/code-security/code-scanning/integrating-with-code-scanning/uploading-a-sarif-file-to-github).
- Code scanning is available on public repositories without GitHub Code Security
  (https://docs.github.com/en/get-started/learning-about-github/about-github-advanced-security).
- GitHub-owned actions (`actions/*`, `github/*`) are pinned to a major tag, per `.claude/rules/security.md`.

## R-07 IaC scanner choice: Trivy config only
<!-- Source: spec.md#FR-007 -->

- **Decision:** Trivy config is the only IaC scanner, covering `infra/` and `Dockerfile`.
- **Rationale:** it's one scanner, already pinned (R-03), and it covers both Terraform and Dockerfile. Checkov's added value for
  azurerm is its "graph-based scanning" with "over 1000 built-in policies" (https://github.com/bridgecrewio/checkov).
  That it catches anything here that Trivy misses is an Assumption and hasn't been demonstrated.
- **Alternatives:** add Checkov (`bridgecrewio/checkov-action` `v12.3125.0` → `444c9db6…009e`). Deferred (ALT-011) and can
  return as a follow-up if Trivy misses the IaC demo defect.

## R-08 Compute: Azure Container Apps (consumption)
<!-- Source: spec.md#FR-009, spec.md#FR-015, spec.md#NFR-004 -->

- **Free grant:** "The first 180,000 vCPU-seconds; The first 360,000 GiB-seconds; The first 2 million HTTP requests"
  per subscription per month. "When a revision is scaled to zero replicas, no resource consumption charges are
  incurred." (https://learn.microsoft.com/en-us/azure/container-apps/billing)
- **eastus rates** (Retail Prices API, `serviceName eq 'Azure Container Apps' and armRegionName eq 'eastus'`):
  - vCPU active: $0.000024/s
  - vCPU idle: $0.000003/s
  - Memory: $0.000003/GiB-s
  - Requests: $0.40 per 1M
  - The eastus meters exist. That Container Apps is *available* in eastus is inferred from this (**Assumption A-104**), and the first `terraform apply` proves it.
- **Decision:** `min_replicas = 0`, `max_replicas = 1`, 0.25 vCPU / 0.5 Gi. That this CPU/memory pair is valid is
  **Assumption A-105** (`terraform plan` validates it).
- **Consequence:** cold starts. The post-deploy smoke test (FR-010) retries for up to 120 s.

## R-09 Hardening on Container Apps: platform exception
<!-- Source: spec.md#NFR-003, .claude/rules/security.md -->

- **Finding:** the azurerm `container` block and the ARM container schema expose no `securityContext`,
  `runAsNonRoot`, `readOnlyRootFilesystem` or capability settings
  (https://github.com/hashicorp/terraform-provider-azurerm/blob/main/website/docs/r/container_app.html.markdown).
  The platform states: "Azure Container Apps doesn't allow privileged containers mode"
  (https://learn.microsoft.com/en-us/azure/container-apps/containers). The feature request for non-root enforcement is open:
  https://github.com/microsoft/azure-container-apps/issues/1001. The image's `USER` is honoured, as implied by
  https://github.com/microsoft/azure-container-apps/issues/1746.
- **Decision (D-007):**
  - The image sets a numeric non-root `USER`. Trivy config's non-root Dockerfile check enforces it.
  - CI runs the built image locally under `--read-only --cap-drop ALL --security-opt no-new-privileges --user 10001`. This proves the app *works* under the full least-privilege profile, even though Azure can't enforce it.
  - The gap is documented in plan.md and the README as a platform exception.
- **Alternatives:** App Service for Containers or AKS. Rejected: AKS far exceeds the cost target (NFR-004), and App Service has no free tier for containers. **Assumption:** App Service has no free container tier. This wasn't verified; it isn't load-bearing because Container Apps was chosen per `.claude/rules/azure.md`.

## R-10 Logs: Log Analytics with a daily cap
<!-- Source: spec.md#NFR-004, spec.md#NFR-006 -->

- **Facts:**
  - Container Apps can "disable the storage of log data" (https://learn.microsoft.com/en-us/azure/container-apps/log-options).
  - In azurerm, `logs_destination` is "(Optional) … `log-analytics` and `azure-monitor`". Omitting it means logs are only streamed.
  - For Log Analytics: "The first 5 GB/month per billing account in this tier are free"
    (https://azure.microsoft.com/en-us/pricing/details/monitor/). The eastus rate is $0.00 up to 5 GB, then $2.30/GB.
- **Decision (D-009):** `logs_destination = "log-analytics"`, with a `PerGB2018` workspace, 30-day retention and a daily quota
  cap. That makes operability (NFR-006) demonstrable at a $0 expected cost.
- **Assumption A-106:** `azurerm_log_analytics_workspace` supports `daily_quota_gb`. This wasn't fetched in this session;
  `terraform validate` confirms it.
- **Alternatives:** no log destination (ALT-012). Rejected: nothing to look at when the smoke test fails.

## R-11 Terraform and remote state
<!-- Source: spec.md#FR-008, .claude/rules/azure.md -->

- **Versions:** Terraform CLI 1.16.4 (2026-09-23); azurerm provider 5.7.0 (2026-09-24);
  `hashicorp/setup-terraform@v4` (from the GitHub releases pages).
- **Decision:** pin as follows:
  - `required_version = ">= 1.6, < 2.0"`
  - azurerm `~> 5.7`
  - CI installs exactly 1.16.4 via `hashicorp/setup-terraform`, pinned to a SHA because it's third-party
  - `infra/.terraform.lock.hcl` is committed
- **Backend** (https://developer.hashicorp.com/terraform/language/backend/azurerm):
  - "This backend supports state locking and consistency checking with Azure Blob Storage native capabilities" (a blob lease).
  - `use_oidc = true` and `use_azuread_auth = true`, with `storage_account_name`, `container_name` and `key`.
  - Recommended role: "Storage Blob Data Contributor on the storage account container (Recommended for least privilege)".
- **State location:** a separate resource group `rg-stf-devsecops-pipeline-tfstate`, created by the bootstrap script, so tearing down the
  app resource group doesn't destroy its own state (A-005).
- **Storage cost** (Retail Prices API, Hot LRS, eastus): $0.0208/GB-month; writes $0.05 per 10K. A state blob under 1 MB
  costs well under $0.01/month (arithmetic, not a quoted price).

## R-12 CI identity: OIDC, main-branch only, RG-scoped roles
<!-- Source: spec.md#FR-009, spec.md#NFR-001, spec.md#NFR-003, .claude/rules/azure.md -->

- **Facts:**
  - `azure/login@v3` takes `client-id`, `tenant-id` and `subscription-id`, and OIDC requires `id-token: write`
    (https://github.com/Azure/login).
  - Federated subject for a branch: `repo:<owner>/<repo>:ref:refs/heads/<branch>`. "Wildcard characters aren't
    supported in any federated identity credential property value"
    (https://learn.microsoft.com/en-us/entra/workload-id/workload-identity-federation-create-trust).
  - The PR subject the token carries is `repo:ORG/REPO:pull_request`, with an underscore
    (https://docs.github.com/en/actions/reference/security/oidc). Microsoft's page writes it with a hyphen, and GitHub's form is the one the token uses.
- **Decision (D-006):**
  - One Entra app registration with **one** federated credential: `repo:cjsy2001/devsecops-pipeline:ref:refs/heads/main`.
  - PR runs get no Azure access at all. In a public repo that avoids exposing cloud credentials to fork PRs. Terraform checks on PRs are
    `fmt -check`, `validate -backend=false` and the Trivy config scan.
  - Roles:
    - **Contributor at `rg-stf-devsecops-pipeline` scope only.**
    - **Storage Blob Data Contributor on the `tfstate` container only.**
- **Why Contributor:** the narrower roles "Container Apps Contributor" and "Container Apps ManagedEnvironments Contributor" exist
  (https://learn.microsoft.com/en-us/azure/role-based-access-control/built-in-roles). Whether they also cover the
  Log Analytics workspace and every call Terraform makes is unverified, so RG-scoped Contributor is the fallback. It's allowed
  by the rule, which only forbids Owner/Contributor at subscription scope. **Follow-up** (Polish): try the narrower roles.
- **Alternatives:**
  - A second federated credential for `pull_request` so PRs can run `terraform plan` (ALT-013). Rejected: it gives fork-reachable workflows cloud read access.
  - A user-assigned managed identity instead of an app registration. It's equivalent. The app registration is what the `azure/login` docs lead with.

## R-13 Registry: GHCR, deployed by digest
<!-- Source: spec.md#FR-006, spec.md#FR-017 -->

- **Facts:** the azurerm `registry` block is optional. For private images it takes `server`, `username` and
  `password_secret_name`, or `identity` (container_app.html.markdown above). Container Apps runs "Containers from any public
  or private container registry" (https://learn.microsoft.com/en-us/azure/container-apps/containers).
- **Decision:**
  - The image job pushes `ghcr.io/cjsy2001/devsecops-pipeline` with `GITHUB_TOKEN` (`packages: write`), only on `main` and only after the image gate passed.
  - The digest is passed to Terraform as `var.image`.
  - The package is made **public**, so no `registry` block and no pull credential exist.
- **Assumption A-107:** a public GHCR image needs no `registry` block, which is inferred from the block being optional. The first deploy proves it.
- **Assumption A-108:** a newly created GHCR package may default to private. Making it public is a one-time owner step, documented in the README.
  **Fallback:** a GitHub PAT with `read:packages` stored as a Container Apps secret and fed from a GitHub Actions secret, never in git.

## R-14 Workflow structure, required checks and skipped jobs
<!-- Source: spec.md#FR-002, spec.md#FR-009, spec.md#FR-013, spec.md#FR-014, spec.md#FR-017 -->

- **Facts:**
  - "A job that is skipped will report its status as 'Success'. It will not prevent a pull request from merging, even if it is a required check."
    (https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-jobs-with-conditions)
  - "Using the same job name in multiple workflows can cause ambiguous status check results"
    (https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches).
- **Decision (D-008):**
  - One workflow, `ci.yml`, with jobs `build-test`, `secrets`, `sast`, `deps`, `iac`, `image`, then `deploy` (`needs:` all the others, with
    `if: github.event_name == 'push' && github.ref == 'refs/heads/main'`).
  - Required checks are the gate jobs plus `build-test`, **never `deploy`** (a skipped job reports success).
  - `secrets.yml` stays in place but becomes a reusable workflow (`on: workflow_call`, plus `workflow_dispatch` and a weekly `schedule`). `ci.yml`
    calls it, so `deploy` can depend on it and the check name isn't duplicated.
- **Assumption A-109:** the check name of a called job is `<caller job> / <called job>` (for example `secrets / gitleaks`). The branch
  protection task reads the real names with `gh api repos/{o}/{r}/commits/{sha}/check-runs` before registering them.
- **Action pins (latest majors via `gh api`, 2026-09-25):**
  - `actions/checkout@v7`
  - `github/codeql-action/upload-sarif@v4`
  - SHA-pinned (third-party): `azure/login` (v3), `hashicorp/setup-terraform` (v4), `docker/setup-buildx-action` (v4), `docker/login-action` (v4) and `docker/build-push-action` (v7). The Setup task resolves their SHAs.

## R-15 Idle-month cost
<!-- Source: spec.md#NFR-004, .claude/rules/azure.md -->

| Item | Idle month (eastus) | Basis |
|---|---|---|
| Container App, min 0 replicas | $0.00 | "scaled to zero … no resource consumption charges" (R-08) |
| Occasional requests / smoke tests | $0.00 | within the free grant (R-08) |
| Log Analytics | $0.00 | < 5 GB free per billing account (R-10) |
| Container Apps environment (consumption) | $0.00 | **Assumption A-110:** a consumption-only environment has no fixed fee. To be checked on the first invoice |
| State storage account | < $0.01 | Hot LRS rates (R-11) |
| GHCR (public package) | $0.00 | free for public packages, **Assumption A-111** |
| **Total** | **≈ $0.01 / month** | NFR-004 target < $5 |

## Decisions recorded in the plane

- **D-004:** scanners run as digest-pinned containers, with a report run and a separate gate run.
- **D-005:** Python 3.12, FastAPI and uv.lock.
- **D-006:** OIDC for `main` only, with RG-scoped Contributor and blob-data roles.
- **D-007:** Container Apps hardening platform exception, plus a local hardened-run test.
- **D-008:** a single `ci.yml`, with `secrets.yml` as a reusable workflow and deploy never a required check.
- **D-009:** Log Analytics with a daily cap.

Rejected alternatives: ALT-010 trivy-action, ALT-011 Checkov (deferred), ALT-012 no log destination, ALT-013 PR federated credential.
