# Matching: first implementation

The LinkedIn workflow now evaluates discovered and restored jobs before passing
them to Easy Apply. It evaluates again at the start of each attempt and immediately
before either Submit application action. Missing page identity, title, description,
or readable matching evidence blocks the application.

Configure `job_applications/matching_config.json`:

- `allowed_titles`: complete approved titles, compared without case differences.
  Add title variants explicitly; mixed titles do not receive an automatic pass.
- `selected_skills`: skills to count, intersected with the parsed resume skills.
- `minimum_skills`: at least three distinct supported skills (default three).
- `version`: increment when changing the policy. A policy hash is also saved.

Defaults target Data Engineer variants and PySpark, AWS, SQL, Python. Machine
Learning Engineer is excluded even with all four skills. AWS/Amazon Web Services
and Python/Python 3 count once. Spark alone does not establish PySpark.
Negated or instruction-like skill evidence triggers review. These are conservative
text rules, not a complete semantic requirements parser.

Preview without logging in, reading your resume, calling a model, or applying:

```powershell
python -B -m job_applications.match_preview
```

Use custom JSON with `--input path/to/examples.json`:

```json
{
  "candidate_skills": ["Python", "SQL", "AWS"],
  "jobs": [
    {"title": "Data Engineer", "description": "Build pipelines with Python, SQL and AWS."}
  ]
}
```

Run regression tests:

```powershell
python -B -m unittest discover -s tests
```

Matching outcomes are printed and stored separately in the `match_decisions` table
in `data/job_agent.db`. Records contain reason, evidence, policy/hash, profile skill
hash, and job snapshot hash. Rejected jobs are not recorded as applications and can
be evaluated again after profile/policy changes. Navigation failures print a review
reason and are excluded. The production database is only touched when the workflow
runs; tests use temporary databases.

Current limits:

- This first slice enforces title and skill matching only. Experience requirements,
  salary, location radius, job expiry, and required-versus-preferred skill semantics
  still need structured extraction and policy gates. ELIGIBLE here means title/skill
  eligibility, not proof of meeting every employer requirement.
- DOM selectors have fixture coverage, not validation in a logged-in live session.
  An unrecognized page blocks rather than falling back to search-card content.
- The existing discovery batch limit remains. Filtering can produce fewer eligible
  jobs; it does not automatically replenish the batch to hit an application target.
- Naukri and the manual-search stage do not use these new checks yet.
- The current CLI still starts desktop UI on import of `hr_apply.py`; extracting a
  side-effect-free application engine is the next refactoring phase.
- This prototype does not establish permitted commercial LinkedIn automation;
  the platform-access dependency remains documented in PRODUCT_ARCHITECTURE.md.
