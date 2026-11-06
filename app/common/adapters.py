import base64
import io
import math
import struct
import wave
import unicodedata
from app.common.domain import now


def normalize(text: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFKC', text).casefold() if not c.isspace() and c not in '.,!?。！？，、')


def grade(tasks: list, answers: dict) -> dict:
    results = []
    for task in tasks:
        answer = answers[task['id']]
        correct = normalize(answer) in [normalize(x) for x in task['accepted_answers']]
        results.append(dict(task_id=task['id'], answer=answer, correct=correct, expected=task['accepted_answers'][0]))
    score = round(100 * sum(r['correct'] for r in results) / len(results))
    return dict(adapter='local-reference-checker', score=score, passed=score >= 70, results=results)


def audio_preview(text: str) -> dict:
    """A short tone, deliberately not represented as Chinese speech."""
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as wav:
        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(8000)
        wav.writeframes(b''.join(struct.pack('<h', int(5000 * math.sin(2 * math.pi * 440 * n / 8000))) for n in range(1600)))
    return dict(adapter='local-demo-tone', text=text, speech=False, media_type='audio/wav', audio_base64=base64.b64encode(buffer.getvalue()).decode())


def push(notification: dict) -> dict:
    return dict(adapter='local-push-log', delivered_at=now(), notification_id=notification['id'])
