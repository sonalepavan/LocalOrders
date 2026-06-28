import { storage } from "@/src/utils/storage";

/**
 * Lightweight per-user offline cache for read-only lists.
 * Persists JSON-encoded strings to local storage keyed by `<scope>:<userId>`.
 * Never throws — read failures return `fallback`.
 */

const PREFIX = "lo.cache.";

function key(scope: string, userId: string) {
  return `${PREFIX}${scope}:${userId}`;
}

export const offlineCache = {
  async save<T>(scope: string, userId: string, value: T): Promise<void> {
    if (!userId) return;
    try {
      await storage.setItem(key(scope, userId), JSON.stringify(value));
    } catch {
      // best-effort
    }
  },
  async load<T>(scope: string, userId: string, fallback: T): Promise<T> {
    if (!userId) return fallback;
    try {
      const raw = await storage.getItem<string>(key(scope, userId), "");
      if (!raw) return fallback;
      return JSON.parse(raw) as T;
    } catch {
      return fallback;
    }
  },
  async clear(scope: string, userId: string): Promise<void> {
    if (!userId) return;
    try {
      await storage.removeItem(key(scope, userId));
    } catch {
      // best-effort
    }
  },
};

export const CACHE_SCOPES = {
  buyerOrders: "buyerOrders",
  sellerOrders: "sellerOrders",
  sellerInventory: "sellerInventory",
  notifications: "notifications",
} as const;
