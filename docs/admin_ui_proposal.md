# Admin UI — Executive Proposal

**Verdict: GO.** All pieces are buildable on Azure at **$0/month during development** (SWA Free tier + existing storage account), with the existing Logic Apps pipeline completely untouched. Full planning detail exists (5-perspective analysis); this doc is decisions only — ask for any section expanded.

## Decision points

| # | Decision | Recommendation | Why (one line) |
|---|----------|----------------|----------------|
| 1 | Hosting | **Azure Static Web Apps, Free tier** — GO | Only $0 option with SPA hosting + SSL + managed API + staging envs; Storage-static-website breaks SPA deep links; App Service costs $13+/mo. |
| 2 | API host | **Standalone Function App (Python)** — ✅ decided | Room for future advanced integrations; own `deploy-be` Make target; API accepts only bearer tokens issued to the SPA after successful login. |
| 3 | Frontend | **React 19 + Vite + TypeScript**, CSS Modules + design tokens, TanStack Query | Typed parse boundary over ~20 loose table columns is the biggest maintainability win; no Tailwind/MUI — avoids generic-admin look. |
| 4 | Auth | **Self-managed, per requirements**: users + hashed sessions in Azure Tables, stdlib scrypt password hashing, HttpOnly/Secure/SameSite cookie, login lockout, **no password-reset endpoint** (CLI only) | Matches "provisioned by backend only"; tiny surface. ⚠️ *Alternative you should consciously reject: SWA built-in Entra ID login = near-zero auth code. Say the word and we swap.* |
| 5 | Storage | 3 new tables in existing `releadscraper` account: `users`, `sessions`, `interactions` (notes/messages/follow-ups, newest-first keys) | Notes/follow-ups have no backing store today; interactions table doubles as the future real-outreach message spine. |
| 6 | Pipeline safety | **`leads` table is read-only for the admin API** | Hub/spokes MERGE-upsert continuously; admin data lives only in `interactions`, so corruption is structurally impossible. |
| 7 | Layout | **List-first** — ✅ decided: full-width lead list (thick rows showing a few lines of content, highlight columns, search + category/status/date filters + pagination) → seamless transition to two-pane Deal/Activity detail with "back to list" top-left and bottom-left | Reference-admin-style triage table first; detail view keeps the fixed-viewport pane-scroll rule. |
| 8 | Look | Light "digitized deed ledger": paper whites, deep pine-green accent, muted per-category color chips, one grotesque face + mono for JSON | Real-estate-records feel, not generic dashboard; deliberately zero reuse of arboryx-admin styling. |
| 9 | Deploy | `swa` CLI with deployment token — **no GitHub Actions**; one-time `deploy/admin-ui.bicep` for infra, **kept out of main.bicep** | Existing values.yaml → sync.py → deploy.py flow stays 100% untouched; preview env → production promote built in. |
| 10 | Build system | **New Makefile at repo root** (none exists today, despite requirements saying "expand") — categorized targets incl. `create-user` / `disable-user` / `reset-password`; `docker-*` targets not needed for SWA (kept as documented no-ops) | Every target a one-liner; `make dev` = Vite hot reload + local Functions. |
| 11 | Testing | Pytest (fake table client) + Vitest/RTL + 1 Playwright smoke; `make test / lint / typecheck` cover both languages | Bulk of value in API unit tests; e2e suite deliberately capped at one. |
| 12 | Category list | Single source stays `values.yaml`; API serves it via `GET /api/meta` | No hardcoded category array in the UI, ever. |

## Flags before you approve

- **Dev speed (WSL):** repo lives on `/mnt/c` — node installs/watching will be 5–20× slower there. Recommended: develop from a WSL-native clone; polling fallback will be checked in either way.
- **Cold starts:** free-tier Python API sleeps; first request after idle takes 2–6 s. UI masks it; the paid fix exists but isn't worth it.
- **Scale ceiling:** Azure Tables list queries are fine to ~10–20k leads; beyond that needs an index partition (not built now, path reserved).
- **Future-proofed, not built:** real FB message sending, roles, re-run outreach per lead — all land as additive rows/endpoints later, no migrations.

## Implementation status (2026-08-02)

Phases 1–4 built and verified locally; Azure deploy (phase 5) is scripted but **not yet run**:

- `admin-api/` — framework-agnostic handlers + Azure Functions entry (`function_app.py`) + Flask local adapter (`dev_server.py`) + provisioning CLI (`cli.py`). **34 pytest tests, ruff clean.**
- `admin-ui/` — React 19 + Vite + TS strict; login, lead list (search / category tabs with counts / completeness filter / pagination), two-pane detail with notes & follow-ups. **12 vitest tests, tsc clean, 92 kB gzip bundle.**
- `Makefile` — all required categories; `make help` lists everything. `deploy-be` / `deploy-azure` / `publish` ready for phase 5.
- `deploy/admin-ui.bicep` — SWA Free + Y1 Function App + `users`/`sessions`/`interactions` tables; compiles clean; separate from main.bicep.
- **Local deploy verified against real storage**: `make migrate` created the three tables in `releadscraper`; a smoke user logged in via the API and browsed 281 real leads (counts per category correct), created/deleted a note, SPA served with deep-link fallback. Smoke user disabled and its session removed afterwards.

To go live: `make publish` (runs the Bicep deploy, zips the function code, deploys the SPA), then `make create-user U=<you>`.

## Deployment record (2026-08-02, phase "go-live")

- Renamed to **FlyNest Leads Admin**; per-lead edit (pencil → detail in edit mode, whitelisted PATCH) and delete (bin → confirm dialog, removes lead + its interactions) added on user request. This supersedes the "leads read-only" rule from decision #6 — writes are limited to `category / authorName / groupName / contact / extracted_info / outreach_message / investment_summary`; pipeline stage columns remain untouchable.
- **Live at: https://kind-hill-00577c70f.7.azurestaticapps.net** — SWA Free in East US 2, storage stays in East US.
- **Decision #2 amendment (forced):** the subscription has **0 quota for Y1 consumption plans in every region** (`SubscriptionIsOverQuotaForSku`), so the standalone Function App could not be provisioned. The API runs as **SWA managed functions** (same code, v1 entry point in `api_handler/`, deps vendored to `.python_packages`). The standalone path is preserved in `deploy/admin-ui.bicep` behind `deployFunctionApp=true` — flip it after a quota increase, set `VITE_API_BASE`, and nothing else changes.
- Two Azure-specific quirks encoded in the code: SWA rejects `AzureWebJobs*` app settings (hence v1 function model), and SWA **replaces the `Authorization` header** before requests reach managed functions — the SPA therefore authenticates via an `X-Admin-Token` header (checked first server-side; `Authorization: Bearer` still works locally/standalone).
- Live verification: login/lockout, 281 leads with correct category counts, lead detail, note create/delete — all against production. Smoke user disabled and its sessions removed.

## Approval record (2026-08-02)

Approved by the user with these calls: **#2 standalone Function App** (future integrations; `deploy-be` target; bearer-token-only API), **#4 self-managed auth**, **#7 list-first layout** (full-width list → detail transition with back link), **#8 deed-ledger visual direction**; dev stays on `/mnt/c` (WSL node v22). Implementation proceeds unattended, tested and verified, **local deploy first** before any Azure deploy. Local API runs are served by a thin Flask adapter over the same handlers (Functions Core Tools not installed locally); the Azure Functions bindings are the production entry point.
