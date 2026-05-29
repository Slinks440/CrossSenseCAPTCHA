import os
import redis

# Redis config from environment
REDIS_HOST = os.environ.get("REDIS_HOST", "127.0.0.1")
REDIS_PORT = int(os.environ.get("REDIS_PORT", 6379))
REDIS_PASSWORD = os.environ.get("REDIS_PASSWORD", None)

# V14: High-Concurrency Blocking Connection Pool
pool = redis.BlockingConnectionPool(
    host=REDIS_HOST,
    port=REDIS_PORT,
    password=REDIS_PASSWORD,
    decode_responses=True, # We will store dicts as JSON strings
    max_connections=1000,
    timeout=20
)
redis_conn = redis.Redis(connection_pool=pool)

# Secure Lua script for releasing locks
RELEASE_LUA_SCRIPT = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""
release_script = redis_conn.register_script(RELEASE_LUA_SCRIPT)

# Atomic GETDEL Lua script for Crypto Annihilation
GETDEL_LUA_SCRIPT = """
local val = redis.call('get', KEYS[1])
if val then
    redis.call('del', KEYS[1])
end
return val
"""
getdel_script = redis_conn.register_script(GETDEL_LUA_SCRIPT)

# Rate Limit Token Bucket Lua script
TOKEN_BUCKET_LUA = """
local key = KEYS[1]
local max_tokens = tonumber(ARGV[1])
local refill_rate = tonumber(ARGV[2])
local now = tonumber(ARGV[3])

local bucket = redis.call('HMGET', key, 'tokens', 'last_refill')
local tokens = tonumber(bucket[1])
local last_refill = tonumber(bucket[2])

if not tokens then
    tokens = max_tokens
    last_refill = now
else
    local delta = math.max(0, now - last_refill)
    local new_tokens = math.floor(delta * refill_rate)
    if new_tokens > 0 then
        tokens = math.min(max_tokens, tokens + new_tokens)
        last_refill = now
    end
end

if tokens >= 1 then
    tokens = tokens - 1
    redis.call('HMSET', key, 'tokens', tokens, 'last_refill', last_refill)
    redis.call('EXPIRE', key, math.ceil(max_tokens / refill_rate) * 2)
    return 1
else
    redis.call('HMSET', key, 'tokens', tokens, 'last_refill', last_refill)
    return 0
end
"""
token_bucket_script = redis_conn.register_script(TOKEN_BUCKET_LUA)

class RedisLock:
    """Distributed lock implementation using Redis SET NX EX and Lua release"""
    def __init__(self, key, value, timeout=5):
        self.key = key
        self.value = value
        self.timeout = timeout

    def acquire(self):
        return redis_conn.set(self.key, self.value, nx=True, ex=self.timeout)

    def release(self):
        release_script(keys=[self.key], args=[self.value])
