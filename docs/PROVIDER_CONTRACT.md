# Job-feed and application-provider contracts

Only configure services you are authorized to use. These contracts are our
integration interfaces, not claims that LinkedIn or Naukri implements these APIs.
Credentials are configured on the server and never sent to the browser.

## Job feed

`GET JOB_FEED_URL` sends `Authorization: Bearer PROVIDER_TOKEN`.
The response is at most 4 MB, with at most 100 jobs per sync:

```json
{
  "jobs": [{
    "external_id": "provider-job-123",
    "source": "your-provider",
    "title": "Data Engineer",
    "company": "Example employer",
    "url": "https://example.com/careers/123",
    "description": "Build data pipelines using Python, SQL and AWS.",
    "location": "Pune",
    "latitude": 18.5204,
    "longitude": 73.8567,
    "work_mode": "hybrid",
    "minimum_experience": 2,
    "salary_max_inr": 2400000,
    "required_skills": ["Python", "SQL"],
    "expires_at": null
  }]
}
```

Allowed work modes: remote, hybrid, onsite, unknown. Compensation is annual INR,
not lakhs. Times are Unix seconds. Unknown values should be null/unknown and must
not be fabricated to pass matching. Duplicate `(user, source, external_id)` imports
update the job snapshot; workers re-evaluate updated requirements before submission.

## Submit an application

`POST {PROVIDER_URL}/applications`

Headers: `Authorization: Bearer ...`, `Idempotency-Key: <attempt ID>`.

```json
{
  "idempotency_key": "immutable-attempt-id",
  "user_reference": "opaque-user-id",
  "job": {"external_id": "provider-job-123", "source": "your-provider"},
  "profile": {"full_name": "User-confirmed name", "skills": ["Python", "SQL", "AWS"]},
  "resume": {"filename": "resume.pdf", "content_base64": "..."}
}
```

Actual `job` and `profile` include the validated fields documented in `/docs`.
The provider must support the intended platform, user authorization and permitted
access, reject closed jobs, validate requirements, and avoid duplicate submissions
for the same idempotency key. Never invent missing screening answers or consent.

Supported JSON responses:

```json
{"status":"CONFIRMED","receipt":"authoritative-job-specific-receipt"}
```

```json
{"status":"NOT_SUBMITTED"}
```

```json
{"status":"NEEDS_INPUT"}
```

CONFIRMED requires a nonempty receipt. NOT_SUBMITTED must definitively mean no
external submission occurred. NEEDS_INPUT must also mean no submission occurred;
the UI offers manual handoff without claiming a confirmed application.

Transport errors, unexpected responses, and missing confirmation receipts become
UNCERTAIN. The quota reservation remains held and no automatic retry occurs.

## Reconcile an uncertain result

`GET {PROVIDER_URL}/applications/{attempt ID}`, with the same bearer token.
Return CONFIRMED with receipt, NOT_SUBMITTED, or an unresolved status. The user can
press **Check status** in the tracker. A 404 or network error does not prove that
submission did not occur and does not release a credit.

Provider ownership, per-user platform connection, and authorization verification
must be implemented by the actual integration. The generic adapter is not itself
a LinkedIn account-connection service.
