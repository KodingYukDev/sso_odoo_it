const GRANTABLE = new Set([
  'AccessToken', 'AuthorizationCode', 'RefreshToken', 'DeviceCode',
  'BackchannelAuthenticationRequest',
]);

export function createRedisAdapter(redis, prefix = 'ky:oidc:') {
  return class RedisAdapter {
    constructor(model) { this.model = model; }
    key(id) { return `${prefix}${this.model}:${id}`; }
    index(type, value) { return `${prefix}index:${type}:${value}`; }

    async upsert(id, payload, expiresIn) {
      const key = this.key(id);
      const transaction = redis.multi().set(key, JSON.stringify(payload), 'EX', expiresIn);
      if (this.model === 'Session' && payload.uid) {
        transaction.set(this.index('sessionUid', payload.uid), id, 'EX', expiresIn);
      }
      if (payload.userCode) {
        transaction.set(this.index('userCode', payload.userCode), id, 'EX', expiresIn);
      }
      if (GRANTABLE.has(this.model) && payload.grantId) {
        const grantKey = this.index('grant', payload.grantId);
        transaction.sadd(grantKey, key).expire(grantKey, expiresIn);
      }
      await transaction.exec();
    }

    async find(id) {
      const value = await redis.get(this.key(id));
      return value ? JSON.parse(value) : undefined;
    }

    async findByUid(uid) {
      const id = await redis.get(this.index('sessionUid', uid));
      return id ? this.find(id) : undefined;
    }

    async findByUserCode(userCode) {
      const id = await redis.get(this.index('userCode', userCode));
      return id ? this.find(id) : undefined;
    }

    async destroy(id) { await redis.del(this.key(id)); }

    async consume(id) {
      const key = this.key(id);
      const [value, ttl] = await Promise.all([redis.get(key), redis.ttl(key)]);
      if (!value) return;
      const payload = JSON.parse(value);
      payload.consumed = Math.floor(Date.now() / 1000);
      if (ttl > 0) await redis.set(key, JSON.stringify(payload), 'EX', ttl);
    }

    async revokeByGrantId(grantId) {
      const grantKey = this.index('grant', grantId);
      const keys = await redis.smembers(grantKey);
      if (keys.length) await redis.del(...keys);
      await redis.del(grantKey);
    }
  };
}
