import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { useColorScheme } from "react-native";

import { storage } from "@/src/utils/storage";
import { darkTheme, lightTheme, type ThemePreference } from "./theme";

const STORAGE_KEY = "lo.themePreference";

type ThemeState = {
  preference: ThemePreference;
  theme: typeof lightTheme;
  isDark: boolean;
  setPreference: (next: ThemePreference) => Promise<void>;
};

const ThemeCtx = createContext<ThemeState | undefined>(undefined);

export function ThemePrefProvider({ children }: { children: React.ReactNode }) {
  const systemScheme = useColorScheme();
  const [preference, setPreferenceState] = useState<ThemePreference>("system");
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    (async () => {
      const saved = await storage.getItem<string>(STORAGE_KEY, "system");
      if (saved === "light" || saved === "dark" || saved === "system") {
        setPreferenceState(saved as ThemePreference);
      }
      setHydrated(true);
    })();
  }, []);

  const setPreference = useCallback(async (next: ThemePreference) => {
    setPreferenceState(next);
    await storage.setItem(STORAGE_KEY, next);
  }, []);

  const isDark = preference === "dark" || (preference === "system" && systemScheme === "dark");
  const theme = isDark ? darkTheme : lightTheme;

  const value = useMemo(
    () => ({ preference, theme, isDark, setPreference }),
    [preference, theme, isDark, setPreference],
  );

  if (!hydrated) return null;
  return <ThemeCtx.Provider value={value}>{children}</ThemeCtx.Provider>;
}

export function useThemePref(): ThemeState {
  const ctx = useContext(ThemeCtx);
  if (!ctx) throw new Error("useThemePref must be used inside ThemePrefProvider");
  return ctx;
}
