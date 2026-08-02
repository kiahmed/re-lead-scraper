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

## What approval triggers

Phase 1: scaffold `admin-ui/` + `admin-api/` + Makefile → Phase 2: auth + users CLI → Phase 3: leads list/detail panes → Phase 4: interactions/timeline → Phase 5: Azure deploy. Each phase tested before the next, per requirements.

## Approval record (2026-08-02)

Approved by the user with these calls: **#2 standalone Function App** (future integrations; `deploy-be` target; bearer-token-only API), **#4 self-managed auth**, **#7 list-first layout** (full-width list → detail transition with back link), **#8 deed-ledger visual direction**; dev stays on `/mnt/c` (WSL node v22). Implementation proceeds unattended, tested and verified, **local deploy first** before any Azure deploy. Local API runs are served by a thin Flask adapter over the same handlers (Functions Core Tools not installed locally); the Azure Functions bindings are the production entry point.
