# Free pilot deployment: Render + Supabase

This deployment keeps the website, Python API, queue worker, PostgreSQL data, and
resume uploads in one zero-cost pilot architecture:

- Render Free Web Service runs the Docker image and supplies the HTTPS URL.
- Supabase Free supplies PostgreSQL. `RESUME_STORAGE=database` stores private
  resume bytes in PostgreSQL because Render's free filesystem is ephemeral.
- Google Identity Services authenticates users.
- Razorpay Orders, Checkout, and a signed webhook activate the INR 199 pass.

The checked-in [`render.yaml`](../render.yaml) configures the Render service. It
starts both the API and database-backed worker in one container.

## 1. Put this repository on GitHub

Create a private GitHub repository and push this project. Confirm that `.env`,
`backend/deployment.env`, `runtime/`, `.venv/`, `.tools/`, `node_modules/`, and
resume documents are absent from the commit. Render can connect to a private
repository after its GitHub app is authorized.

## 2. Create the Supabase database

Create a free Supabase project. In **Connect**, copy the pooled PostgreSQL URI.
Prefer the session pooler URI for this long-running container. It normally begins
with `postgresql://`; ApplyWell automatically selects the installed psycopg driver.
Keep the database password only in Render's secret environment settings.

Supabase's free plan currently includes a 500 MB database and 1 GB file storage.
This pilot stores resumes in the database, so monitor database size closely. At
the 5 MB upload limit, this is suitable only for a small trial. Move resumes to
private object storage before inviting many users.

## 3. Deploy the Render Blueprint

In Render, choose **New > Blueprint**, connect the GitHub repository, and select
the repository's `render.yaml`. Supply these secret values when prompted:

| Variable | Value |
| --- | --- |
| `DATABASE_URL` | Supabase pooled PostgreSQL URI |
| `GOOGLE_CLIENT_ID` | Google OAuth Web client ID |
| `RAZORPAY_KEY_ID` | Razorpay live/test API key ID |
| `RAZORPAY_KEY_SECRET` | Matching API key secret |
| `RAZORPAY_WEBHOOK_SECRET` | A new random webhook signing secret |
| `PROVIDER_URL` | Leave empty until a permitted application provider exists |
| `PROVIDER_TOKEN` | Leave empty until that provider exists |

Render automatically supplies `RENDER_EXTERNAL_URL`; ApplyWell uses it as the
allowed HTTPS origin. The first start initializes schema version 2. Check
`https://<service>.onrender.com/api/health` for `{"status":"ok"}`.

## 4. Configure Google login

In Google Cloud Console, create an OAuth 2.0 **Web application** client. Add the
exact Render URL, without a trailing slash, to **Authorized JavaScript origins**.
If Google initially shows the app in testing mode, add the pilot users as test
users or publish the consent screen as appropriate. Save the client ID in Render
and redeploy.

## 5. Configure Razorpay correctly

The supplied payment-page URL, `https://razorpay.me/@rushabhmadhukarkulkarni`, is
not enough to activate an ApplyWell account. It does not create an ApplyWell-owned
order tied to the signed-in user. Do not place that link in the product checkout.

Create Razorpay API keys in test mode first. In Razorpay Webhooks, add:

```text
https://<service>.onrender.com/api/billing/webhook
```

Subscribe to `payment.captured` and `refund.processed`, and use the same webhook
secret in Razorpay and `RAZORPAY_WEBHOOK_SECRET`. The server checks the signature,
recorded order, captured status, INR currency, and exact amount of 19900 paise
before granting the one-time seven-day pass. Run one real INR 199 transaction and
refund test before opening sales.

Keep `SALES_ENABLED=false` for the initial deployment. The configuration refuses
to enable sales until both Razorpay and a permitted application-delivery provider
are configured. This prevents charging for the promised confirmed-application
service while the site can only prepare manual handoffs.

## Free-tier operating limits

Render free web services sleep after 15 minutes without inbound traffic and can
take about a minute to wake. Their local files disappear on sleep/restart, which
is why this deployment uses PostgreSQL resume storage. A sleeping service also
cannot execute scheduled daily work; it resumes queued work when a user or webhook
wakes it. Render describes free instances as preview/hobby infrastructure rather
than production infrastructure.

Supabase free projects pause after one week of inactivity and do not include
automatic backups. Export the database regularly during the pilot. A service that
accepts payment eventually needs always-on compute, backups, monitoring, and an
object store; those requirements cannot be provided reliably by this free setup.

Current platform references:

- [Render free service limits](https://render.com/docs/free)
- [Render default environment variables](https://render.com/docs/environment-variables)
- [Supabase pricing and free quotas](https://supabase.com/pricing)
- [Google server-side ID token verification](https://developers.google.com/identity/gsi/web/guides/verify-google-id-token)
- [Razorpay Orders and Checkout](https://razorpay.com/docs/payments/payment-gateway/quick-integration/integration-steps/)
- [Razorpay webhook validation](https://razorpay.com/docs/webhooks/validate-test/)
