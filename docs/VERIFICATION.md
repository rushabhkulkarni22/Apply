# Implementation verification

Verified locally on Windows on 2026-09-12 with Python 3.14 and project-local
Node.js 24.19.0 (official distribution, SHA-256 checked against Node's checksum file).

| Check | Result |
| --- | --- |
| Frontend JavaScript syntax and production asset build | Passed |
| npm dependency audit at install | No known vulnerabilities reported |
| Backend integration tests | 21 passed |
| Existing matching and screening regression tests | 34 passed |
| Browser acceptance flow against compiled frontend | Passed |
| Mobile horizontal-overflow check at 390px | Passed |

The browser flow covered demo login, PDF upload, profile confirmation, job import,
wrong-role exclusion, ten simulated applications, demo pass activation, mobile
layout, and personal workspace deletion. It checked for browser JavaScript errors.

Backend tests cover tenant isolation, CSRF, file/database resume storage, PDF/DOCX upload validation, matching,
run idempotency, pause/cancel, profile version changes, concurrent trial credits,
40-credit daily cap, seven-day expiry, scheduling stop, submission uncertainty,
failed-submission credit release, worker recovery, manual handoff, duplicate payment
events, refunds, signed webhooks, provider response validation, and data deletion.

Run locally:

```powershell
.\.venv\Scripts\python.exe -m backend.frontend build
.\.venv\Scripts\python.exe -m pytest backend/tests -q
.\.venv\Scripts\python.exe -B -m unittest discover -s tests
```

With the server/worker running from `python -m backend.run`:

```powershell
.\.venv\Scripts\python.exe -m backend.browser_smoke --require-built
```

Screenshots are written to ignored `artifacts/`. Tests use temporary databases and
generated resumes. No real application or payment was submitted during verification.

Not verified: live Google OAuth credentials, live Razorpay transactions, an actual
application provider, Docker image execution, PostgreSQL runtime, public DNS/TLS,
or cloud deployment. These require the target accounts/environment. Backend tests
currently emit upstream Starlette/httpx deprecation warnings; the tested flows pass.
