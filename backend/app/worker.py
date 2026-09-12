"""Durable database queue. Run with python -m backend.app.worker."""
import logging
import time
from sqlalchemy import select
from .config import Settings
from .database import Database
from .delivery import submit
from .matching import match
from .models import Attempt, Job, Profile, Resume, Run, User
from .storage import resume_exists
from .usage import finish_credit, lock_user, reserve, usage, DAY

log = logging.getLogger(__name__)


def tick(db, settings):
    now = time.time()
    with db.transaction() as session:
        stale = session.scalars(select(Attempt).where(Attempt.status == 'SUBMITTING', Attempt.updated_at < now-180).with_for_update()).all()
        for attempt in stale:
            attempt.status = 'UNCERTAIN'
            attempt.reason = 'Worker stopped during submission. Reconciliation is required; no automatic retry.'
            attempt.updated_at = now
    with db.transaction() as session:
        candidate = session.scalar(select(Run).where(Run.status.in_(['QUEUED', 'RUNNING', 'WAITING_QUOTA', 'SCHEDULED']),
                                                    Run.next_at <= now).order_by(Run.next_at, Run.created_at).limit(1))
        if not candidate:
            return False
        # Keep lock order consistent with HTTP/payment transactions: user, then run.
        user = session.scalar(select(User).where(User.id == candidate.user_id).with_for_update(skip_locked=True))
        if not user:
            return False
        run = session.scalar(select(Run).where(Run.id == candidate.id).with_for_update().execution_options(populate_existing=True))
        if not run:
            return False
        if run.status not in ('QUEUED', 'RUNNING', 'WAITING_QUOTA', 'SCHEDULED') or run.next_at > now:
            return True
        # One active external action per user, including across separate runs.
        active = session.scalar(select(Attempt.id).where(Attempt.user_id == user.id, Attempt.status == 'SUBMITTING').limit(1))
        if active:
            run.next_at = now+5
            return True
        profile = session.get(Profile, user.id)
        if not profile or profile.version != run.profile_version:
            run.status, run.message = 'PAUSED', 'Profile changed. Create a new run after reviewing your matches.'
            return True
        if run.status == 'SCHEDULED':
            if not usage(session, user.id, owner=settings.is_owner(user.email))['paid']:
                run.status, run.message = 'COMPLETE', 'Seven-day pass ended. Daily scheduling stopped.'
                return True
            existing = set(session.scalars(select(Attempt.job_id).where(Attempt.user_id == user.id)))
            added = 0
            for job in session.scalars(select(Job).where(Job.user_id == user.id).order_by(Job.created_at.desc())):
                if job.id not in existing and match(run.profile, job.data)['status'] == 'ELIGIBLE':
                    session.add(Attempt(user_id=user.id, run_id=run.id, job_id=job.id))
                    added += 1
                    if added >= run.limit:
                        break
            session.flush()
        attempt = session.scalar(select(Attempt).where(Attempt.run_id == run.id, Attempt.status == 'QUEUED').order_by(Attempt.id).with_for_update().limit(1))
        if not attempt:
            uncertain = session.scalar(select(Attempt.id).where(Attempt.run_id == run.id, Attempt.status == 'UNCERTAIN').limit(1))
            if uncertain:
                run.status, run.message = 'NEEDS_REVIEW', 'An uncertain submission requires provider reconciliation.'
            elif run.daily:
                allowance = usage(session, user.id, owner=settings.is_owner(user.email))
                if allowance['paid']:
                    run.status, run.next_at, run.message = 'SCHEDULED', allowance['resets_at'], 'Next daily run will check newly imported matching jobs.'
                else:
                    run.status, run.message = 'COMPLETE', 'Daily scheduling ended with your pass.'
            else:
                run.status, run.message = 'COMPLETE', 'Run finished. See each application outcome below.'
            return True
        job = session.get(Job, attempt.job_id)
        decision = match(run.profile, job.data)
        attempt.evidence = decision
        if decision['status'] != 'ELIGIBLE':
            attempt.status, attempt.reason = 'SKIPPED', decision['reason']
            return True
        if run.mode == 'manual':
            attempt.status, attempt.reason = 'NEEDS_ACTION', 'Prepared for manual application. Open the job link; no credit charged.'
            return True
        resume = session.get(Resume, run.resume_id)
        if not resume or resume.user_id != user.id or not resume_exists(resume):
            run.status, run.message = 'PAUSED', 'Resume is unavailable. Upload a resume and create a new run.'
            return True
        credit = reserve(session, user.id, attempt.id, owner=settings.is_owner(user.email))
        if not credit:
            allowance = usage(session, user.id, owner=settings.is_owner(user.email))
            run.status, run.message = 'WAITING_QUOTA', 'Application allowance exhausted. Upgrade or wait for your next quota window.'
            run.next_at = allowance['resets_at'] or now+DAY
            return True
        run.status, run.message = 'RUNNING', 'Processing your matching jobs'
        attempt.status, attempt.updated_at = 'SUBMITTING', now
        attempt_id, user_id = attempt.id, user.id
        payload = {'job': job.data, 'profile': run.profile, 'user_reference': user.id}
        demo = user.demo
    # No network calls inside the database transaction. The persisted attempt is the queue receipt.
    try:
        result = submit(settings, payload, resume, attempt_id, demo)
    except Exception:
        result = {'status': 'UNCERTAIN', 'reason': 'Delivery interrupted. Outcome requires review.', 'receipt': ''}
    with db.transaction() as session:
        lock_user(session, user_id)
        attempt = session.get(Attempt, attempt_id)
        if attempt.status == 'SUBMITTING':
            attempt.status, attempt.reason, attempt.receipt = result['status'], result['reason'], result['receipt']
            attempt.updated_at = time.time()
            if result['status'] != 'UNCERTAIN':
                finish_credit(session, attempt_id, result['status'] in ('CONFIRMED', 'SIMULATED'))
    return True


def main():
    settings = Settings.from_env()
    db = Database(settings.database_url)
    db.initialize()
    logging.basicConfig(level=logging.INFO)
    log.info('Application worker ready')
    while True:
        try:
            worked = tick(db, settings)
        except Exception:
            log.exception('Worker iteration failed')
            worked = False
        time.sleep(0.5 if worked else 2)


if __name__ == '__main__':
    main()
