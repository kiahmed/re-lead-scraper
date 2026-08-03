# SolJet lead_scraper — build system
# Admin UI/API lives in admin-ui/ + admin-api/; the Logic Apps pipeline keeps
# its own flow (values.yaml → sync.py → deploy.py) and is not touched here.
.DEFAULT_GOAL := help

UI      := admin-ui
API     := admin-api
RG      := RELeadScraperGroup
SWA_APP := flynest-admin
FUNCAPP := flynest-admin-api

help: ## Show this help
	@awk 'BEGIN {FS = ":.*## "} /^# ----/ {sec = substr($$0, 8); sub(/ -+$$/, "", sec); printf "\n\033[1m%s\033[0m\n", sec} /^[a-zA-Z_-]+:.*## / {desc = $$2; gsub(/[A-Za-z][A-Za-z0-9_]*=("[^"]*"|[^ ,]+)/, "\033[38;5;208m&\033[0m", desc); printf "  \033[94m%-16s\033[0m %s\n", $$1, desc}' $(MAKEFILE_LIST)

# ---- Development ----

install: ## Install UI deps (API uses system python3 + admin-api/requirements.txt)
	cd $(UI) && npm install --no-audit --no-fund
	pip3 install -r $(API)/requirements.txt

dev: ## Code mode: Vite hot reload (:5173) + local API (:7071)
	$(MAKE) -j2 dev-ui run

dev-ui: ## Vite dev server only (proxies /api → :7071)
	cd $(UI) && npm run dev

watch: ## Continuous typecheck feedback (Vite already hot-reloads)
	cd $(UI) && npx tsc --noEmit --watch

stop: ## Stop any running local API/UI dev servers
	-pkill -f "dev_server.py" 2>/dev/null || true
	-pkill -f "vite" 2>/dev/null || true
	@echo "local servers stopped"

clean: ## Remove build output and caches
	rm -rf $(UI)/dist $(UI)/node_modules/.vite artifacts
	find $(API) -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true

# ---- Testing ----

test: test-py test-ui ## Run all tests

test-py: ## API unit tests (pytest, in-memory fake tables)
	cd $(API) && python3 -m pytest tests/ -q

test-ui: ## Frontend tests (vitest)
	cd $(UI) && npx vitest run

lint: ## Lint Python (ruff); JS is covered by typecheck
	ruff check $(API)

format: ## Format Python (ruff)
	ruff format $(API)

typecheck: ## TypeScript strict typecheck
	cd $(UI) && npx tsc --noEmit

# ---- Frontend ----

build: ## Production build (typecheck + vite build → admin-ui/dist)
	cd $(UI) && npm run build

preview: ## Preview the production bundle locally
	cd $(UI) && npm run preview

deploy-local: build ## Prod simulation: built SPA + API served together on :7071 (like Azure)
	cd $(API) && python3 dev_server.py --port 7071

deploy-azure: ## Build SPA and deploy SPA + managed-functions API to SWA
	cd $(UI) && npm run build
	cp values.yaml $(API)/values.yaml
	pip3 install -q --target $(API)/.python_packages/lib/site-packages -r $(API)/requirements.txt
	cd $(UI) && SWA_CLI_DEPLOYMENT_TOKEN=$$(az staticwebapp secrets list -n $(SWA_APP) -g $(RG) --query properties.apiKey -o tsv) \
		./node_modules/.bin/swa deploy ./dist --api-location ../$(API) --api-language python --api-version 3.11 --env production

# ---- Backend ----

run: ## API only on :7071 (Flask adapter, no UI)
	cd $(API) && python3 dev_server.py --port 7071

migrate: ## Ensure admin tables exist (users, sessions, interactions)
	cd $(API) && python3 -c "from core import tables; tables.provider(); print('admin tables ensured')"

seed: ## Create the local dev admin user (ADMIN_PASSWORD env or prompt)
	cd $(API) && python3 cli.py create devadmin --display-name "Dev Admin" || true

deploy-be: ## Provision Azure infra (SWA Free + admin tables) via bicep
	az deployment group create -g $(RG) -f deploy/admin-ui.bicep --parameters functionAppName=$(FUNCAPP) staticWebAppName=$(SWA_APP)
	@echo "API code ships together with the SPA: run 'make deploy-azure' (SWA managed functions)."
	@echo "Standalone Function App (needs Y1 quota): re-run with --parameters deployFunctionApp=true"

# ---- Authentication ----

create-user: ## make create-user U=alice — provision an admin user
	cd $(API) && python3 cli.py create $(U)

disable-user: ## make disable-user U=alice
	cd $(API) && python3 cli.py disable $(U)

reset-password: ## make reset-password U=alice
	cd $(API) && python3 cli.py reset-password $(U)

list-users: ## List admin users
	cd $(API) && python3 cli.py list

purge-sessions: ## Delete expired session rows
	cd $(API) && python3 cli.py purge-sessions

# ---- Deployment ----

package: build ## Zip SPA + API into artifacts/ for manual deploys
	mkdir -p artifacts
	cd $(UI)/dist && zip -qr ../../artifacts/admin-ui.zip .
	cd $(API) && zip -qr ../artifacts/admin-api.zip . -x 'tests/*' -x '__pycache__/*' -x 'local.settings.json'
	@ls -lh artifacts/

docker-build: ## Not used — SWA + Functions deploy without containers
	@echo "docker-build: not applicable — the admin UI deploys to Azure Static Web Apps (see deploy-azure) and the API via deploy-be. No container images in the deploy path."

docker-run: ## Not used — run locally with 'make deploy-local' instead
	@echo "docker-run: not applicable — use 'make deploy-local' for a production-layout local run."

publish: deploy-be deploy-azure ## Full production deploy: backend then frontend

.PHONY: help install dev dev-ui watch stop clean test test-py test-ui lint format typecheck \
	_notmain guard commit push pr ship clean-worktrees \
	build preview deploy-local deploy-azure run migrate seed deploy-be \
	create-user disable-user reset-password list-users purge-sessions \
	package docker-build docker-run publish

# ---- Git workflow ----

# typo guard: any command-line VAR= outside this list fails loudly
KNOWN_VARS := U m
# MAKEOVERRIDES splits quoted values on spaces — only words containing '=' are variable assignments
BAD_VARS := $(filter-out $(KNOWN_VARS),$(foreach o,$(MAKEOVERRIDES),$(if $(findstring =,$(o)),$(firstword $(subst =, ,$(o))))))
ifneq ($(BAD_VARS),)
$(error unknown variable(s): $(BAD_VARS) — known: $(KNOWN_VARS))
endif

_notmain:
	@branch=$$(git rev-parse --abbrev-ref HEAD); \
	if [ "$$branch" = "main" ] || [ "$$branch" = "master" ]; then \
		echo "refusing: on $$branch — create a branch first"; exit 1; fi

guard: ## Scan staged changes for secrets/sensitive files (runs inside commit/ship)
	@git diff --cached --name-only | grep -E '(^|/)\.env$$|\.pem$$|\.p12$$|local\.settings\.json$$' \
		&& { echo "guard: sensitive file staged — commit blocked"; exit 1; } || true
	@! git diff --cached -U0 -- . ':(exclude)Makefile' | grep -nEi 'AccountKey=[A-Za-z0-9+/]{16}|DefaultEndpointsProtocol=http|SharedAccessSignature=[A-Za-z0-9%]|BEGIN (RSA |EC )?PRIVATE KEY' \
		|| { echo "guard: possible secret in staged diff — commit blocked"; exit 1; }
	@echo "guard: clean"

commit: _notmain ## make commit m="message" — guarded commit of all changes
	@test -n "$(m)" || { echo 'usage: make commit m="message"'; exit 1; }
	@git add -A
	@$(MAKE) --no-print-directory guard
	@if git diff --cached --quiet; then echo "nothing to commit"; else git commit -m "$(m)"; fi

push: _notmain ## Push current branch to origin
	git push -u origin HEAD

pr: _notmain ## Open a draft PR for the current branch (no-op if one exists)
	-gh pr create --draft --fill 2>/dev/null || echo "PR already exists (or gh unavailable)"

ship: _notmain ## make ship m="msg" — lint+typecheck+tests, guarded commit, push, draft PR
	@test -n "$(m)" || { echo 'usage: make ship m="message"'; exit 1; }
	$(MAKE) --no-print-directory lint typecheck test
	$(MAKE) --no-print-directory commit m="$(m)"
	$(MAKE) --no-print-directory push
	$(MAKE) --no-print-directory pr

clean-worktrees: ## Remove .claude/worktrees checkouts (skips current; refuses dirty)
	@common=$$(git rev-parse --path-format=absolute --git-common-dir); \
	root=$$(dirname "$$common"); cur=$$(git rev-parse --show-toplevel); \
	for wt in "$$root"/.claude/worktrees/*/; do \
		[ -d "$$wt" ] || continue; \
		wtpath=$$(cd "$$wt" && git rev-parse --show-toplevel 2>/dev/null) || continue; \
		if [ "$$wtpath" = "$$cur" ]; then echo "skip (current): $$wt"; continue; fi; \
		if [ -n "$$(git -C "$$wt" status --porcelain 2>/dev/null)" ]; then echo "refuse (dirty): $$wt"; continue; fi; \
		git worktree remove "$$wt" && echo "removed: $$wt"; \
	done; git worktree prune
