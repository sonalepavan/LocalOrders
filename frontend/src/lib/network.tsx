import NetInfo, { type NetInfoState } from "@react-native-community/netinfo";
import React, { createContext, useContext, useEffect, useMemo, useState } from "react";

type NetState = {
  online: boolean;
  type: string | null;
};

const NetCtx = createContext<NetState>({ online: true, type: null });

export function NetworkProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<NetState>({ online: true, type: null });

  useEffect(() => {
    const handler = (s: NetInfoState) => {
      // Consider offline only when explicitly disconnected; treat unknown as online.
      const online = s.isConnected !== false && s.isInternetReachable !== false;
      setState({ online, type: s.type || null });
    };
    NetInfo.fetch().then(handler);
    const unsub = NetInfo.addEventListener(handler);
    return () => {
      unsub();
    };
  }, []);

  const value = useMemo(() => state, [state]);
  return <NetCtx.Provider value={value}>{children}</NetCtx.Provider>;
}

export function useNetwork(): NetState {
  return useContext(NetCtx);
}
