from dataclasses import replace
import hashlib
import hmac
from io import BytesIO
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.matching import match
from backend.app.demo import sample_jobs, sample_profile
from backend.app.models import Attempt, Credit, Entitlement, Job, Payment, Profile, Resume, Run, User
from backend.app.usage import activate_pass, reserve, usage
from backend.app.worker import tick
from backend.app.resumes import parse_resume


@pytest.fixture
def system(tmp_path):
    settings = Settings(database_url='sqlite:///'+str(tmp_path/'test.db'), storage_dir=str(tmp_path/'resumes'))
    app = create_app(settings)
    with TestClient(app) as client:
        user = client.post('/api/auth/demo').json()
        client.headers['X-CSRF-Token'] = user['csrf']
        yield client, app.state.db, settings, user


def start(client, limit=10, key='test-run', daily=False):
    resume = client.get('/api/resumes').json()[0]['id']
    return client.post('/api/runs', json={'resume_id': resume, 'limit': limit, 'daily': daily, 'authorized': True},
                       headers={'Idempotency-Key': key})


def drain(db, settings, count=60):
    for _ in range(count):
        if not tick(db, settings):
            break


def test_full_demo_journey(system):
    client, db, settings, user = system
    assert client.get('/').status_code == 200
    assert client.get('/api/health').json()['status'] == 'ok'
    jobs = client.get('/api/jobs').json()
    assert len([j for j in jobs if j['match']['status'] == 'ELIGIBLE']) == 12
    assert next(j for j in jobs if j['title']=='Machine Learning Engineer')['match']['status'] == 'REJECTED'
    assert start(client).status_code == 200
    drain(db, settings)
    runs = client.get('/api/runs').json()
    assert runs[0]['status'] == 'COMPLETE'
    assert {a['status'] for a in runs[0]['attempts']} == {'SIMULATED'}
    assert client.get('/api/usage').json()['free_remaining'] == 0
    assert start(client, key='second').status_code == 402
    assert client.post('/api/billing/demo-pass').status_code == 200
    assert client.get('/api/usage').json()['remaining'] == 40
    assert start(client, key='paid').status_code == 200
    drain(db, settings)
    assert client.get('/api/usage').json()['remaining'] == 38
    assert 'SIMULATED' in client.get('/api/export').text


def test_csrf_and_tenant_isolation(system):
    client, db, settings, user = system
    resume = client.get('/api/resumes').json()[0]['id']
    run_id = start(client).json()['id']
    with TestClient(create_app(settings)) as other:
        second = other.post('/api/auth/demo').json()
        other.headers['X-CSRF-Token'] = second['csrf']
        assert other.get('/api/resumes/'+resume+'/download').status_code == 404
        assert other.delete('/api/resumes/'+resume).status_code == 404
        assert other.post('/api/runs/'+run_id+'/cancel').status_code == 404
        assert other.post('/api/runs', headers={'Idempotency-Key':'x'}, json={'resume_id':resume,'authorized':True}).status_code == 404
        other.headers.pop('X-CSRF-Token')
        assert other.post('/api/billing/demo-pass').status_code == 403
    assert client.post('/api/auth/demo', headers={'Origin':'https://attacker.example'}).status_code == 403


def test_pdf_docx_upload_and_rejection(system):
    client, db, settings, user = system
    from docx import Document
    document = Document()
    document.add_paragraph('Avery Smith\nPython SQL AWS PySpark data engineer with three years of experience.')
    data = BytesIO()
    document.save(data)
    response = client.post('/api/resumes', files={'file':('resume.docx',data.getvalue(),'application/vnd.openxmlformats-officedocument.wordprocessingml.document')})
    assert response.status_code == 200, response.text
    assert 'PySpark' in response.json()['extracted']['skills']
    resume_id = response.json()['id']
    assert client.get(f'/api/resumes/{resume_id}/download').content == data.getvalue()
    assert client.delete(f'/api/resumes/{resume_id}').status_code == 200
    assert client.get(f'/api/resumes/{resume_id}/download').status_code == 404
    assert client.post('/api/resumes',files={'file':('bad.pdf',b'fake pdf')}).status_code == 422
    assert client.post('/api/resumes',files={'file':('bad.doc',b'old doc')}).status_code == 422
    assert client.post('/api/resumes',files={'file':('huge.pdf',b'%PDF-'+b'a'*(5*1024*1024))}).status_code == 422


def test_database_resume_storage_survives_without_files(tmp_path):
    settings = Settings(database_url='sqlite:///'+str(tmp_path/'database-storage.db'),
                        storage_dir=str(tmp_path/'unused'), resume_storage='database')
    with TestClient(create_app(settings)) as client:
        user = client.post('/api/auth/demo').json()
        client.headers['X-CSRF-Token'] = user['csrf']
        resume = client.get('/api/resumes').json()[0]
        downloaded = client.get(f'/api/resumes/{resume["id"]}/download')
        assert downloaded.status_code == 200 and downloaded.content.startswith(b'%PDF-')
        assert not Path(settings.storage_dir).exists() or not list(Path(settings.storage_dir).rglob('*.*'))
        with client.app.state.db.sessions() as session:
            stored = session.get(Resume, resume['id'])
            assert stored.content == downloaded.content and stored.path == ''


def test_profile_rules():
    profile = sample_profile()
    jobs = sample_jobs()
    assert match(profile,jobs[0])['status'] == 'ELIGIBLE'
    assert match(profile,jobs[12])['status'] == 'REJECTED'
    assert match(profile,jobs[13])['status'] == 'REJECTED'
    assert match(profile,jobs[14])['status'] == 'REJECTED'
    assert match(profile,jobs[15])['status'] == 'REJECTED'
    job = {**jobs[0], 'minimum_experience':None}
    assert match(profile,job)['status'] == 'NEEDS_REVIEW'
    assert match(profile,{**jobs[0],'expires_at':time.time()-1})['status'] == 'REJECTED'
    assert match(profile,{**jobs[0],'required_skills':['Java']})['status'] == 'REJECTED'
    assert match({**profile,'strict_salary':True},{**jobs[0],'salary_max_inr':None})['status'] == 'NEEDS_REVIEW'
    assert match({**profile,'strict_salary':True},{**jobs[0],'salary_max_inr':100})['status'] == 'REJECTED'
    assert match(profile,{**jobs[0],'latitude':None,'longitude':None})['status'] == 'ELIGIBLE'
    assert match(profile,{**jobs[0],'location':'Unspecified','latitude':None,'longitude':None})['status'] == 'NEEDS_REVIEW'
    assert match({**profile,'preferred_locations':['Mumbai']},jobs[0])['status'] == 'REJECTED'
    assert match({**profile,'preferred_locations':['state:Maharashtra']},jobs[0])['status'] == 'ELIGIBLE'


def test_location_catalogue_and_profile_validation(system):
    client, _, _, _ = system
    regions = client.get('/api/locations').json()['regions']
    assert any(region['state'] == 'Maharashtra' and 'Pune' in region['cities'] for region in regions)
    profile = client.get('/api/profile').json()['data']
    profile['preferred_locations'] = ['Pune', 'state:Karnataka']
    profile['latitude'] = profile['longitude'] = None
    assert client.put('/api/profile', json=profile).status_code == 200
    profile['preferred_locations'] = ['Atlantis']
    assert client.put('/api/profile', json=profile).status_code == 422


def test_run_idempotency_pause_cancel_and_profile_change(system):
    client, db, settings, user = system
    first = start(client).json()
    assert start(client).json()['id'] == first['id']
    assert client.post(f'/api/runs/{first["id"]}/pause').status_code == 200
    drain(db,settings)
    assert client.get('/api/usage').json()['free_used'] == 0
    profile = client.get('/api/profile').json()['data']
    profile['notice_days'] = 45
    assert client.put('/api/profile',json=profile).status_code == 200
    assert client.post(f'/api/runs/{first["id"]}/resume').status_code == 409
    assert client.post(f'/api/runs/{first["id"]}/cancel').status_code == 200
    assert {a['status'] for a in client.get('/api/runs').json()[0]['attempts']} == {'CANCELLED'}


def test_atomic_quota_reservations(system):
    client, db, settings, user = system
    start(client,limit=12)
    with db.sessions() as session:
        ids = list(session.scalars(select(Attempt.id)))
    def claim(identity):
        with db.transaction() as session:
            return reserve(session,user['id'],identity) is not None
    with ThreadPoolExecutor(max_workers=6) as pool:
        outcomes = list(pool.map(claim,ids))
    assert sum(outcomes) == 10
    assert client.get('/api/usage').json()['free_remaining'] == 0


def test_seven_day_windows_and_expiry(system):
    client, db, settings, user = system
    with db.transaction() as session:
        item = activate_pass(session,user['id'],'paid-test')
        start_time, end_time = item.starts_at, item.expires_at
        assert end_time-start_time == 7*86400
        for day in range(7):
            result = usage(session,user['id'],start_time+day*86400+1)
            assert result['paid'] and result['bucket'].endswith(':'+str(day))
        assert not usage(session,user['id'],end_time)['paid']


def test_unknown_submission_retains_reservation(system):
    client, db, settings, user = system
    start(client,limit=1)
    with patch('backend.app.worker.submit',return_value={'status':'UNCERTAIN','reason':'network timeout','receipt':''}) as provider:
        drain(db,settings)
    provider.assert_called_once()
    assert client.get('/api/runs').json()[0]['status'] == 'NEEDS_REVIEW'
    assert client.get('/api/usage').json()['free_used'] == 1
    with db.sessions() as session:
        assert session.scalar(select(Credit)).status == 'RESERVED'


def test_failed_submission_releases_credit(system):
    client, db, settings, user = system
    start(client,limit=1)
    with patch('backend.app.worker.submit',return_value={'status':'FAILED','reason':'not submitted','receipt':''}):
        drain(db,settings)
    assert client.get('/api/usage').json()['free_used'] == 0


def test_stale_worker_never_retries_submit(system):
    client, db, settings, user = system
    start(client,limit=1)
    with db.transaction() as session:
        attempt = session.scalar(select(Attempt))
        reserve(session,user['id'],attempt.id)
        attempt.status,attempt.updated_at = 'SUBMITTING',time.time()-300
    with patch('backend.app.worker.submit') as provider:
        drain(db,settings)
    provider.assert_not_called()
    assert client.get('/api/runs').json()[0]['attempts'][0]['status'] == 'UNCERTAIN'


def test_manual_handoff_does_not_charge(system):
    client, db, settings, user = system
    with db.transaction() as session:
        session.get(User,user['id']).demo = False
    start(client,limit=2)
    drain(db,settings)
    assert {a['status'] for a in client.get('/api/runs').json()[0]['attempts']} == {'NEEDS_ACTION'}
    assert client.get('/api/usage').json()['free_used'] == 0
    assert client.post('/api/billing/checkout').status_code == 503


def test_payment_duplicates_and_refund(system):
    client, db, settings, user = system
    from backend.app.billing import process_webhook
    with db.transaction() as session:
        session.add(Payment(user_id=user['id'],order_id='order_1'))
    payment = {'id':'pay_1','order_id':'order_1','amount':19900,'currency':'INR','status':'captured'}
    payload = {'event':'payment.captured','payload':{'payment':{'entity':payment}}}
    process_webhook(db,settings,'event_1',payload)
    process_webhook(db,settings,'event_1',payload)
    process_webhook(db,settings,'event_2',payload)
    with db.sessions() as session:
        assert len(session.scalars(select(Entitlement)).all()) == 1
    payload={'event':'refund.processed','payload':{
        'refund':{'entity':{'id':'rfnd_1','payment_id':'pay_1','amount':19900,'status':'processed'}},
        'payment':{'entity':{**payment,'amount_refunded':19900,'refund_status':'full'}}}}
    process_webhook(db,settings,'event_3',payload)
    assert client.get('/api/usage').json()['paid'] is False


def test_partial_refund_does_not_revoke_pass(system):
    client, db, settings, user = system
    with db.transaction() as session:
        session.add(Payment(user_id=user['id'], order_id='order_partial', payment_id='pay_partial', status='CAPTURED'))
        activate_pass(session, user['id'], 'pay_partial')
    payload={'event':'refund.processed','payload':{
        'refund':{'entity':{'id':'rfnd_partial','payment_id':'pay_partial','amount':100,'status':'processed'}},
        'payment':{'entity':{'id':'pay_partial','order_id':'order_partial','amount':19900,
                             'amount_refunded':100,'currency':'INR','status':'captured','refund_status':'partial'}}}}
    from backend.app.billing import process_webhook
    process_webhook(db, settings, 'event-partial', payload)
    assert client.get('/api/usage').json()['paid'] is True


def test_invalid_payment_and_auth(system):
    client, db, settings, user = system
    assert client.post('/api/billing/webhook',json={}).status_code == 400
    assert client.post('/api/billing/verify',json={'razorpay_order_id':'x','razorpay_payment_id':'y','razorpay_signature':'bad'}).status_code == 400
    assert client.post('/api/auth/google',json={'credential':'forged'}).status_code == 503
    profile=sample_profile();profile['selected_skills']=['AWS','Python','Kotlin']
    assert client.put('/api/profile',json=profile).status_code == 422
    assert client.post('/api/auth/logout').status_code == 200
    assert client.get('/api/me').status_code == 401


def test_production_configuration_guard(monkeypatch):
    monkeypatch.setenv('ENVIRONMENT','production')
    monkeypatch.setenv('DEMO_ENABLED','true')
    with pytest.raises(ValueError):
        Settings.from_env()


def test_placeholder_google_client_is_not_exposed(system):
    _, _, settings, _ = system
    pending = replace(settings, google_client_id='setup-required.apps.googleusercontent.com')
    with TestClient(create_app(pending)) as client:
        config = client.get('/api/config').json()
        assert config['google_ready'] is False
        assert config['google_client_id'] == ''


def test_paid_daily_cap(system):
    client, db, settings, user = system
    client.post('/api/billing/demo-pass')
    jobs = [{**sample_jobs()[0], 'external_id':f'bulk-{i}'} for i in range(50)]
    assert client.post('/api/jobs',json={'jobs':jobs}).status_code == 200
    assert start(client,limit=40,key='paid40').status_code == 200
    drain(db,settings)
    assert client.get('/api/usage').json()['remaining'] == 0
    assert client.get('/api/usage').json()['daily_used'] == 40
    assert start(client,key='overflow').status_code == 402
    reset = client.get('/api/usage').json()['resets_at']
    with db.sessions() as session:
        assert usage(session,user['id'],reset+1)['remaining'] == 40


def test_daily_schedule_stops_at_expiry(system):
    client, db, settings, user = system
    client.post('/api/billing/demo-pass')
    assert start(client,limit=1,daily=True).status_code == 200
    drain(db,settings)
    assert client.get('/api/runs').json()[0]['status'] == 'SCHEDULED'
    expiry=client.get('/api/usage').json()['expires_at']
    with patch('time.time',return_value=expiry+1):
        drain(db,settings)
    assert client.get('/api/runs').json()[0]['status'] == 'COMPLETE'


def test_deletion_retains_trial_history_and_removes_resumes(system):
    client, db, settings, user = system
    start(client,limit=1)
    drain(db,settings)
    assert client.get('/api/account/export').status_code == 200
    assert client.delete('/api/account').status_code == 200
    assert client.get('/api/me').status_code == 401
    assert not list(Path(settings.storage_dir).rglob('*.pdf'))
    with db.sessions() as session:
        account=session.get(User,user['id'])
        assert account.email == '' and account.prior_free_usage == 1
        assert usage(session,user['id'])['free_remaining'] == 9
        assert session.scalar(select(Resume)) is None


def test_manual_confirmation_is_not_provider_confirmation(system):
    client, db, settings, user = system
    with db.transaction() as session:
        session.get(User,user['id']).demo = False
    start(client,limit=1)
    drain(db,settings)
    attempt=client.get('/api/runs').json()[0]['attempts'][0]['id']
    assert client.post(f'/api/attempts/{attempt}/manual-confirm').status_code == 200
    assert client.get('/api/runs').json()[0]['attempts'][0]['status'] == 'USER_REPORTED'
    assert client.get('/api/usage').json()['free_used'] == 0


def test_valid_signed_webhook(system):
    client, db, settings, user = system
    settings=replace(settings,razorpay_webhook_secret='test-secret')
    with db.transaction() as session:
        session.add(Payment(user_id=user['id'],order_id='order_signed'))
    payload={'event':'payment.captured','payload':{'payment':{'entity':{
        'id':'pay_signed','order_id':'order_signed','amount':19900,'currency':'INR','status':'captured'}}}}
    body=json.dumps(payload).encode()
    signature=hmac.new(b'test-secret',body,hashlib.sha256).hexdigest()
    with TestClient(create_app(settings)) as incoming:
        assert incoming.post('/api/billing/webhook',content=body,headers={'X-Razorpay-Signature':signature,'X-Razorpay-Event-Id':'signed-1'}).status_code == 200
    assert client.get('/api/usage').json()['paid']


def test_provider_delivery_contract(system):
    from backend.app.delivery import submit
    from unittest.mock import Mock
    client,db,settings,user=system
    with db.sessions() as session:
        resume=session.scalar(select(Resume))
    settings=replace(settings,provider_url='https://provider.example',provider_token='test')
    response=Mock()
    response.json.return_value={'status':'CONFIRMED','receipt':'receipt-123'}
    with patch('backend.app.delivery.httpx.post',return_value=response) as post:
        result=submit(settings,{'job':sample_jobs()[0]},resume,'attempt-123')
    assert result['status']=='CONFIRMED'
    assert post.call_args.kwargs['headers']['Idempotency-Key']=='attempt-123'
    assert post.call_args.kwargs['json']['resume']['content_base64']
    response.json.return_value={'status':'CONFIRMED'}
    with patch('backend.app.delivery.httpx.post',return_value=response):
        assert submit(settings,{},resume,'x')['status']=='UNCERTAIN'
