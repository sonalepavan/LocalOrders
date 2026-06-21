import { Stack, useRouter } from "expo-router";
import * as Linking from "expo-linking";
import * as Notifications from "expo-notifications";
import * as SplashScreen from "expo-splash-screen";
import { useEffect } from "react";
import { LogBox, Platform } from "react-native";
import { Provider as PaperProvider } from "react-native-paper";
import { SafeAreaProvider } from "react-native-safe-area-context";

import { OfflineBanner } from "@/src/components/OfflineBanner";
import { useIconFonts } from "@/src/hooks/use-icon-fonts";
import { AuthProvider } from "@/src/lib/auth-context";
import { NetworkProvider } from "@/src/lib/network";
import { ThemePrefProvider, useThemePref } from "@/src/lib/theme-context";

LogBox.ignoreAllLogs(true);
SplashScreen.preventAutoHideAsync();

// --- Module-scope push setup (per Emergent push playbook) ---
if (Platform.OS !== "web") {
  Notifications.setNotificationHandler({
    handleNotification: async () => ({
      shouldShowAlert: true,
      shouldShowBanner: true,
      shouldShowList: true,
      shouldPlaySound: true,
      shouldSetBadge: true,
    }),
  });
}

if (Platform.OS === "android") {
  Notifications.setNotificationChannelAsync("default", {
    name: "Default",
    importance: Notifications.AndroidImportance.MAX,
    sound: "default",
  });
}

function ThemedStack() {
  const { theme } = useThemePref();
  return (
    <PaperProvider theme={theme}>
      <AuthProvider>
        <OfflineBanner />
        <Stack
          screenOptions={{
            headerShown: false,
            contentStyle: { backgroundColor: theme.colors.background },
          }}
        />
      </AuthProvider>
    </PaperProvider>
  );
}

export default function RootLayout() {
  const [loaded, error] = useIconFonts();
  const router = useRouter();

  useEffect(() => {
    if (loaded || error) SplashScreen.hideAsync();
  }, [loaded, error]);

  useEffect(() => {
    if (Platform.OS === "web") return;
    // Warm tap — app already in foreground/background
    const tapSub = Notifications.addNotificationResponseReceivedListener((response) => {
      const data = (response.notification.request.content.data || {}) as Record<string, any>;
      const url = data.deeplink || data.action_url;
      if (!url) return;
      if (typeof url === "string" && url.startsWith("http")) {
        Linking.openURL(url);
      } else {
        router.push(url as any);
      }
    });
    // Cold-start tap — app was killed
    Notifications.getLastNotificationResponseAsync().then((response) => {
      if (!response) return;
      const data = (response.notification.request.content.data || {}) as Record<string, any>;
      const url = data.deeplink || data.action_url;
      if (!url) return;
      if (typeof url === "string" && url.startsWith("http")) {
        Linking.openURL(url);
      } else {
        router.push(url as any);
      }
    });
    return () => {
      tapSub.remove();
    };
  }, [router]);

  if (!loaded && !error) return null;

  return (
    <SafeAreaProvider>
      <ThemePrefProvider>
        <NetworkProvider>
          <ThemedStack />
        </NetworkProvider>
      </ThemePrefProvider>
    </SafeAreaProvider>
  );
}
