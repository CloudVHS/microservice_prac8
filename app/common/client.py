import httpx
from app.common.config import settings
from app.common.domain import DomainError


async def request(service: str, method: str, path: str, user_id: str, body: dict | None = None):
    base = getattr(settings(), service + '_url')
    headers = {'X-Service-Token': settings().internal_token, 'X-User-Id': user_id}
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.request(method, base + path, headers=headers, json=body)
    except httpx.RequestError:
        raise DomainError(503, f'Сервис {service} недоступен')
    if response.status_code >= 500:
        raise DomainError(503, f'Сервис {service} недоступен')
    if response.is_error:
        raise DomainError(response.status_code, f'{service}: {response.json().get("detail", "ошибка запроса")}')
    return response.json()
