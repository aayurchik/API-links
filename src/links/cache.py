import json
from src.core.redis import redis_client

async def get_cached_url(short_code: str) -> str | None:
    print(f"get_cached_url({short_code})")
    try:
        data = await redis_client.get(f"link:{short_code}")
        print(f"data from redis: {data}")
        if data:
            parsed = json.loads(data)
            print(f"   parsed JSON: {parsed}")
            result = parsed.get("original_url")
            print(f"   result: {result}")
            return result
        else:
            print("no data in redis")
            return None
    except Exception as e:
        print(f"ERROR in get_cached_url: {e}")
        return None

async def set_cached_url(short_code: str, original_url: str, ttl: int = 3600):
    print(f"set_cached_url({short_code}, {original_url})")
    try:
        value = json.dumps({"original_url": original_url})
        print(f"value to set: {value}")
        await redis_client.setex(
            f"link:{short_code}",
            ttl,
            value)
        print("set successful")
    except Exception as e:
        print(f"ERROR in set_cached_url: {e}")

async def delete_cached_url(short_code: str):
    print(f"delete_cached_url({short_code})")
    try:
        await redis_client.delete(f"link:{short_code}")
        print("delete successful")
    except Exception as e:
        print(f"ERROR in delete_cached_url: {e}")