import hashlib
import secrets
import time
from fastapi import HTTPException, Request, Response
from sqlalchemy import select
from .models import LoginSession, User


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def new_session(db, settings, user, response):
    raw = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(32)
    with db.transaction() as session:
        session.add(LoginSession(token=token_hash(raw), user_id=user.id, csrf=csrf,
                                 expires_at=time.time() + settings.session_seconds))
    response.set_cookie('applywell_session', raw, httponly=True, samesite='lax',
                        secure=settings.environment == 'production', max_age=settings.session_seconds, path='/')
    return {'id': user.id, 'name': user.name, 'email': user.email, 'demo': user.demo, 'csrf': csrf}


def current_user(request: Request):
    raw = request.cookies.get('applywell_session', '')
    db = request.app.state.db
    with db.sessions() as session:
        login = session.get(LoginSession, token_hash(raw))
        if not login or login.expires_at <= time.time():
            raise HTTPException(401, 'Please sign in')
        user = session.get(User, login.user_id)
        if not user:
            raise HTTPException(401, 'Account unavailable')
        if request.method not in ('GET', 'HEAD', 'OPTIONS'):
            if not secrets.compare_digest(request.headers.get('x-csrf-token', ''), login.csrf):
                raise HTTPException(403, 'Session verification failed; refresh the page')
        request.state.csrf = login.csrf
        return user


def google_identity(credential, client_id):
    if not client_id:
        raise HTTPException(503, 'Google sign-in is not configured')
    from google.auth.transport.requests import Request as GoogleRequest
    from google.oauth2 import id_token
    try:
        identity = id_token.verify_oauth2_token(credential, GoogleRequest(), client_id)
        if not identity.get('email_verified') or not identity.get('sub'):
            raise ValueError('Unverified identity')
        return identity
    except Exception:
        raise HTTPException(401, 'Google identity could not be verified')
