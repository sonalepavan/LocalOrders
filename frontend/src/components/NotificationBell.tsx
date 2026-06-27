import { useFocusEffect, useRouter } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import { AppState, StyleSheet, View } from "react-native";
import { Badge, IconButton, useTheme } from "react-native-paper";

import { api } from "@/src/lib/api";
import { useNetwork } from "@/src/lib/network";

/**
 * Bell icon with an unread badge. Polls the unread-count endpoint on mount,
 * whenever the host screen regains focus (e.g. after returning from
 * /notifications where items may have been marked read), and when the app
 * returns to foreground. Tapping navigates to /notifications.
 */
export function NotificationBell({ testID = "notifications-bell" }: { testID?: string }) {
  const router = useRouter();
  const theme = useTheme();
  const { online } = useNetwork();
  const [count, setCount] = useState(0);

  const refresh = useCallback(async () => {
    if (!online) return;
    try {
      const { unreadCount } = await api.unreadCount();
      setCount(unreadCount);
    } catch {
      // ignore — offline / unauth
    }
  }, [online]);

  // Refresh every time the host screen regains focus. This is what fixes the
  // stale badge after the user reads notifications on the /notifications
  // screen and navigates back.
  useFocusEffect(
    useCallback(() => {
      refresh();
    }, [refresh]),
  );

  useEffect(() => {
    const sub = AppState.addEventListener("change", (state) => {
      if (state === "active") refresh();
    });
    const interval = setInterval(refresh, 30_000);
    return () => {
      sub.remove();
      clearInterval(interval);
    };
  }, [refresh]);

  return (
    <View style={styles.wrap}>
      <IconButton
        icon="bell-outline"
        size={24}
        onPress={() => router.push("/notifications" as any)}
        iconColor={theme.colors.onSurface}
        accessibilityLabel="Notifications"
        testID={testID}
      />
      {count > 0 && (
        <Badge
          size={18}
          testID="notifications-badge"
          style={[styles.badge, { backgroundColor: theme.colors.error }]}
        >
          {count > 99 ? "99+" : count}
        </Badge>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { position: "relative" },
  badge: {
    position: "absolute",
    top: 4,
    right: 4,
    color: "#FFFFFF",
  },
});
