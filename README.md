# ApplyWell

ApplyWell is a resume-driven job matching and application-management web app.
It accepts PDF or DOCX resumes, collects the applicant's preferences, and admits
only jobs with an approved target title and at least three distinct selected skills.

## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.lock
.\.venv\Scripts\python.exe -m backend.frontend build
.\.venv\Scripts\python.exe -m backend.run
```

Open **http://localhost:8000** and choose **Explore the demo**. Demo applications
and payments are simulated and never use a real resume or employer.

- `apps/web/`: responsive browser frontend.
- `backend/app/`: API, authentication, profiles, matching, billing, and worker.
- `backend/tests/`: product integration tests.
- `job_applications/matching.py`: deterministic role and skill matching core.
- `render.yaml`: free pilot deployment blueprint.
- `compose.yaml`: PostgreSQL, web service, and worker self-hosted deployment.
- `runtime/`: private local application data, excluded from Git.

See [web setup and current limits](docs/WEB_APP.md),
[the free Render + Supabase deployment guide](docs/FREE_DEPLOYMENT.md),
[provider integration contracts](docs/PROVIDER_CONTRACT.md), and
[the architecture](docs/PRODUCT_ARCHITECTURE.md).

Google login, real payments, and automatic delivery require external service
configuration. The website uses manual handoffs when no delivery provider is
configured, and paid checkout is disabled by default.

## Verify

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests -q
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -p test_job_matching.py
```
