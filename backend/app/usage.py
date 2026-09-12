import time
from sqlalchemy import func, select
from .models import Credit, Entitlement, User

DAY = 86400


def lock_user(session, user_id):
    return session.scalar(select(User).where(User.id == user_id).with_for_update())


def usage(session, user_id, now=None, owner=False):
    now = time.time() if now is None else now
    free = session.scalar(select(func.count()).select_from(Credit).where(
        Credit.user_id == user_id, Credit.bucket == 'free', Credit.status.in_(['RESERVED', 'CONSUMED'])))
    account = session.get(User, user_id)
    free += account.prior_free_usage if account else 0
    entitlement = session.scalar(select(Entitlement).where(
        Entitlement.user_id == user_id, Entitlement.starts_at <= now,
        Entitlement.expires_at > now, Entitlement.revoked == False).order_by(Entitlement.starts_at.desc()))
    result = {'free_used': free, 'free_remaining': max(0, 10-free), 'paid': False,
              'daily_used': 0, 'daily_limit': 40, 'remaining': max(0, 10-free),
              'bucket': 'free', 'expires_at': None, 'resets_at': None, 'owner_access': owner}
    if owner:
        window = int(now // DAY)
        bucket = f'owner:{window}'
        used = session.scalar(select(func.count()).select_from(Credit).where(
            Credit.user_id == user_id, Credit.bucket == bucket, Credit.status.in_(['RESERVED', 'CONSUMED'])))
        result.update(paid=True, bucket=bucket, daily_used=used, remaining=max(0, 40-used),
                      resets_at=(window+1)*DAY)
        return result
    if entitlement:
        window = int((now-entitlement.starts_at)//DAY)
        bucket = f'{entitlement.id}:{window}'
        used = session.scalar(select(func.count()).select_from(Credit).where(
            Credit.user_id == user_id, Credit.bucket == bucket, Credit.status.in_(['RESERVED', 'CONSUMED'])))
        result.update(paid=True, bucket=bucket, daily_used=used, remaining=max(0, 40-used),
                      expires_at=entitlement.expires_at,
                      resets_at=min(entitlement.expires_at, entitlement.starts_at+(window+1)*DAY))
    return result


def reserve(session, user_id, attempt_id, owner=False):
    lock_user(session, user_id)
    existing = session.scalar(select(Credit).where(Credit.attempt_id == attempt_id))
    if existing:
        return existing if existing.status == 'RESERVED' else None
    allowance = usage(session, user_id, owner=owner)
    if allowance['remaining'] <= 0:
        return None
    credit = Credit(user_id=user_id, attempt_id=attempt_id, bucket=allowance['bucket'])
    session.add(credit)
    session.flush()
    return credit


def finish_credit(session, attempt_id, confirmed):
    credit = session.scalar(select(Credit).where(Credit.attempt_id == attempt_id).with_for_update())
    if credit and credit.status == 'RESERVED':
        credit.status = 'CONSUMED' if confirmed else 'RELEASED'


def activate_pass(session, user_id, payment_id):
    lock_user(session, user_id)
    existing = session.scalar(select(Entitlement).where(Entitlement.payment_id == payment_id))
    if existing:
        return existing
    now = time.time()
    latest = session.scalar(select(func.max(Entitlement.expires_at)).where(
        Entitlement.user_id == user_id, Entitlement.revoked == False))
    start = max(now, latest or now)
    item = Entitlement(user_id=user_id, payment_id=payment_id, starts_at=start, expires_at=start+7*DAY)
    session.add(item)
    session.flush()
    return item
