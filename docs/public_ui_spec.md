# Public UI — Technical Spec

**Status: proposed, not yet built.** Companion to `admin_ui_proposal.md`. Same stack, same storage
account, same `values.yaml`; a *separate* app with a deliberately smaller permission surface —
public users read leads, keep private notes and a personal workspace, and set up alerts.
They cannot edit or delete anything the pipeline owns.

---

## 1. Decisions

| # | Decision | Call | Why |
|---|----------|------|-----|
| 1 | Where it lives | **`public-ui/`** at repo root: `web/` (SPA) + `api/` (Functions) + `infra/` (bicep) | One directory as requested; internally mirrors the proven `admin-ui/` + `admin-api/` split so every Make/deploy pattern transfers. |
| 2 | Hosting | **Second Static Web App, Free tier** (`flynest-public`), API as SWA managed functions | Same $0 path the admin UI landed on; the Y1 quota block still applies to this subscription. |
| 3 | Isolation from admin | Separate SWA, separate API, **separate session + user tables** (`pubusers`, `pubsessions`) | A public token must never be presentable to the admin API. Different table = structurally impossible, not policy-enforced. |
| 4 | Pipeline safety | **`leads` is read-only for the public API — no PATCH/DELETE route exists** | Not "hidden in the UI": the routes are absent from the route table, so there is no code path to a write. |
| 5 | Per-user data | New tables `pubnotes`, `pubsaved`, `pubalerts`, `pubalertlog`, PartitionKey = **user id taken from the session, never from the request** | Cross-user reads/writes are unrepresentable, not merely forbidden. |
| 6 | Auth | **Own OAuth**: email+password (scrypt, as admin) **plus Google (OIDC), Microsoft (OIDC), Facebook (OAuth2)** | SWA's built-in providers no longer include Google, and custom OIDC on SWA requires the **Standard** plan ($9/mo). Rolling our own keeps SWA Free and reuses the admin session model. |
| 7 | Signup | **Self-serve**, email verified before alerts can fire | It's the public app; admin provisioning would defeat the point. Verification gates the notification channel, not browsing. |
| 8 | Alert criteria | One JSON criteria object, evaluated by **`criteria.py` shared by the live filter and the notifier** | What you preview in Settings is byte-for-byte what fires at 3am. No second implementation to drift. |
| 9 | Notification transport | **All three: email + Web Push + real SMS**, each independently switchable by config. Email = ACS (swap to Brevo via one env var); SMS = ACS toll-free, gated by `NOTIFY_SMS_ENABLED` | ✅ decided by the user. See §6 — Azure has no free tier for either email or SMS, and no provider has a free SMS tier at any scale. The spec says so rather than pretending. |
| 10 | Notifier schedule | Logic App cron → `POST /api/alerts/run` with a service token, every 15 min | Exactly the shape of the existing `flynest-admin-purge-sweep`. All logic in the API; the Logic App is pure cron. |
| 11 | Look | **"Blueprint & Ledger"** — admin's paper/ink tokens re-keyed warmer, plus a hand-drawn property frieze + creative-finance terms behind auth/marketing surfaces | Distinct from the admin's austere ledger without inventing a second design language. Working screens stay calm. |
| 12 | Category/field source | Still `values.yaml`, served by `GET /api/meta` | Zero hardcoded categories or field names in the public UI, same rule as admin. |

---

## 2. Layout on disk

```
public-ui/
  web/                       # Vite + React 19 + TS strict (mirrors admin-ui/)
    src/
      api/{client,hooks,types}.ts
      auth/{AuthContext,LoginPage,SignupPage,OAuthCallback,RequireAuth}.tsx
      pages/{BrowsePage,LeadPage,WorkspacePage,SettingsPage}.tsx
      pages/panes/{PostPane,NotesPane,AlertBuilder}.tsx
      components/{PropertyFrieze,CriteriaRow,CategoryChip,...}.tsx
      styles/{tokens,global,app}.css
  api/                       # Azure Functions v1 Python (mirrors admin-api/)
    api_handler/             # catch-all HTTP trigger
    core/
      config.py  http.py  security.py  tables.py    # same primitives as admin-api
      auth.py        # password + session
      oauth.py       # Google / Microsoft / Facebook authorization-code flow
      leads.py       # READ ONLY view over the leads table
      notes.py       # per-user notes  (add / update / delete own)
      saved.py       # per-user workspace: pin, status, tags
      alerts.py      # saved criteria CRUD + preview
      criteria.py    # the single matcher (UI filter == notifier)
      notify.py      # channel abstraction: acs | brevo | smtp | webpush | acs_sms
      digest.py      # cursor, dedupe, rate cap, quiet hours
      routes.py      # route table (note what is NOT in it)
    cli.py           # service token, alert dry-runs
    dev_server.py    # Flask adapter, same trick as admin-api
  infra/public-ui.bicep      # SWA Free + pub* tables + ACS + notifier Logic App
  README.md
```

Root `Makefile` gains a `# ---- Public UI ----` section: `pub-install pub-dev pub-build pub-test
pub-typecheck pub-deploy-be pub-deploy-azure pub-service-token pub-run-alerts`.

---

## 3. Data model

All in the existing `releadscraper` storage account.

| Table | PartitionKey | RowKey | Notes |
|---|---|---|---|
| `pubusers` | `"user"` | normalized email | `password_hash` (may be empty for social-only), `providers` JSON, `email_verified`, `phone`, `phone_verified`, `tz`, `is_active`, lockout fields |
| `pubsessions` | `"session"` | SHA-256 of token | mirrors admin sessions; 7-day sliding |
| `pubnotes` | user id | inverted-ts + rand | `lead_id`, `body`, `created_at`, `updated_at`, `edited` |
| `pubsaved` | user id | encoded `lead_id` | `pinned`, `status` (`new/working/passed`), `tags` JSON — the workspace |
| `pubalerts` | user id | alert id | `name`, `criteria` JSON, `channels`, `digest`, `quiet_hours`, `max_per_day`, `enabled`, `last_cursor` |
| `pubalertlog` | `alert_id` | encoded `lead_id` | dedupe ledger + delivery outcome; TTL-swept with the leads |

**Why notes partition by user, not by lead:** both access patterns ("my notes on this lead",
"everything I've written" for the history/workspace view) are one partition query, and the
partition key comes from the validated session — a request cannot name someone else's partition.

---

## 4. API surface

Read-only over pipeline data, read-write over the user's own rows.

```
POST   auth/signup                 email + password, sends verification
POST   auth/login
POST   auth/logout
GET    auth/me
POST   auth/verify                 consume emailed token
GET    auth/oauth/{provider}       -> redirect to Google/Microsoft/Facebook
GET    auth/oauth/{provider}/cb    <- code exchange, link-or-create, issue session

GET    meta                        categories, cities, per-category spec fields
GET    leads                       list + facet counts   (READ ONLY)
GET    leads/{id}                  detail                (READ ONLY)

GET    leads/{id}/notes            own notes only
POST   leads/{id}/notes
PATCH  leads/{id}/notes/{nid}      own note only
DELETE leads/{id}/notes/{nid}      own note only

GET    workspace                   pinned + statuses + note counts
PUT    workspace/{lead_id}         pin / status / tags

GET    alerts
POST   alerts
PATCH  alerts/{aid}
DELETE alerts/{aid}
POST   alerts/preview              criteria -> matching leads right now (no save)
POST   alerts/test                 send one sample to the user's channels
POST   alerts/run                  service-token only; the cron entry point
```

**Deliberately absent — there is no route to reach them:** `PATCH /leads/*`,
`DELETE /leads/*`, `POST /leads/purge`, `/users*`.

---

## 5. Alert criteria

Stored as JSON; the same object drives the Settings preview and the notifier.

```jsonc
{
  "name": "ATL SubTo under 8%",
  "categories": ["Subject-To", "Hybrid"],     // from values.yaml
  "cities":     ["Atlanta"],                  // same list the pipeline filters on
  "hoa":        ["zero", "none"],             // the pipeline's own three states
  "completeness": "any",                      // any | complete | incomplete
  "keywords_any":  ["tenant occupied"],
  "keywords_none": ["agent", "realtor"],

  // property specs — the fields the spokes use to write the follow-up message,
  // i.e. values.yaml outreach.required_fields[category], unioned over the
  // selected categories and served by GET /api/meta
  "specs": [
    {"field": "interest_rate", "op": "lte",     "value": 8,               "unknown": "exclude"},
    {"field": "loan_balance",  "op": "between", "value": [50000, 300000], "unknown": "include"}
  ],

  // "unknowns per category" — driven by the spoke's own missing_fields column
  "unknowns_required":  ["location"],   // notify me *because* it's still unknown
  "unknowns_forbidden": ["asking_price"],

  "channels": ["email", "webpush"],
  "digest": "instant",                  // instant | hourly | daily
  "quiet_hours": {"tz": "America/New_York", "from": "21:00", "to": "08:00"},
  "max_per_day": 25
}
```

### The honest gap, and how it's handled

The pipeline **does not persist structured specs today**. `classifier.extracted_info_rules` returns
only `{"summary": "..."}`, and the spokes read `loan_balance` / `interest_rate` / `ARV` straight out
of the post text when they generate the message — those numbers are never written to a column.
So a naive `interest_rate <= 8` filter would have nothing to compare against.

Three ways to close it:

| | Approach | Pipeline change | Fidelity |
|---|---|---|---|
| **a** | Criteria over what *is* stored: category, city, HOA, completeness, keywords, and known/unknown per field via the spoke's `missing_fields` | none | exact |
| **b** | Public API derives specs at read time — regex over the post text for `$185,000`, `7.25%`, `$1,450/mo`, `ARV 240k` | none | good, not perfect |
| **c** | Spokes also persist `extracted_specs` JSON | values.yaml + sync + deploy | exact |

**Ship (a) + (b) now, record (c) as the follow-up.** Every spec value the UI shows carries a
`source: "stored" | "parsed"` marker, and each spec criterion carries an explicit
`unknown: include | exclude` so a user decides what an unparseable post means for them. This keeps
the prime directive intact — the Logic Apps pipeline is not touched — while (a) alone already
delivers "the criteria we filter by today + the unknowns per category" exactly.

---

## 6. Notification transport — what's actually free

Researched against the vendor docs, August 2026.

| Channel | Option | Free tier | Real cost |
|---|---|---|---|
| Email | **Azure Communication Services Email** (Azure-managed domain — no DNS work) | **none** | $0.00025/email + $0.00012/MB → **$0.25 per 1,000** |
| Email | **Brevo** | **9,000/mo (300/day), forever** | $0 in our range |
| Email | Resend / MailerSend | 3,000/mo | $0 in our range |
| Email | Amazon SES | 62k/mo only from EC2 | $0.10/1k otherwise |
| SMS | **ACS SMS**, US toll-free | **none** | $2/mo lease + $0.0075 send + $0.0025 carrier ≈ **$0.01/segment**, and toll-free verification is **mandatory** — unverified numbers are blocked outright |
| SMS | ACS 10DLC | none | $4 brand + $40 vetting + $1.50–30/mo campaign + $1/mo number + ~$0.01/segment |
| SMS | any other vendor | none | there is no free SMS tier at scale, anywhere |
| Push | **Web Push (VAPID)** | **unlimited, free** | $0 — W3C standard, desktop + Android + iOS 16.4+ installed PWA |
| Push | Azure Notification Hubs | 1M pushes/mo free | needs native app registrations; unnecessary for a PWA |

### Decision (user, 2026-08-24)

**Ship all three channels, each independently switchable by config.** The user's call after being
shown that Web Push carries no phone number and that no SMS is free at any scale:

- `NOTIFY_EMAIL_PROVIDER` = `acs` (default) | `brevo` | `smtp` | `off`
- `NOTIFY_WEBPUSH_ENABLED` = `true` (default) | `false`
- `NOTIFY_SMS_ENABLED` = `false` (default) | `true`, with `NOTIFY_SMS_PROVIDER=acs`

Every channel is a no-op when its switch is off — a user may select it in Settings only if the
server advertises it in `GET /api/meta.channels`, so the UI can never offer a dead channel.

**Rationale, Azure-first as asked, with an escape hatch:**

- **Email = ACS by default.** It is the Azure-native answer, needs no DNS setup with an
  Azure-managed domain, and at any plausible volume it is *effectively* free — 10,000 alert emails
  is $2.50/month. `NOTIFY_EMAIL_PROVIDER=brevo` swaps to a hard $0 with one env var if that
  $2.50 matters.
- **"Text me" = Web Push, not SMS.** It is the only instant channel that is genuinely free and
  genuinely unlimited, it needs no phone number, no carrier verification, and no per-message cost.
  The UI labels it *"Instant push"*, not *"SMS"* — no pretending.
- **Real SMS ships built and working, defaulting to off** (`NOTIFY_SMS_ENABLED=false`). It needs a
  provisioned toll-free number and a cleared verification before it can send at all; until then the
  channel is hidden from the UI. Flip the flag when verification clears — no code change. Note the
  reach limit: an ACS toll-free number sends to **US, Canada, and Puerto Rico only**; other
  countries need their own number type per country.
- Carrier email-to-SMS gateways (`5551234567@vtext.com`) are free but best-effort and actively
  being deprecated by carriers — offered as an explicitly-labeled experimental channel, never as
  the default.

`notify.py` exposes one `send(channel, user, subject, body)` so all four transports are swappable
behind config, exactly like `RUN_MODE` swaps the pipeline runners.

---

## 7. Notifier loop

1. Logic App cron fires `POST /api/alerts/run` every 15 min with the service token.
2. For each enabled alert: read leads newer than `last_cursor`, run `criteria.match()`.
3. Drop anything already in `pubalertlog` for that alert (dedupe survives cursor rewinds).
4. Apply `quiet_hours` (hold, don't drop) and `max_per_day` (cap, and say so in the message).
5. `instant` → one message per lead; `hourly`/`daily` → one digest.
6. Write outcome to `pubalertlog`, advance `last_cursor`.

Every guard is server-side; the cron carries no logic. `make pub-run-alerts` fires it on demand,
`POST /api/alerts/preview` is a pure dry run.

---

## 8. Visual direction — "Blueprint & Ledger"

Same bones as the admin's deed-ledger tokens, re-keyed for a public audience: warm paper
(`#fbfaf7`), deep navy-teal ink, a brass/ochre accent instead of pine green, and the identical
per-category chip hues so a lead reads the same in both apps.

The theme the request asked for, applied with restraint:

- A single hand-drawn, one-line-weight SVG frieze — **bungalow, duplex, mid-rise, RV park,
  vacant land parcel, crane/scaffold, coin stack** — tiled at ~4% opacity as a background layer.
- Creative-finance vocabulary set in small caps drifting between the drawings: *Subject-To,
  Seller Carry, Wrap, ARV, PITI, Balloon, DSCR, Assumable, Morby Method, Due-on-Sale*.
- **Where:** login, signup, empty states, page headers, the marketing strip above the fold.
  **Where not:** the lead list and the reading pane, which stay plain paper — the frieze is
  atmosphere, not wallpaper.
- Respects `prefers-reduced-motion` (no drift animation) and never drops text contrast below AA.

---

## 9. Build phases

1. Scaffold `public-ui/{web,api,infra}` + Make targets + `pub*` tables.
2. Auth: email/password → sessions; then Google/Microsoft/Facebook; then verification email.
3. Read-only browse: list with facets, detail, reusing `leadfilter` semantics.
4. Notes + workspace (pin / status / tags / "everything I've written").
5. `criteria.py` + alert builder UI + `alerts/preview`.
6. `notify.py` + Web Push + ACS email + the cron Logic App.
7. Theme pass: tokens, frieze, empty states.
8. Tests throughout — pytest on fake tables (as admin-api does), vitest on the SPA.

## 10. Open questions for the user

1. **Who may sign up?** Open to anyone, invite-code gated, or email-domain allowlisted?
2. **Do public users see every lead**, or only classified/actionable ones (Others hidden)?
3. **Spec criteria fidelity** — is (a)+(b) acceptable now, or should (c) land first so numeric
   filters are exact from day one?
4. ~~Is "Instant push" an acceptable stand-in for "text"?~~ **Answered:** no — ship all three
   channels, SMS behind `NOTIFY_SMS_ENABLED`. See §6.

---

## 11. Build + deployment record (2026-08-25)

**Live** — SWA Free in East US 2, storage stays in East US. The hostname is in
`PUBLIC_SITE_URL` (`.env`), not written down here: this repo is public. Built, deployed, and verified against production.

### What shipped

- `public-ui/api/` — 16 core modules behind one route table; **98 pytest tests, ruff clean**.
- `public-ui/web/` — React 19 + Vite + TS strict; **17 vitest tests, tsc clean, 103 kB gzip**.
- `public-ui/infra/public-ui.bicep` — SWA Free, the seven `pub*` tables, and the
  15-minute notifier Logic App (`flynest-public-alert-notifier`, confirmed firing
  and succeeding on schedule).
- `public-ui/tools/push_settings.py` — pushes only the public subset of `.env` to
  SWA app settings; the repo `.env` also holds pipeline and admin secrets that
  have no business in this app.
- 21 `pub-*` Make targets, mirroring the admin app's.

### Verified against the live site

40 checks across two live suites, all passing, against the real 369-lead table —
auth and lockout, the read-only guarantee (`PATCH`/`DELETE`/`purge`/`users` all
404), notes round-trip, workspace, alert preview, channel gating, and cross-user
isolation (another user's token can neither read nor edit a note). Both suites
create throwaway accounts and delete everything they touch.

Spec recovery works on real posts: a stored Subject-To lead yields
`loan_balance $185,000`, `interest_rate 4.25%`, `monthly_payment $1,450`,
`asking_price $195,000`, `ARV $260,000`, `term 360 months`,
`occupancy_status tenant occupied`.

### Decision amendments forced by reality

- **Email is not live.** ACS Email needs the `Microsoft.Communication` resource
  provider registered on the subscription, and the deploy identity is refused
  `Microsoft.Communication/register/action`. `deployEmail` therefore defaults to
  **false**; the one Owner-level command to switch it on is in the README.
  Consequence handled rather than hidden: signup now reports whether a
  verification email actually went out, and says so plainly when it didn't.
  Accounts still work — sign in with the password, browse, take notes, use push.
- **OAuth is not live** — no client ids are configured yet, so `GET /api/meta`
  advertises no providers and the SPA renders no social buttons. Adding
  `OAUTH_GOOGLE_CLIENT_ID`/`_SECRET` (and running `make pub-settings`) is the
  whole job; the redirect URI is
  `{PUBLIC_SITE_URL}/api/auth/oauth/google/callback`.
- **Web Push is live** — VAPID pair generated and pushed, and it is the only
  delivery channel currently available. `GET /api/meta` reports
  `email:false, webpush:true, sms:false`, and the alert builder offers only push.

### Defects found by screenshotting the deployed site and fixed

1. The header frieze sliced across the nav bar; re-cropped to a footings band.
2. `0 unknown` chips rendered on leads with nothing unknown.
3. The spec ledger stretched two values to opposite ends of a 1100px row.
4. Rows whose specs were *all* blank rendered a ledger of pure empty space.
5. Settings said "Confirmed. Email alerts can be switched on" while the email
   channel was off at the server.
6. `Around the address` cards stretched to the tallest sibling, leaving holes;
   now column-packed.
7. The hero frieze scaled its dimension labels to ~4px on phones; now a legible
   detail crop below 640px.
8. No emoji fallback in the font stack, and Facebook posts are full of them.

### Still open

- Numeric spec criteria run on **parsed** values (option **b** in §5). Option
  **c** — persisting `extracted_specs` from the spokes — remains the exact fix
  and is a values.yaml + sync + deploy away. Nothing in the public app changes
  when it lands: `stored` already wins over `parsed`.
- Open questions 1 and 2 from §10 are unanswered, so the current behaviour is:
  signup is open to anyone, and every lead is visible including `Others`.
