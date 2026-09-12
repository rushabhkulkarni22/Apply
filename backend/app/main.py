from contextlib import asynccontextmanager
from dataclasses import asdict
import csv
import hashlib
from io import StringIO
import json
from pathlib import Path
import secrets
import time
from urllib.parse import quote
import httpx
from fastapi import Depends, FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import delete, select, text

from .auth import current_user, google_identity, new_session, token_hash
from .billing import capture, checkout, process_webhook, provider_get, signature_valid
from .config import ROOT, Settings
from .database import Database
from .demo import sample_jobs, sample_pdf, sample_profile
from .matching import match
from .models import Attempt, Credit, Entitlement, Job, LoginSession, Payment, Profile, Resume, Run, User
from .resumes import MAX_BYTES, parse_resume
from .schemas import GoogleInput, JobInput, JobsInput, ProfileInput, RunInput, VerifyPayment
from .storage import delete_resume_file, read_resume, save_resume
from .usage import activate_pass, finish_credit, lock_user, usage


def owned(session, model, identity, user_id):
    row = session.get(model, identity)
    if not row or row.user_id != user_id:
        raise HTTPException(404, 'Record not found')
    return row


def save_jobs(session, user_id, rows):
    ids = []
    for data in rows:
        existing = session.scalar(select(Job).where(Job.user_id == user_id, Job.source == data['source'], Job.external_id == data['external_id']))
        if existing:
            existing.data = data
            ids.append(existing.id)
        else:
            item = Job(user_id=user_id, source=data['source'], external_id=data['external_id'], data=data)
            session.add(item)
            session.flush()
            ids.append(item.id)
    return ids


def create_app(settings=None):
    settings = settings or Settings.from_env()
    db = Database(settings.database_url)

    @asynccontextmanager
    async def lifespan(app):
        db.initialize()
        Path(settings.storage_dir).mkdir(parents=True, exist_ok=True)
        yield
        db.engine.dispose()

    app = FastAPI(title='ApplyWell', version='0.1.0', lifespan=lifespan)
    app.state.db, app.state.settings = db, settings

    @app.middleware('http')
    async def security(request, call_next):
        origin = request.headers.get('origin')
        if request.method not in ('GET', 'HEAD', 'OPTIONS') and origin and origin != settings.app_origin:
            return JSONResponse({'detail': 'Origin is not allowed'}, status_code=403)
        try:
            if int(request.headers.get('content-length', '0')) > 6*1024*1024:
                return JSONResponse({'detail': 'Request exceeds 6 MB'}, status_code=413)
        except ValueError:
            return JSONResponse({'detail': 'Invalid request length'}, status_code=400)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Cross-Origin-Opener-Policy'] = 'same-origin-allow-popups'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self' https://accounts.google.com https://checkout.razorpay.com; style-src 'self' 'unsafe-inline' https://accounts.google.com; img-src 'self' data: https:; connect-src 'self' https://accounts.google.com https://*.razorpay.com; frame-src https://accounts.google.com https://*.razorpay.com; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
        if request.url.path.startswith('/api'):
            response.headers['Cache-Control'] = 'no-store'
        return response

    @app.get('/api/health')
    def health():
        with db.sessions() as session:
            session.execute(text('SELECT 1'))
        return {'status': 'ok', 'version': '0.1.0'}

    @app.get('/api/config')
    def public_config():
        google_ready = bool(settings.google_client_id and not settings.google_client_id.startswith('setup-required'))
        return {'google_client_id': settings.google_client_id if google_ready else '', 'google_ready': google_ready,
                'demo_enabled': settings.demo_enabled,
                'delivery': 'provider' if settings.provider_url else 'manual', 'sales_enabled': settings.sales_enabled,
                'price_inr': 199, 'free_limit': 10, 'daily_limit': 40, 'pass_days': 7}

    @app.post('/api/auth/demo')
    def demo_login(response: Response):
        if not settings.demo_enabled:
            raise HTTPException(404, 'Demo is disabled')
        with db.transaction() as session:
            user = User(subject='demo:'+secrets.token_hex(16), name='Alex Morgan', email='demo@example.com', demo=True)
            session.add(user)
            session.flush()
            session.add(Profile(user_id=user.id, data=sample_profile()))
            save_jobs(session, user.id, sample_jobs())
            # Generate a real sample PDF; never reuse the workspace owner's resume.
            content = sample_pdf()
            path, stored = save_resume(settings, user.id, 'demo.pdf', content)
            session.add(Resume(user_id=user.id, filename='Demo resume.pdf', path=path, content=stored,
                               sha256=hashlib.sha256(content).hexdigest(), extracted=parse_resume('demo.pdf', content)))
        return new_session(db, settings, user, response)

    @app.post('/api/auth/google')
    def google_login(body: GoogleInput, response: Response):
        identity = google_identity(body.credential, settings.google_client_id)
        with db.transaction() as session:
            user = session.scalar(select(User).where(User.subject == 'google:'+identity['sub']))
            if not user:
                user = User(subject='google:'+identity['sub'], name=identity.get('name', 'Applicant'), email=identity['email'])
                session.add(user)
                session.flush()
            else:
                user.name, user.email = identity.get('name', user.name), identity['email']
        return new_session(db, settings, user, response)

    @app.get('/api/me')
    def me(request: Request, user=Depends(current_user)):
        return {'id': user.id, 'name': user.name, 'email': user.email, 'demo': user.demo, 'csrf': request.state.csrf}

    @app.post('/api/auth/logout')
    def logout(request: Request, response: Response, user=Depends(current_user)):
        with db.transaction() as session:
            login = session.get(LoginSession, token_hash(request.cookies.get('applywell_session', '')))
            if login:
                session.delete(login)
        response.delete_cookie('applywell_session')
        return {'ok': True}

    @app.get('/api/profile')
    def get_profile(user=Depends(current_user)):
        with db.sessions() as session:
            profile = session.get(Profile, user.id)
            return {'version': profile.version, 'data': profile.data} if profile else {'version': 0, 'data': None}

    @app.put('/api/profile')
    def update_profile(body: ProfileInput, user=Depends(current_user)):
        with db.transaction() as session:
            lock_user(session, user.id)
            profile = session.get(Profile, user.id)
            if profile:
                profile.data, profile.version = body.model_dump(), profile.version+1
            else:
                profile = Profile(user_id=user.id, data=body.model_dump())
                session.add(profile)
            session.flush()
            return {'version': profile.version, 'data': profile.data}

    @app.post('/api/resumes')
    def upload_resume(file: UploadFile = File(...), user=Depends(current_user)):
        content = file.file.read(MAX_BYTES+1)
        name = Path((file.filename or 'resume').replace('\\', '/')).name[:200]
        try:
            extracted = parse_resume(name, content)
        except Exception as exc:
            detail = str(exc) if isinstance(exc, ValueError) else 'This document could not be read. Try another PDF or DOCX.'
            raise HTTPException(422, detail)
        with db.transaction() as session:
            lock_user(session, user.id)
            rows = session.scalars(select(Resume).where(Resume.user_id == user.id)).all()
            if len(rows) >= 10:
                raise HTTPException(409, 'Keep at most 10 resume versions; delete an unused version first')
            path, stored = save_resume(settings, user.id, name, content)
            item = Resume(user_id=user.id, filename=name, path=path, content=stored,
                          sha256=hashlib.sha256(content).hexdigest(), extracted=extracted)
            session.add(item)
            session.flush()
            return {'id': item.id, 'filename': name, 'extracted': extracted}

    @app.get('/api/resumes')
    def list_resumes(user=Depends(current_user)):
        with db.sessions() as session:
            return [{'id': r.id, 'filename': r.filename, 'created_at': r.created_at, 'extracted': r.extracted}
                    for r in session.scalars(select(Resume).where(Resume.user_id == user.id).order_by(Resume.created_at.desc()))]

    @app.get('/api/resumes/{resume_id}/download')
    def download_resume(resume_id: str, user=Depends(current_user)):
        with db.sessions() as session:
            item = owned(session, Resume, resume_id, user.id)
            disposition = "attachment; filename*=UTF-8''" + quote(item.filename, safe='')
            return Response(read_resume(item), media_type='application/octet-stream',
                            headers={'Content-Disposition': disposition})

    @app.delete('/api/resumes/{resume_id}')
    def delete_resume(resume_id: str, user=Depends(current_user)):
        with db.transaction() as session:
            lock_user(session, user.id)
            item = owned(session, Resume, resume_id, user.id)
            active = session.scalar(select(Run.id).where(Run.resume_id == item.id, Run.status.not_in(['COMPLETE', 'CANCELLED'])).limit(1))
            if active:
                raise HTTPException(409, 'Cancel active runs using this resume first')
            try:
                delete_resume_file(settings, item)
            except ValueError as exc:
                raise HTTPException(409, str(exc))
            session.delete(item)
        return {'ok': True}

    @app.post('/api/jobs')
    def import_jobs(body: JobsInput, user=Depends(current_user)):
        with db.transaction() as session:
            lock_user(session, user.id)
            return {'ids': save_jobs(session, user.id, [j.model_dump() for j in body.jobs])}

    @app.post('/api/jobs/sync')
    def sync_jobs(user=Depends(current_user)):
        if not settings.job_feed_url:
            raise HTTPException(503, 'No licensed job feed configured. Import job descriptions instead.')
        try:
            with httpx.stream('GET', settings.job_feed_url, headers={'Authorization': f'Bearer {settings.provider_token}'}, timeout=30) as response:
                response.raise_for_status()
                chunks, size = [], 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > 4*1024*1024:
                        raise ValueError('Feed too large')
                    chunks.append(chunk)
            body = JobsInput.model_validate_json(b''.join(chunks))
        except Exception:
            raise HTTPException(502, 'Job feed is unavailable or has invalid data')
        return import_jobs(body, user)

    @app.get('/api/jobs')
    def jobs(user=Depends(current_user)):
        with db.sessions() as session:
            profile = session.get(Profile, user.id)
            attempted = {a.job_id: a.status for a in session.scalars(select(Attempt).where(Attempt.user_id == user.id))}
            result = []
            for job in session.scalars(select(Job).where(Job.user_id == user.id).order_by(Job.created_at.desc()).limit(1000)):
                decision = match(profile.data, job.data) if profile and profile.data.get('confirmed') else {'status': 'NEEDS_REVIEW', 'reason': 'Confirm your profile first', 'matched_skills': []}
                result.append({'id': job.id, **job.data, 'match': decision, 'application_status': attempted.get(job.id)})
            return sorted(result, key=lambda j: j['match']['status'] != 'ELIGIBLE')

    @app.get('/api/usage')
    def get_usage(user=Depends(current_user)):
        with db.sessions() as session:
            return {**usage(session, user.id), 'demo': user.demo}

    @app.post('/api/runs')
    def create_run(body: RunInput, request: Request, user=Depends(current_user)):
        key = request.headers.get('idempotency-key', '')
        if not key or len(key) > 100:
            raise HTTPException(400, 'Supply an Idempotency-Key of at most 100 characters')
        if not body.authorized:
            raise HTTPException(422, 'Confirm the application scope before starting')
        with db.transaction() as session:
            lock_user(session, user.id)
            existing = session.scalar(select(Run).where(Run.user_id == user.id, Run.idempotency_key == key))
            if existing:
                return {'id': existing.id, 'status': existing.status}
            profile = session.get(Profile, user.id)
            if not profile or not profile.data.get('confirmed'):
                raise HTTPException(422, 'Confirm your profile first')
            owned(session, Resume, body.resume_id, user.id)
            allowance = usage(session, user.id)
            mode = 'demo' if user.demo else 'provider' if settings.provider_url else 'manual'
            if body.daily and (not allowance['paid'] or mode == 'manual'):
                raise HTTPException(422, 'Daily application scheduling requires an active pass and supported delivery')
            attempted = set(session.scalars(select(Attempt.job_id).where(Attempt.user_id == user.id)))
            query = select(Job).where(Job.user_id == user.id).order_by(Job.created_at.desc())
            if body.job_ids:
                query = query.where(Job.id.in_(body.job_ids))
            candidates = [j for j in session.scalars(query) if j.id not in attempted and match(profile.data, j.data)['status'] == 'ELIGIBLE'][:body.limit]
            if not candidates:
                raise HTTPException(409, 'No new eligible jobs. Review your preferences or import more jobs.')
            if mode != 'manual' and allowance['remaining'] <= 0:
                raise HTTPException(402, 'Your allowance is used. Activate a pass or wait for the next quota window.')
            run = Run(user_id=user.id, idempotency_key=key, mode=mode, limit=body.limit,
                      profile_version=profile.version, profile=profile.data, resume_id=body.resume_id, daily=body.daily)
            session.add(run)
            session.flush()
            for job in candidates:
                session.add(Attempt(user_id=user.id, run_id=run.id, job_id=job.id))
            return {'id': run.id, 'status': run.status}

    @app.get('/api/runs')
    def list_runs(user=Depends(current_user)):
        with db.sessions() as session:
            result = []
            for run in session.scalars(select(Run).where(Run.user_id == user.id).order_by(Run.created_at.desc()).limit(50)):
                attempts = []
                for attempt, job in session.execute(select(Attempt, Job).join(Job, Attempt.job_id == Job.id).where(Attempt.run_id == run.id)):
                    attempts.append({'id': attempt.id, 'title': job.data['title'], 'company': job.data['company'],
                                     'url': job.data['url'], 'status': attempt.status, 'reason': attempt.reason, 'receipt': attempt.receipt})
                result.append({'id': run.id, 'status': run.status, 'mode': run.mode, 'message': run.message,
                               'daily': run.daily, 'next_at': run.next_at, 'created_at': run.created_at, 'attempts': attempts})
            return result

    @app.post('/api/runs/{run_id}/{action}')
    def change_run(run_id: str, action: str, user=Depends(current_user)):
        if action not in ('pause', 'resume', 'cancel'):
            raise HTTPException(404, 'Unknown action')
        with db.transaction() as session:
            lock_user(session, user.id)
            run = owned(session, Run, run_id, user.id)
            if run.status in ('COMPLETE', 'CANCELLED'):
                raise HTTPException(409, 'This run has finished')
            if action == 'resume':
                profile = session.get(Profile, user.id)
                if not profile or profile.version != run.profile_version:
                    raise HTTPException(409, 'Profile changed; cancel this run and create a new one')
                run.status, run.next_at = 'QUEUED', 0
            else:
                run.status = 'PAUSED' if action == 'pause' else 'CANCELLED'
                run.message = 'Stopped before the next application; an in-flight submission may still finish.'
                if action == 'cancel':
                    run.daily = False
                    for attempt in session.scalars(select(Attempt).where(Attempt.run_id == run.id, Attempt.status == 'QUEUED')):
                        attempt.status, attempt.reason = 'CANCELLED', 'Cancelled by user before submission'
            return {'status': run.status}

    @app.get('/api/export')
    def export(user=Depends(current_user)):
        stream = StringIO()
        writer = csv.writer(stream)
        writer.writerow(['Company', 'Title', 'URL', 'Status', 'Reason'])
        def safe(value):
            return "'"+value if value.lstrip().startswith(('=', '+', '-', '@')) else value
        for run in list_runs(user):
            for attempt in run['attempts']:
                writer.writerow([safe(str(attempt[k])) for k in ('company', 'title', 'url', 'status', 'reason')])
        return Response(stream.getvalue(), media_type='text/csv', headers={'Content-Disposition': 'attachment; filename="applications.csv"'})

    @app.post('/api/attempts/{attempt_id}/manual-confirm')
    def manual_confirm(attempt_id: str, user=Depends(current_user)):
        with db.transaction() as session:
            lock_user(session, user.id)
            attempt = owned(session, Attempt, attempt_id, user.id)
            run = session.get(Run, attempt.run_id)
            if run.mode != 'manual' or attempt.status != 'NEEDS_ACTION':
                raise HTTPException(409, 'Only a manual handoff can be marked as user-reported')
            attempt.status, attempt.reason = 'USER_REPORTED', 'User reported applying manually; not provider-verified. No credit charged.'
        return {'ok': True}

    @app.post('/api/attempts/{attempt_id}/reconcile')
    def reconcile(attempt_id: str, user=Depends(current_user)):
        if not settings.provider_url or user.demo:
            raise HTTPException(503, 'No provider status service is configured')
        with db.sessions() as session:
            attempt = owned(session, Attempt, attempt_id, user.id)
            if attempt.status != 'UNCERTAIN':
                raise HTTPException(409, 'Only an uncertain submission needs reconciliation')
        try:
            response = httpx.get(settings.provider_url.rstrip('/')+'/applications/'+attempt_id,
                                 headers={'Authorization':f'Bearer {settings.provider_token}'},timeout=20)
            response.raise_for_status()
            result = response.json()
        except Exception:
            raise HTTPException(502, 'Provider status could not be retrieved; the reservation remains held')
        with db.transaction() as session:
            lock_user(session, user.id)
            attempt = owned(session, Attempt, attempt_id, user.id)
            if attempt.status != 'UNCERTAIN':
                return {'status':attempt.status}
            if result.get('status') == 'CONFIRMED' and isinstance(result.get('receipt'),str) and result['receipt']:
                attempt.status, attempt.receipt = 'CONFIRMED', result['receipt'][:500]
                attempt.reason = 'Provider reconciled and confirmed the submission.'
                finish_credit(session,attempt.id,True)
            elif result.get('status') == 'NOT_SUBMITTED':
                attempt.status, attempt.reason = 'FAILED', 'Provider confirmed no submission. Credit released.'
                finish_credit(session,attempt.id,False)
            attempt.updated_at = time.time()
            return {'status':attempt.status}

    @app.get('/api/account/export')
    def account_export(user=Depends(current_user)):
        return JSONResponse({'account':{'name':user.name,'email':user.email},'profile':get_profile(user),
                             'resumes':list_resumes(user),'jobs':jobs(user),'runs':list_runs(user),'usage':get_usage(user)},
                            headers={'Content-Disposition':'attachment; filename="applywell-data.json"'})

    @app.delete('/api/account')
    def delete_account(response: Response, user=Depends(current_user)):
        with db.transaction() as session:
            account = lock_user(session,user.id)
            active = session.scalar(select(Attempt.id).where(Attempt.user_id == user.id,Attempt.status.in_(['SUBMITTING','UNCERTAIN'])).limit(1))
            if active:
                raise HTTPException(409,'An in-flight or uncertain application must be reconciled before account removal')
            account.prior_free_usage = usage(session,user.id)['free_used']
            for resume in session.scalars(select(Resume).where(Resume.user_id == user.id)):
                try:
                    delete_resume_file(settings, resume)
                except ValueError:
                    pass
            for model in (Credit,Attempt,Run,Job,Resume,Profile,LoginSession):
                session.execute(delete(model).where(model.user_id == user.id))
            # Retain only pseudonymous identity and financial history to prevent trial resets.
            account.name,account.email = 'Deleted account',''
            for entitlement in session.scalars(select(Entitlement).where(Entitlement.user_id == user.id)):
                entitlement.revoked = True
        response.delete_cookie('applywell_session')
        return {'ok':True,'retained':'Pseudonymous account identity, prior trial usage, and payment records.'}

    @app.post('/api/billing/demo-pass')
    def demo_pass(user=Depends(current_user)):
        if not settings.demo_enabled or not user.demo:
            raise HTTPException(404, 'Demo billing unavailable')
        with db.transaction() as session:
            activate_pass(session, user.id, 'demo-pass-'+user.id)
            for run in session.scalars(select(Run).where(Run.user_id == user.id, Run.status == 'WAITING_QUOTA')):
                run.status, run.next_at = 'QUEUED', 0
        return {'ok': True}

    @app.post('/api/billing/checkout')
    def start_checkout(user=Depends(current_user)):
        return checkout(db, settings, user)

    @app.post('/api/billing/verify')
    def verify_payment(body: VerifyPayment, user=Depends(current_user)):
        if not signature_valid(f'{body.razorpay_order_id}|{body.razorpay_payment_id}'.encode(), body.razorpay_signature, settings.razorpay_key_secret):
            raise HTTPException(400, 'Payment signature is invalid')
        with db.transaction() as session:
            lock_user(session,user.id)
            order = session.scalar(select(Payment).where(Payment.order_id == body.razorpay_order_id, Payment.user_id == user.id).with_for_update())
            if not order:
                raise HTTPException(404, 'Order not found')
            try:
                payment = provider_get(settings, 'payments/'+body.razorpay_payment_id)
            except Exception:
                raise HTTPException(502, 'Payment verification is pending. Refresh usage shortly.')
            capture(session, order, payment)
        return {'ok': True}

    @app.post('/api/billing/webhook')
    async def webhook(request: Request):
        raw = await request.body()
        if len(raw) > 1024*1024 or not signature_valid(raw, request.headers.get('x-razorpay-signature', ''), settings.razorpay_webhook_secret):
            raise HTTPException(400, 'Invalid webhook')
        event_id = request.headers.get('x-razorpay-event-id', '')
        if not event_id or len(event_id) > 150:
            raise HTTPException(400, 'Missing event identity')
        try:
            payload = json.loads(raw)
        except ValueError:
            raise HTTPException(400, 'Invalid JSON')
        if not isinstance(payload, dict):
            raise HTTPException(400, 'Invalid event')
        process_webhook(db, settings, event_id, payload)
        return {'ok': True}

    web_root = ROOT/'apps'/'web'
    if (web_root/'dist'/'index.html').is_file():
        web_root = web_root/'dist'
    app.mount('/static', StaticFiles(directory=web_root), name='static')

    @app.get('/')
    def index():
        return FileResponse(web_root/'index.html', headers={'Cache-Control':'no-cache'})

    return app
