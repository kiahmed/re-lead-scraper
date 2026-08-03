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
	@awk 'BEGIN {FS = ":.*## "} /^# ----/ {printf "\n\033[1m%s\033[0m\n", substr($$0, 8)} /^[a-zA-Z_-]+:.*## / {printf "  \033[32m%-16s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# ---- Development ----

install: ## Install UI deps (API uses system python3 + admin-api/requirements.txt)
	cd $(UI) && npm install --no-audit --no-fund
	pip3 install -r $(API)/requirements.txt

dev: ## Run Vite dev server + local API together (hot reload both sides)
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

deploy-local: build ## Serve built SPA + API from one local server (prod simulation)
	cd $(API) && python3 dev_server.py --port 7071

deploy-azure: ## Build SPA and deploy SPA + managed-functions API to SWA
	cd $(UI) && npm run build
	cp values.yaml $(API)/values.yaml
	pip3 install -q --target $(API)/.python_packages/lib/site-packages -r $(API)/requirements.txt
	cd $(UI) && SWA_CLI_DEPLOYMENT_TOKEN=$$(az staticwebapp secrets list -n $(SWA_APP) -g $(RG) --query properties.apiKey -o tsv) \
		./node_modules/.bin/swa deploy ./dist --api-location ../$(API) --api-language python --api-version 3.11 --env production

# ---- Backend ----

run: ## Run the local API (Flask adapter over the same handlers as Azure)
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
	build preview deploy-local deploy-azure run migrate seed deploy-be \
	create-user disable-user reset-password list-users purge-sessions \
	package docker-build docker-run publish
