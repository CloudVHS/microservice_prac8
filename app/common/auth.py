import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from fastapi import Header
from app.common.config import settings
from app.common.domain import require, uuid_value


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 210000).hex()
    return salt + ':' + digest


def check_password(password: str, encoded: str) -> bool:
    salt, digest = encoded.split(':')
    actual = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 210000).hex()
    return hmac.compare_digest(actual, digest)


def sign_token(user: dict) -> str:
    raw = json.dumps(dict(sub=user['id'], role=user['role'], exp=int(time.time()) + settings().token_ttl_seconds), separators=(',', ':')).encode()
    payload = base64.urlsafe_b64encode(raw).decode().rstrip('=')
    signature = hmac.new(settings().auth_secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return payload + '.' + signature


@dataclass
class Actor:
    id: str
    role: str
    internal: bool = False


def actor(authorization: str = Header(default=''), x_service_token: str = Header(default=''), x_user_id: str = Header(default='')) -> Actor:
    if x_service_token:
        require(hmac.compare_digest(x_service_token, settings().internal_token), 401, 'Неверный служебный токен')
        return Actor(uuid_value(x_user_id) if x_user_id else '', 'service', True)
    require(authorization.startswith('Bearer '), 401, 'Требуется Bearer-токен')
    try:
        payload, signature = authorization[7:].split('.')
        expected = hmac.new(settings().auth_secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
        require(hmac.compare_digest(signature, expected), 401, 'Неверная подпись токена')
        data = json.loads(base64.urlsafe_b64decode(payload + '=' * (-len(payload) % 4)))
        require(data['exp'] > time.time(), 401, 'Токен истек')
        require(data['role'] in ['user', 'admin'], 401, 'Неверная роль')
        return Actor(uuid_value(data['sub']), data['role'])
    except (ValueError, KeyError, TypeError, UnicodeDecodeError):
        from app.common.domain import DomainError
        raise DomainError(401, 'Некорректный токен')


def owner(value: dict, who: Actor):
    require(value['user_id'] == who.id, 404, 'Объект не найден')


def internal(who: Actor):
    require(who.internal, 403, 'Требуется служебный доступ')
