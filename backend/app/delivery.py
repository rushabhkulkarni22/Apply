"""A provider must implement idempotency and authoritative confirmation; no scraping."""
import base64
import httpx
from .storage import read_resume


def submit(settings, payload, resume, attempt_id, demo=False):
    if demo:
        return {'status': 'SIMULATED', 'receipt': f'demo-{attempt_id}',
                'reason': 'Demo simulation only. No employer received an application.'}
    if not settings.provider_url:
        return {'status': 'NEEDS_ACTION', 'receipt': '', 'reason': 'Open the job link and apply yourself.'}
    content = read_resume(resume)
    body = {**payload, 'idempotency_key': attempt_id,
            'resume': {'filename': resume.filename, 'content_base64': base64.b64encode(content).decode()}}
    try:
        response = httpx.post(settings.provider_url.rstrip('/') + '/applications', json=body,
                              headers={'Authorization': f'Bearer {settings.provider_token}', 'Idempotency-Key': attempt_id},
                              timeout=45, follow_redirects=False)
        response.raise_for_status()
        result = response.json()
        if result.get('status') == 'CONFIRMED' and isinstance(result.get('receipt'), str) and result['receipt']:
            return {'status': 'CONFIRMED', 'receipt': result['receipt'][:500], 'reason': 'Application confirmed by the configured provider.'}
        if result.get('status') == 'NOT_SUBMITTED':
            return {'status': 'FAILED', 'receipt': '', 'reason': 'Provider confirmed that no application was submitted.'}
        if result.get('status') == 'NEEDS_INPUT':
            return {'status': 'NEEDS_ACTION', 'receipt': '', 'reason': 'Provider requires information. Continue through the job link.'}
    except (httpx.HTTPError, ValueError):
        pass
    return {'status': 'UNCERTAIN', 'receipt': '', 'reason': 'Submission outcome is unknown. Credit remains reserved; do not retry blindly.'}
