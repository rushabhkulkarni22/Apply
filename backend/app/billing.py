import hashlib
import hmac
import time
import httpx
from fastapi import HTTPException
from sqlalchemy import select
from .models import Entitlement, Payment, Run, WebhookEvent
from .usage import activate_pass


def signature_valid(content, signature, secret):
    return bool(secret) and hmac.compare_digest(hmac.new(secret.encode(), content, hashlib.sha256).hexdigest(), signature)


def provider_get(settings, path):
    response = httpx.get('https://api.razorpay.com/v1/' + path,
                         auth=(settings.razorpay_key_id, settings.razorpay_key_secret), timeout=20)
    response.raise_for_status()
    return response.json()


def capture(session, order, payment):
    if payment.get('order_id') != order.order_id or payment.get('amount') != 19900 or payment.get('currency') != 'INR' or payment.get('status') != 'captured':
        raise HTTPException(400, 'Payment amount, currency or captured status does not match the order')
    if order.status == 'REFUNDED':
        return
    order.payment_id = payment['id']
    order.status = 'PAID'
    activate_pass(session, order.user_id, payment['id'])
    for run in session.scalars(select(Run).where(Run.user_id == order.user_id, Run.status == 'WAITING_QUOTA')):
        run.status, run.next_at = 'QUEUED', 0


def checkout(db, settings, user):
    if user.demo:
        raise HTTPException(400, 'Use the demo pass button; demo accounts cannot make payments')
    if not settings.sales_enabled:
        raise HTTPException(503, 'Paid checkout is not enabled for this deployment')
    with db.transaction() as session:
        from .usage import lock_user, usage
        lock_user(session, user.id)
        if usage(session, user.id)['paid']:
            raise HTTPException(409, 'Your seven-day pass is already active')
        order = session.scalar(select(Payment).where(Payment.user_id == user.id, Payment.status == 'CREATED',
                                                     Payment.created_at > time.time()-3600).order_by(Payment.created_at.desc()))
        if not order:
            try:
                response = httpx.post('https://api.razorpay.com/v1/orders', json={'amount': 19900, 'currency': 'INR'},
                                      auth=(settings.razorpay_key_id, settings.razorpay_key_secret), timeout=20)
                response.raise_for_status()
                data = response.json()
                order = Payment(user_id=user.id, order_id=data['id'])
                session.add(order)
            except (httpx.HTTPError, ValueError, KeyError):
                raise HTTPException(502, 'Payment provider is unavailable. Please try later.')
        return {'key': settings.razorpay_key_id, 'order_id': order.order_id, 'amount': 19900, 'currency': 'INR'}


def process_webhook(db, settings, event_id, payload):
    payment_entity = payload.get('payload', {}).get('payment', {}).get('entity', {})
    refund_entity = payload.get('payload', {}).get('refund', {}).get('entity', {})
    event = payload.get('event', '')
    entity = payment_entity
    with db.transaction() as session:
        from .usage import lock_user
        if event == 'refund.processed':
            payment_id = refund_entity.get('payment_id', '')
            order = session.scalar(select(Payment).where(Payment.payment_id == payment_id))
        else:
            order = session.scalar(select(Payment).where(Payment.order_id == entity.get('order_id', '')))
        if order:
            lock_user(session,order.user_id)
            order = session.scalar(select(Payment).where(Payment.id == order.id).with_for_update().execution_options(populate_existing=True))
        if session.get(WebhookEvent, event_id):
            return
        if event in ('payment.captured', 'payment.refunded', 'refund.processed'):
            if not order:
                raise HTTPException(409, 'Order is not recorded yet; retry delivery')
            if event == 'payment.captured':
                capture(session, order, entity)
            else:
                # Razorpay includes both entities for refund.processed. A partial
                # refund does not revoke the full pass; a completed full refund does.
                full_refund = event == 'payment.refunded' or (
                    refund_entity.get('status') == 'processed' and
                    payment_entity.get('amount_refunded', 0) >= payment_entity.get('amount', 1)
                )
                if full_refund:
                    order.status = 'REFUNDED'
                    entitlement = session.scalar(select(Entitlement).where(Entitlement.payment_id == order.payment_id))
                    if entitlement:
                        entitlement.revoked = True
        session.add(WebhookEvent(id=event_id))
