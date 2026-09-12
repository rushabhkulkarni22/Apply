# ApplyWell: running and deploying the web product

The repository now includes a runnable end-to-end web MVP. The new application
does not import or execute the legacy desktop automation script.

## Start locally

From the repository root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.lock
.\.venv\Scripts\python.exe -m backend.run
```

Open **http://localhost:8000** and choose **Explore the demo**. The launcher starts
both the website/API and the background worker. Ctrl+C stops both. The environment
and dependencies have already been created in this workspace.

The demo creates a private sample account, a generated resume, and fictional jobs.
No owner resume, `.env` credentials, or existing job tracker is used. Demo submissions
are SIMULATED, not CONFIRMED. A demo pass never takes payment.

Local product data lives in `runtime/app.db` and `runtime/resumes/`. These are separate
from the old CLI data and ignored by Git. Do not delete `runtime/` if you want to keep
your local accounts. API documentation is at `/docs`.

## What is implemented

- Responsive landing page and authenticated dashboard, including mobile layouts.
- Google ID-token verification, HTTP-only sessions, CSRF checks, origin restrictions.
- PDF/DOCX upload, private download/deletion, text/skill extraction, profile review.
- Confirmed target titles, selected skills, experience, notice period, annual CTC,
  remote/hybrid/on-site preference, location coordinates, radius, salary filtering.
- Job description import and an optional configured licensed JSON job feed.
- Role and three-distinct-skill gates, required skill/experience checks, location
  radius, expiration, salary rules, and transparent reasons for excluded jobs.
- Versioned run inputs, run creation idempotency, durable queue, pause/resume/cancel.
- Simulated delivery, manual handoff, and an application-provider HTTP adapter.
- Lifetime 10-credit trial; INR 199 one-time seven-day pass; seven 24-hour windows
  of 40 credits; reservations, confirmation accounting, and optional daily runs.
- Razorpay order creation, callback verification, signed webhooks, duplicate-event
  handling, refund revocation, and expiry. Real sales are disabled by default.
- Provider status reconciliation for uncertain submissions; user-reported manual
  application status kept separate from provider-confirmed submissions.
- CSV tracking export, account JSON export, personal workspace deletion.
- Docker Compose deployment with PostgreSQL, versioned schema initialization,
  separate API/worker processes, dependency lockfile, and CI test configuration.

## Deliberate implementation choices

The original architecture document proposed Next.js and Celery/Redis. This first
version uses a static HTML/CSS/JavaScript frontend served by FastAPI and a durable
PostgreSQL/SQLite queue. Node.js 24 LTS builds and checks the production frontend;
the runtime serves its compiled static files and does not need a Node server or Redis. Queue state and quota
reservations commit in one database transaction, avoiding a database-to-broker
delivery gap. Workers claim records with locks, and external delivery happens
outside the transaction. The UI and API remain separate modules.

Build browser assets after editing the frontend:

```powershell
npm --prefix apps/web ci
npm --prefix apps/web run build
```

The build validates JavaScript syntax and creates minified, content-hashed assets
in `apps/web/dist/`. Restart the backend after the first build so it serves that
directory. A source checkout without a build still works using the original assets.
Docker builds the frontend in its Node stage and copies only the output to the
Python runtime image. If Node was just installed, open a new terminal to refresh PATH.

This workspace also supports a portable Node installation under `.tools/`. To use
it without changing your machine's PATH:

```powershell
.\.venv\Scripts\python.exe -m backend.frontend install
.\.venv\Scripts\python.exe -m backend.frontend build
```

The helper uses a system Node installation if available, otherwise the verified
project-local Node 24 distribution. `.tools/` and `node_modules/` are not committed.

Resume objects use a private local/shared volume in this deployment, not a public
static folder. Distributed multi-host scaling should introduce an object-store
adapter and explicit worker scheduling rather than sharing an arbitrary filesystem.

## Google sign-in

1. Create a Google OAuth web client in your Google Cloud project.
2. Register your exact HTTPS website origin in authorized JavaScript origins.
3. Set `GOOGLE_CLIENT_ID` and `APP_ORIGIN` in the deployment environment.
4. Disable demo access in production. Users sign in using the Google button.

The backend verifies signature, audience, issuer, expiry, and verified email using
Google's supported token-verification library. Google sign-in is only identity for
this website; it does not connect a LinkedIn account.

Source: [Google server-side verification](https://developers.google.com/identity/gsi/web/guides/verify-google-id-token).

## Job discovery and delivery

Applicants select one or more Indian cities or states from the preference form.
Latitude and longitude are internal catalogue metadata and are never requested from
the applicant. On-site and hybrid listings are accepted when their named location
matches a selection or falls within the chosen nearby radius of a selected city.
Unknown listing locations remain in review instead of being guessed.

The Jobs page creates LinkedIn search links from the applicant's exact approved
titles and selected locations. The applicant reviews a current listing and imports
its description for ApplyWell's role, skill, experience, and location checks. This
does not scrape LinkedIn or claim an unsupported automated LinkedIn integration.

Without a configured provider, real accounts use **manual application mode**.
Users add job descriptions and structured requirements from the original listing.
URLs are not scraped. The worker prepares matching job handoffs. Users open those
links and apply, optionally marking an application USER_REPORTED. No credits are
charged for these handoffs.

`JOB_FEED_URL` may point to a licensed/authorized job feed returning the documented
JSON structure. The user can sync it from Job matches. Daily runs check newly
imported matching jobs already in the database; daily scheduling does not silently
scrape sites or automatically refresh the external feed.

`PROVIDER_URL` and `PROVIDER_TOKEN` connect an application service implementing
[the provider contract](PROVIDER_CONTRACT.md). This is a real HTTP integration
boundary, but no external provider has been supplied or live-validated. LinkedIn's
browser automation prototype remains separate and is not used by website accounts.

## Payments and allowances

Set `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, and `RAZORPAY_WEBHOOK_SECRET`.
Use test credentials first. Configure `/api/billing/webhook` for `payment.captured`
and `payment.refunded`. The verified capture must have INR 19900 paise and belong
to the recorded order. A browser success screen cannot grant access by itself.

Set `SALES_ENABLED=true` only after supported provider delivery has been tested and
payment setup is ready. Configuration rejects sales without the required provider
and payment settings. Production demo access is also rejected at startup.

The pass is not an automatically renewing subscription. Each pass lasts 168 hours,
with seven 24-hour credit windows anchored to activation. Credits do not roll over.
An uncertain submission holds its credit until the provider confirms a result.
Failed, definitively unsubmitted applications release the credit. Applications are
never retried blindly after a submission timeout.

Sources: [Razorpay order/checkout verification](https://razorpay.com/docs/payments/payment-gateway/quick-integration/integration-steps/),
[webhook validation and duplicates](https://razorpay.com/docs/webhooks/validate-test/).

## Container deployment

For the zero-cost pilot requested for this project, use the dedicated
[Render + Supabase deployment guide](FREE_DEPLOYMENT.md). The checked-in
`render.yaml` deploys a single free Docker service, and database-backed resume
storage avoids data loss from Render's ephemeral filesystem.

Install Docker on your deployment machine. Copy `backend/deployment.env.example`
to `backend/deployment.env` and replace every relevant value. Use a long random
alphanumeric PostgreSQL password (or adjust URL encoding in the compose file).

```powershell
docker compose --env-file backend/deployment.env up --build -d
docker compose --env-file backend/deployment.env logs -f web worker
```

The web service binds to localhost port 8000. Put your HTTPS reverse proxy in front
of it and set `APP_ORIGIN` to the public HTTPS origin. Persist and back up both the
PostgreSQL and resume volumes. Encrypt volumes/backups and restrict access to the
host. Keep demo access disabled and publish only the proxy, not PostgreSQL.

An optional Caddy configuration is included to automate HTTPS on your server.
Set `PUBLIC_HOSTNAME` (domain only), `TLS_EMAIL`, and the matching HTTPS `APP_ORIGIN`
in `backend/deployment.env`. Point the domain's DNS A record to the server, permit
inbound ports 80/443, and run:

```powershell
docker compose --env-file backend/deployment.env -f compose.yaml -f compose.https.yaml up --build -d
```

For the initial pilot, a DigitalOcean Basic Droplet with 2 vCPUs and 4 GB RAM in
the Bengaluru region fits this single-host setup. The listed base price checked
on 2026-09-12 is USD 24/month, excluding backups, taxes, domain, and external services.
This recommendation does not provision a server or purchase anything. Capacity
still needs measurement with the actual provider and workload.
[Droplet pricing](https://www.digitalocean.com/pricing/droplets),
[regional availability](https://docs.digitalocean.com/platform/regional-availability/).

`backend.migrate` initializes schema version 2 and upgrades version 1 by adding
private database-backed resume content. Future model changes require explicit,
tested numbered migrations.

Back up the database, for example:

```powershell
docker compose --env-file backend/deployment.env exec -T database pg_dump -U applywell -d applywell -Fc -f /tmp/applywell.dump
docker compose --env-file backend/deployment.env cp database:/tmp/applywell.dump ./applywell.dump
```

Also back up the resume volume at the same maintenance point. Test restoration to
a separate environment before relying on backups. Do not use `down -v` on a live
deployment; it destroys volumes. Configure proxy body limits (6 MB), rate limits,
TLS, monitoring, and retention appropriate to the actual deployment.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests -q
.\.venv\Scripts\python.exe -B -m unittest discover -s tests
```

Optional browser acceptance check against a running local demo:

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.txt
.\.venv\Scripts\python.exe -m backend.browser_smoke
```

The smoke test uses installed Chrome on Windows; pass `--browser` for another
Chromium executable. It checks profile editing, excluded jobs, ten simulations,
demo pass activation, resume upload, job import, account deletion, JavaScript errors,
and mobile overflow. Screenshots are saved
to ignored `artifacts/`. It creates its own demo account.

See [the verification record](VERIFICATION.md) for test results and unverified integrations.

## Remaining production dependencies and limits

- No hosting account, domain, Google client, Razorpay account, or permitted delivery
  provider was supplied. The application has been run locally; it has not been
  published to a cloud account or tested with real payments/applications.
- Docker/PostgreSQL deployment is supplied but was not executed on this Windows
  machine because Docker is not installed. Local integration tests use SQLite.
- PDF extraction supports readable text PDFs, not OCR. DOCX is supported; old DOC
  files must be converted. Profile extraction suggests skills, not verified work
  history. Users enter and confirm remaining fields. No LLM credentials are needed.
- Coordinates currently require explicit input. City names do not automatically
  geocode; remote roles bypass radius checks. Job requirements must be provided
  accurately by the user or feed. Matching does not prove every qualification.
- Document type/size/archive checks are implemented. Dedicated antivirus scanning,
  parsing sandbox isolation, and automated storage-retention jobs are not included.
- One attempted application intent per user/job is enforced. Even cancelled or
  failed attempts remain deduplicated; there is no unrestricted retry button.
- Financial audit records and pseudonymous sign-in/trial-use identifiers are retained
  after personal workspace deletion. In-flight/uncertain submissions require
  reconciliation first. Set and disclose the final retention/support policy before launch.
- Provider outages, support/refund handling, production monitoring, data residency,
  and actual per-application costs must be exercised in a pilot before charging.

The new web runtime uses pypdf for PDFs and does not package the legacy PyMuPDF,
Selenium, or LangChain stack. The original CLI still has its own dependencies.
