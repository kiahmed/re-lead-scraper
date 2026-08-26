# Public UI — FlyNest Deal Board

The public-facing counterpart to `admin-ui/`. Anyone with an account can browse
the leads the pipeline has already filtered and classified, keep private notes
and a personal workspace, and set up alerts for the kind of deal they want.

**Live:** the hostname in `PUBLIC_SITE_URL` (`.env`), or
`make pub-url`.
Deliberately not written down here — this repo is public.

Design spec and the decisions behind it: [`docs/public_ui_spec.md`](../docs/public_ui_spec.md).

## What a public user can and cannot do

| | |
|---|---|
| **Can** | browse and filter every stored lead; read the recovered deal numbers; write, edit and delete **their own** notes; pin leads and set their own status/tags; create alerts and preview what they match |
| **Cannot** | edit a lead, delete a lead, purge, see anyone else's notes or workspace, list users, or run the notifier |

That second row is enforced by the shape of the code, not by a permission
check: there is no lead-write route in `core/routes.py`, `core/tables.py`
raises if handed `leads` or `appversions`, and every per-user table is
partitioned by the id on the validated session — never by anything in the
request. `api/tests/test_isolation.py` asserts all of it.

The public app also has **its own** user and session tables (`pubusers`,
`pubsessions`). An admin token is not valid here and a public token is not
valid against the admin API.

## Layout

```
public-ui/
  web/          Vite + React 19 + TypeScript (strict) SPA
  api/          Azure Functions v1 Python API — SWA managed functions
  infra/        public-ui.bicep — SWA Free, pub* tables, notifier Logic App
  tools/        push_settings.py — .env -> SWA application settings
```

## Everyday commands

```bash
make pub-install          # deps for both halves
make pub-dev              # Vite :5174 + API :7072
make pub-check            # ruff + tsc + pytest + vitest
make pub-deploy-azure     # build and ship SPA + API
make pub-run-alerts DRY=1 # dry-run the alert sweep
```

## How alerts work

An alert is a criteria object plus delivery settings. The criteria are matched
by `core/criteria.py`, which is the **same function** the Settings preview
calls — so "show what this matches" is not an approximation of the alert, it is
the alert.

A cron Logic App (`flynest-public-alert-notifier`) POSTs `/api/alerts/run`
every 15 minutes with a service token. All the logic lives in `core/digest.py`:

- a **cursor** per alert, set to *now* at creation, so a new alert never dumps
  the backlog on someone
- a **dedupe ledger** keyed `(alert, lead)` that survives a rewound cursor
- **quiet hours** that *hold* rather than drop — the cursor doesn't advance
  past anything withheld
- a **daily cap**, and the message says how many were held back
- one failing channel never aborts the run, and nothing is marked sent unless
  a channel actually succeeded

## The property specs, and why they're marked

The pipeline stores no structured numbers: the classifier writes only
`{"summary": ...}` and the spokes read `loan_balance` / `interest_rate` / `ARV`
straight out of the post text when they generate a follow-up. So `core/specs.py`
recovers them, and every value carries where it came from:

- **`stored`** — the pipeline recorded it (exact). The day `extracted_info`
  starts carrying real fields, they take precedence with no code change.
- **`parsed`** — we read it out of the post. Shown with a dotted underline, and
  hovering quotes the words it was read from.
- **absent** — the post never said. Rendered as a ruled blank, never a zero,
  and every numeric alert rule carries its own *"if the post doesn't say"*
  switch so the user decides what that means.

## Configuration

Everything is read from `.env` locally and from SWA application settings in
production; `make pub-settings` copies the public subset across. A feature whose
config is missing switches itself off and is never advertised by `GET /api/meta`,
so the UI cannot offer a dead button.

| Setting | Effect |
|---|---|
| `NOTIFY_EMAIL_PROVIDER` | `acs` \| `brevo` \| `smtp` \| `off` |
| `NOTIFY_WEBPUSH_ENABLED` | Web Push (default on; needs the VAPID pair) |
| `NOTIFY_SMS_ENABLED` | real SMS (default **off** — costs money, see below) |
| `OAUTH_{GOOGLE,MICROSOFT,FACEBOOK}_CLIENT_ID/_SECRET` | shows that sign-in button |

### Turning email on

Azure has **no free tier** for email. ACS Email is $0.00025/message — about
$2.50/month at 10,000 alerts — and needs no DNS work with an Azure-managed
domain. Provisioning it needs a resource provider that must be registered by a
subscription Owner:

```bash
az provider register --namespace Microsoft.Communication      # Owner required
az deployment group create -g "$AZURE_RESOURCE_GROUP" \
  -f public-ui/infra/public-ui.bicep --parameters deployEmail=true
# then put ACS_CONNECTION_STRING + ACS_SENDER_ADDRESS in .env
make pub-settings
```

For a hard $0 instead, use Brevo (9,000 emails/month free): set
`NOTIFY_EMAIL_PROVIDER=brevo`, `BREVO_API_KEY`, `NOTIFY_FROM_EMAIL`.

Until one of those is done, signup says so plainly rather than telling people
to check an inbox for a link that was never sent — accounts still work, they
just sign in with their password and use push instead of email.

### Turning SMS on

Real SMS is not free anywhere. ACS toll-free is $2/month for the number plus
about $0.01 per segment, **and** toll-free verification must clear before a
single message will deliver — unverified numbers are blocked outright. It also
only reaches the US, Canada and Puerto Rico. Provision a number, file the
verification, then set `NOTIFY_SMS_ENABLED=true` and `ACS_SMS_FROM_NUMBER`.

Note that **Web Push is not a substitute for SMS**: it is free, instant and
worldwide, but it delivers to a browser the user opted in on, not to a phone
number. The UI calls it "Instant push" for exactly that reason.

## Web Push setup

```bash
make pub-vapid        # generate the key pair, once — put both in .env
make pub-settings     # push them to the SWA
```

On iOS, push only works once the site is added to the Home Screen (iOS 16.4+),
which is why the app ships a web manifest and a service worker.
