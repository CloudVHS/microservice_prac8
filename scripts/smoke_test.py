"""Real HTTP/RabbitMQ end-to-end checks. Run after docker compose up --wait."""
import argparse
import base64
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import time
import urllib.error
import urllib.request
import urllib.parse
import uuid

SERVICES = ['user', 'practice', 'grammar', 'lexicon', 'dictionary', 'reference', 'payment', 'notification']
PORTS = dict(zip(SERVICES, range(8001, 8009)))
checks = []
token = ''


def call(service, method, path, body=None, expected=200, headers=None, auth=True):
    url = f'http://127.0.0.1:{PORTS[service]}' + urllib.parse.quote(path, safe='/?=&:%')
    h = {'Content-Type': 'application/json'}
    if auth and token:
        h['Authorization'] = 'Bearer ' + token
    h.update(headers or {})
    request = urllib.request.Request(url, data=json.dumps(body, ensure_ascii=False).encode() if body is not None else None, method=method, headers=h)
    try:
        response = urllib.request.urlopen(request, timeout=15)
    except urllib.error.HTTPError as exc:
        response = exc
    raw = response.read()
    value = json.loads(raw) if 'application/json' in response.headers.get('Content-Type', '') else raw.decode('utf-8')
    assert response.status == expected, f'{method} {url}: expected {expected}, got {response.status}: {value}'
    checks.append(dict(service=service, method=method, path=path, status=response.status))
    return value


def eventually(function, predicate, description):
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        try:
            value = function()
            if predicate(value):
                return value
        except (AssertionError, urllib.error.URLError):
            pass  # Readiness may temporarily be 503 during reconnection.
        time.sleep(0.3)
    raise AssertionError('Timeout: ' + description)


def command(service, id, action, **kwargs):
    return call(service, 'POST', f'/api/v1/sessions/{id}/commands', dict(action=action, **kwargs))


def run():
    global token
    for service in SERVICES:
        health = call(service, 'GET', '/health', auth=False)
        assert health['database'] == 'ok' and health['broker'] == 'connected'
        schema = call(service, 'GET', '/openapi.json', auth=False)
        route_count = sum(len([m for m in methods if m in ['get', 'post', 'put', 'patch', 'delete']]) for methods in schema['paths'].values())
        assert route_count == 5, (service, route_count)
    email = 'test-' + uuid.uuid4().hex[:12] + '@pr7.local'
    credentials = dict(email=email, password='Student-pr7-2026!')
    user = call('user', 'POST', '/api/v1/users', dict(**credentials, display_name='Проверка ПР7'), expected=201)
    call('user', 'POST', '/api/v1/users', dict(**credentials, display_name='Повтор'), expected=409)
    call('user', 'POST', '/api/v1/sessions', dict(email=email, password='wrong'), expected=401)
    token = call('user', 'POST', '/api/v1/sessions', credentials, expected=201)['access_token']
    call('user', 'GET', '/api/v1/users/me', auth=False, expected=401)
    call('user', 'PATCH', '/api/v1/users/me', {'hsk_level': 0}, expected=422)
    call('user', 'PATCH', '/api/v1/users/me', {'hsk_level': 2, 'goal': 'tourism'})
    call('user', 'PATCH', '/api/v1/users/me', {}, expected=422)
    call('notification', 'POST', '/notification-permissions', {}, expected=404)
    call('notification', 'POST', '/api/v1/notification-permissions', {'allowed': True})
    words = call('dictionary', 'GET', '/api/v1/words?q=привет')['items']
    assert words
    word_id = words[0]['id']
    call('dictionary', 'GET', '/api/v1/words?count=0', expected=422)
    call('dictionary', 'GET', '/api/v1/words/not-a-uuid', expected=422)
    call('dictionary', 'POST', f'/api/v1/words/{word_id}/commands', {'action': 'select_level'})
    sound = call('dictionary', 'POST', f'/api/v1/words/{word_id}/commands', {'action': 'listen'})
    assert base64.b64decode(sound['audio_base64']).startswith(b'RIFF') and sound['speech'] is False
    call('dictionary', 'POST', f'/api/v1/words/{word_id}/commands', {'action': 'open_canvas'})
    for _ in range(2):
        assert call('dictionary', 'POST', f'/api/v1/words/{word_id}/commands', {'action': 'mark_learned'})['learned']
    call('dictionary', 'POST', '/api/v1/words', {}, expected=422)
    ex = call('reference', 'GET', '/api/v1/exams')['items']; assert ex[0]['demo']
    uni = call('reference', 'GET', '/api/v1/universities')['items'][0]
    update = {k: uni[k] for k in ['name', 'city', 'description']}
    call('reference', 'PATCH', '/api/v1/universities/' + uni['id'], update, expected=403)
    text = call('reference', 'GET', '/api/v1/templates/application-letter'); assert '尊敬' in text
    admin = call('user', 'POST', '/api/v1/sessions', dict(email='admin@pr7.local', password=os.environ.get('DEMO_ADMIN_PASSWORD', 'Admin-pr7-2026!')), expected=201)['access_token']
    call('reference', 'PATCH', '/api/v1/universities/' + uni['id'], update, headers={'Authorization': 'Bearer ' + admin})
    call('user', 'PATCH', '/api/v1/users/me', {'action': 'grant_rights', 'target_user_id': user['id'], 'role': 'admin'}, expected=403)
    session_ids = {}
    for service, answers in [('lexicon', ['привет', 'спасибо', 'учиться']), ('grammar', ['我学习汉语', '不', '吗']), ('practice', ['你好', '谢谢', 'Я изучаю китайский язык'])]:
        call(service, 'GET', '/api/v1/tasks')
        session = call(service, 'POST', '/api/v1/sessions', {}, expected=201)
        id = session['id']; session_ids[service] = id
        assert all('accepted_answers' not in task for task in session['tasks'])
        call(service, 'POST', f'/api/v1/sessions/{id}/commands', {'action': 'finish_session'}, expected=409)
        command(service, id, 'build_sequence'); command(service, id, 'start_session')
        data = [dict(task_id=task['id'], text=text) for task, text in zip(session['tasks'], answers)]
        wrong = [dict(task_id=task['id'], text='ошибка') for task in session['tasks']]
        if service == 'lexicon':
            command(service, id, 'view_lexicon')
            call(service, 'POST', f'/api/v1/sessions/{id}/commands', dict(action='finish_session', answers=wrong), expected=409)
        elif service == 'grammar':
            command(service, id, 'view_rules')
            command(service, id, 'send_ai_request', answers=wrong)
            call(service, 'POST', f'/api/v1/sessions/{id}/commands', {'action': 'finish_session'}, expected=409)
            command(service, id, 'send_ai_request', answers=data)
            command(service, id, 'generate_grammar')
        else:
            call(service, 'POST', f'/api/v1/sessions/{id}/commands', {'action': 'play_audio'}, expected=409)
            for action in ['request_audio', 'start_audio', 'play_audio', 'finish_audio', 'start_translation']:
                command(service, id, action)
            command(service, id, 'translate', answers=data)
            command(service, id, 'send_ai_request', answers=data)
            command(service, id, 'finish_translation')
        result = command(service, id, 'finish_session', **({'answers': data} if service == 'lexicon' else {}))
        assert result['status'] == 'completed' and result['assessment']['score'] == 100
        command(service, id, 'finish_session')
        call(service, 'GET', f'/api/v1/sessions/{id}')
    progress = eventually(lambda: call('lexicon', 'GET', '/api/v1/tasks')['progress'], lambda x: x['completed_sessions'] == 3 and x['learned_words'] == 1, 'learning events delivered once')
    headers = {'Idempotency-Key': uuid.uuid4().hex}
    payment = call('payment', 'POST', '/api/v1/payments', {'plan_code': 'premium_month'}, expected=201, headers=headers)
    repeat = call('payment', 'POST', '/api/v1/payments', {'plan_code': 'premium_month'}, headers=headers)
    assert repeat['id'] == payment['id']
    path = '/api/v1/payments/' + payment['id'] + '/commands'
    confirmation = dict(action='confirm', provider_transaction_id='demo-' + uuid.uuid4().hex)
    call('payment', 'POST', path, confirmation, expected=403)
    internal = {'X-Service-Token': os.environ.get('INTERNAL_TOKEN', 'pr7-local-service-token'), 'X-User-Id': user['id']}
    call('payment', 'POST', path, confirmation, headers=internal)
    call('payment', 'POST', path, confirmation, headers=internal)
    eventually(lambda: call('user', 'GET', '/api/v1/users/me'), lambda x: x['premium'] is True, 'Premium activated through RabbitMQ')
    call('user', 'PATCH', '/api/v1/users/me', {'action': 'cancel_subscription'})
    assert call('payment', 'GET', '/api/v1/subscriptions/me')['auto_renew'] is False
    assert call('user', 'GET', '/api/v1/users/me')['premium'] is True
    notifications = eventually(lambda: call('notification', 'GET', '/api/v1/notifications')['items'], lambda xs: any(n['source'] == 'payment.subscription.activated' for n in xs), 'payment notification')
    n = call('notification', 'POST', '/api/v1/notifications', {'title': 'Пора заниматься', 'text': 'Учебное напоминание'}, expected=201)
    npath = '/api/v1/notifications/' + n['id'] + '/commands'
    call('notification', 'POST', npath, {'action': 'schedule', 'scheduled_at': (datetime.now(timezone.utc) + timedelta(seconds=2)).isoformat()})
    eventually(lambda: call('notification', 'GET', '/api/v1/notifications')['items'], lambda xs: any(x['id'] == n['id'] and x['status'] == 'sent' for x in xs), 'scheduled push')
    call('notification', 'POST', npath, {'action': 'read'})
    call('notification', 'POST', npath, {'action': 'delete'})
    call('notification', 'POST', npath, {'action': 'read'}, expected=404)
    # An unrelated user cannot read session/payment resources.
    other = dict(email='other-' + uuid.uuid4().hex[:12] + '@pr7.local', password='Other-pr7-2026!')
    call('user', 'POST', '/api/v1/users', dict(**other, display_name='Другой пользователь'), expected=201)
    other_token = call('user', 'POST', '/api/v1/sessions', other, expected=201)['access_token']
    call('grammar', 'GET', '/api/v1/sessions/' + session_ids['grammar'], expected=404, headers={'Authorization': 'Bearer ' + other_token})
    call('payment', 'GET', '/api/v1/payments/' + payment['id'], expected=404, headers={'Authorization': 'Bearer ' + other_token})
    return dict(user_id=user['id'], email=email, session_ids=session_ids, payment_id=payment['id'], completed_sessions=progress['completed_sessions'], learned_words=progress['learned_words'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--output', default='.work/smoke-results.json'); args = parser.parse_args()
    evidence = run()
    report = dict(passed=True, checked_at=datetime.now(timezone.utc).isoformat(), checks=len(checks), evidence=evidence, requests=checks)
    path = Path(args.output); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'PASS: {len(checks)} HTTP checks across 8 services; RabbitMQ, ownership, grading, subscription and scheduled push verified.')
