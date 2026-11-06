"""Durable topic exchange, transactional outbox and idempotent inbox."""
import asyncio
import json
import logging
from contextlib import suppress
import aio_pika
from sqlalchemy import select
from app.common.config import settings
from app.common.storage import Sessions, Repository, Inbox, Outbox

log = logging.getLogger(__name__)
SUBSCRIPTIONS = {
    'user': ['payment.subscription.*'],
    'lexicon': ['user.profile.changed', 'learning.#'],
    'notification': ['user.profile.changed', 'payment.#', 'learning.session.completed'],
    'dictionary': ['learning.word.learned'],
}


class Bus:
    connection = None

    def __init__(self, handler, tick):
        self.handler, self.tick = handler, tick
        self.tasks = []

    async def start(self):
        if settings().amqp_url:
            self.connection = await aio_pika.connect_robust(settings().amqp_url, timeout=20)
            self.channel = await self.connection.channel(publisher_confirms=True)
            await self.channel.set_qos(prefetch_count=1)
            self.exchange = await self.channel.declare_exchange('pr7.domain', aio_pika.ExchangeType.TOPIC, durable=True)
            dead = await self.channel.declare_exchange('pr7.dead', aio_pika.ExchangeType.FANOUT, durable=True)
            dead_q = await self.channel.declare_queue('pr7.dead.messages', durable=True)
            await dead_q.bind(dead)
            # Declare the whole topology before any producer sends the first event.
            for name, keys in SUBSCRIPTIONS.items():
                queue = await self.channel.declare_queue('pr7.' + name, durable=True, arguments={'x-dead-letter-exchange': 'pr7.dead'})
                for key in keys:
                    await queue.bind(self.exchange, key)
                if name == settings().service_name:
                    await queue.consume(self.consume)
            self.tasks.append(asyncio.create_task(self.publish_loop()))
        self.tasks.append(asyncio.create_task(self.tick_loop()))

    async def stop(self):
        for task in self.tasks:
            task.cancel()
        for task in self.tasks:
            with suppress(asyncio.CancelledError):
                await task
        if self.connection:
            await self.connection.close()

    async def consume(self, message):
        async with message.process(requeue=False):
            body = json.loads(message.body)
            with Sessions.begin() as session:
                if session.get(Inbox, body['event_id']):
                    return
                self.handler(Repository(session), body)
                session.add(Inbox(event_id=body['event_id']))

    async def publish_loop(self):
        while True:
            try:
                with Sessions() as session:
                    pending = session.scalars(select(Outbox).where(Outbox.sent.is_(False)).order_by(Outbox.sequence).limit(30)).all()
                    for row in pending:
                        await self.exchange.publish(aio_pika.Message(json.dumps(row.payload, ensure_ascii=False).encode(), content_type='application/json', message_id=row.event_id, delivery_mode=aio_pika.DeliveryMode.PERSISTENT), routing_key=row.routing_key)
                        row.sent = True
                        session.commit()
            except Exception:
                log.exception('Outbox publish failed; retrying')
            await asyncio.sleep(0.3)

    async def tick_loop(self):
        while True:
            try:
                with Sessions.begin() as session:
                    self.tick(Repository(session))
            except Exception:
                log.exception('Scheduled task failed; retrying')
            await asyncio.sleep(1)
