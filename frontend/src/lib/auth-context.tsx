import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { storage } from "@/src/utils/storage";
import { AppUser, TOKEN_KEY, api } from "./api";
import { registerForPush } from "./push";

type AuthState = {
  user: AppUser | null;
  loading: boolean;
  setSession: (token: string, user: AppUser) => Promise<void>;
  signOut: () => Promise<void>;
  refresh: () => Promise<void>;
};

const AuthContext = createContext<AuthState | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AppUser | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    const token = await storage.secureGet<string>(TOKEN_KEY, "");
    if (!token) {
      setUser(null);
      return;
    }
    try {
      const { user: fetched } = await api.me();
      setUser(fetched);
      // Best-effort push registration (non-blocking, ignored on web)
      registerForPush().catch(() => {});
    } catch {
      await storage.secureRemove(TOKEN_KEY);
      setUser(null);
    }
  }, []);

  useEffect(() => {
    (async () => {
      await refresh();
      setLoading(false);
    })();
  }, [refresh]);

  const setSession = useCallback(async (token: string, u: AppUser) => {
    await storage.secureSet(TOKEN_KEY, token);
    setUser(u);
    registerForPush().catch(() => {});
  }, []);

  const signOut = useCallback(async () => {
    await storage.secureRemove(TOKEN_KEY);
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({ user, loading, setSession, signOut, refresh }),
    [user, loading, setSession, signOut, refresh],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
