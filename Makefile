.PHONY: setup gitleaks status-pages

setup: ## install the secret-scanning git hook
	git config core.hooksPath .githooks

gitleaks: ## full-history secret scan (docker)
	docker run --rm -v "$(CURDIR):/repo" -w /repo zricethezav/gitleaks:v8.30.1 git --redact --no-banner --config .gitleaks.toml

STF ?= stf  # the stf plugin's CLI (on the Bash tool's PATH in Claude Code); override with STF=/path/to/bin/stf

status-pages: ## rebuild the local STF hub, plane dashboard and spec pages (then ask Claude to republish them: /stf:pages)
	$(STF) pages
