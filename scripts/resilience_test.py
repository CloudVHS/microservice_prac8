"""Optional integration test: restarts this Compose project and stops its broker briefly."""
import json
from pathlib import Path
import subprocess
import time
import smoke_test as smoke


def docker(*args):
    subprocess.run(['docker', 'compose', *args], check=True, stdout=subprocess.DEVNULL)


def run():
    original = json.loads(Path('.work/smoke-results.json').read_text(encoding='utf-8'))['evidence']
    docker('restart')
    deadline = time.monotonic() + 90
    while True:
        try:
            for service in smoke.SERVICES:
                smoke.call(service, 'GET', '/health', auth=False)
            break
        except Exception:
            if time.monotonic() >= deadline:
                raise
            time.sleep(1)
    smoke.token = smoke.call('user', 'POST', '/api/v1/sessions', dict(email=original['email'], password='Student-pr7-2026!'), expected=201)['access_token']
    profile = smoke.call('user', 'GET', '/api/v1/users/me')
    assert profile['premium'] is True
    target_level = 3 if profile['hsk_level'] != 3 else 2
    for service, id in original['session_ids'].items():
        assert smoke.call(service, 'GET', '/api/v1/sessions/' + id)['status'] == 'completed'
    assert smoke.call('payment', 'GET', '/api/v1/payments/' + original['payment_id'])['status'] == 'confirmed'
    assert smoke.call('lexicon', 'GET', '/api/v1/tasks')['progress']['completed_sessions'] == 3
    docker('stop', 'rabbitmq')
    try:
        smoke.call('user', 'PATCH', '/api/v1/users/me', {'hsk_level': target_level})
        health = smoke.call('user', 'GET', '/health', expected=503, auth=False)
        assert health['pending_events'] > 0
    finally:
        docker('up', '-d', '--no-deps', '--wait', '--wait-timeout', '90', 'rabbitmq')
    smoke.eventually(lambda: smoke.call('user', 'GET', '/health', auth=False), lambda x: x['pending_events'] == 0, 'outbox drained')
    value = smoke.eventually(lambda: smoke.call('lexicon', 'GET', '/api/v1/tasks')['progress'], lambda x: x['hsk_level'] == target_level, 'queued profile event delivered')
    assert value['completed_sessions'] == 3 and value['learned_words'] == 1
    Path('.work/resilience-results.json').write_text(json.dumps(dict(passed=True, restart_preserved_data=True, broker_outage_recovered=True, pending_event_delivered=True, requests=smoke.checks), ensure_ascii=False, indent=2), encoding='utf-8')
    print('PASS: data persisted across restart; outbox delivered queued event after RabbitMQ outage; counters unchanged.')


if __name__ == '__main__':
    run()
