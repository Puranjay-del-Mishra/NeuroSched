import redis.asyncio as redis
import json
import os

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
RUN_KEY = "sim:latest"

# TTL for a run: 6 hours
RUN_TTL = 6 * 60 * 60  

class RedisStore:
    def __init__(self):
        self.redis = None

    async def connect(self):
        """Initialize Redis connection."""
        if self.redis is None:
            self.redis = await redis.from_url(REDIS_URL, decode_responses=True)

    async def save_update(self, update: dict):
        """Save a single update (plot point)."""
        await self.connect()
        key = f"{RUN_KEY}:updates"
        await self.redis.rpush(key, json.dumps(update))
        await self.redis.expire(key, RUN_TTL)

    async def load_updates(self):
        """Load all updates for the latest run."""
        await self.connect()
        key = f"{RUN_KEY}:updates"
        updates = await self.redis.lrange(key, 0, -1)
        return [json.loads(u) for u in updates]

    async def save_results(self, results: dict):
        """Save the final simulation results."""
        await self.connect()
        key = f"{RUN_KEY}:results"
        await self.redis.set(key, json.dumps(results), ex=RUN_TTL)

    async def load_results(self):
        """Load final simulation results."""
        await self.connect()
        key = f"{RUN_KEY}:results"
        data = await self.redis.get(key)
        return json.loads(data) if data else None

    async def clear_run(self):
        """Clear both updates and results."""
        await self.connect()
        await self.redis.delete(f"{RUN_KEY}:updates", f"{RUN_KEY}:results")
