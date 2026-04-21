import redis
import json
import os
from src.config import REDIS_HOST, REDIS_PORT, REDIS_DB

# Default connection settings if not in config
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB = int(os.getenv("REDIS_DB", 0))

def get_redis_connection():
    return redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)

def get_async_redis_connection():
    import redis.asyncio as async_redis
    return async_redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)

def publish_event(channel: str, event_type: str, payload: dict):
    """
    Publishes an event to a Redis channel.
    """
    r = get_redis_connection()
    message = json.dumps({
        "type": event_type,
        "payload": payload
    })
    r.publish(channel, message)

async def subscribe_to_channel(channel: str):
    """
    Async generator that yields messages from a Redis channel.
    """
    r = get_redis_connection()
    pubsub = r.pubsub()
    pubsub.subscribe(channel)
    
    for message in pubsub.listen():
        if message['type'] == 'message':
            yield json.loads(message['data'])
