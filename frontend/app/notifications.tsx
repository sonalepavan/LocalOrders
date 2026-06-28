import { MaterialCommunityIcons } from "@expo/vector-icons";
import { formatDistanceToNow } from "date-fns";
import { router, useFocusEffect } from "expo-router";
import { useCallback, useState } from "react";
import { FlatList, RefreshControl, StyleSheet, View } from "react-native";
import { ActivityIndicator, Appbar, Button, Card, Snackbar, Text, useTheme } from "react-native-paper";
import { SafeAreaView } from "react-native-safe-area-context";

import { api, type AppNotification } from "@/src/lib/api";
import { useAuth } from "@/src/lib/auth-context";
import { useNetwork } from "@/src/lib/network";
import { CACHE_SCOPES, offlineCache } from "@/src/lib/offline-cache";

const ICON_MAP: Record<string, string> = {
  order_requested: "package-variant",
  order_accepted: "check-circle-outline",
  order_rejected: "close-circle-outline",
  order_cancelled: "alert-circle-outline",
  order_delivered: "truck-check-outline",
  order_expired: "clock-alert-outline",
  connection_request: "account-plus-outline",
  connection_accepted: "account-check-outline",
  connection_rejected: "account-cancel-outline",
  custom_request_received: "message-text-outline",
  custom_quote_received: "cash-multiple",
  custom_request_accepted_by_buyer: "check-circle-outline",
  custom_request_rejected_by_buyer: "close-circle-outline",
  custom_request_accepted_by_seller: "check-circle-outline",
  custom_request_rejected_by_seller: "close-circle-outline",
  custom_request_completed: "check-decagram",
};

export default function NotificationsScreen() {
  const theme = useTheme();
  const { user } = useAuth();
  const { online } = useNetwork();
  const [items, setItems] = useState<AppNotification[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [snack, setSnack] = useState("");
  const [fromCache, setFromCache] = useState(false);

  const load = useCallback(async () => {
    if (!user) return;
    if (!online) {
      const cached = await offlineCache.load<AppNotification[]>(
        CACHE_SCOPES.notifications,
        user.userId,
        [],
      );
      setItems(cached);
      setFromCache(true);
      setLoading(false);
      return;
    }
    try {
      const { notifications } = await api.listNotifications(100);
      setItems(notifications);
      setFromCache(false);
      await offlineCache.save(CACHE_SCOPES.notifications, user.userId, notifications);
    } catch (e: any) {
      // Fallback to cache on error
      const cached = await offlineCache.load<AppNotification[]>(
        CACHE_SCOPES.notifications,
        user.userId,
        [],
      );
      setItems(cached);
      setFromCache(true);
      setSnack(e?.message || "Failed to load notifications");
    } finally {
      setLoading(false);
    }
  }, [user, online]);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const onRefresh = useCallback(async () => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  }, [load]);

  const onTap = async (n: AppNotification) => {
    if (online && !n.readAt) {
      try { await api.markRead(n.notificationId); } catch { /* ignore */ }
    }
    // Reflect optimistically
    setItems((prev) => prev.map((x) => x.notificationId === n.notificationId ? { ...x, readAt: x.readAt || new Date().toISOString() } : x));
    const orderId = n.data?.orderId;
    const customRequestId = n.data?.customRequestId;
    if (customRequestId) {
      const pathname = user?.userType === "seller"
        ? "/seller-custom-request-detail"
        : "/buyer-custom-request-detail";
      router.push({ pathname, params: { requestId: customRequestId } } as any);
      return;
    }
    if (orderId) {
      router.push({ pathname: "/buyer-order-detail", params: { orderId } } as any);
    }
  };

  const onMarkAllRead = async () => {
    if (!online) {
      setSnack("Connect to internet to mark all as read");
      return;
    }
    try {
      await api.markAllRead();
      setItems((prev) => prev.map((x) => ({ ...x, readAt: x.readAt || new Date().toISOString() })));
      setSnack("All notifications marked as read");
    } catch (e: any) {
      setSnack(e?.message || "Failed");
    }
  };

  const unreadCount = items.filter((n) => !n.readAt).length;

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: theme.colors.background }} edges={["top"]}>
      <Appbar.Header mode="small" elevated>
        <Appbar.BackAction onPress={() => router.back()} testID="notif-back-btn" />
        <Appbar.Content title="Notifications" />
        {unreadCount > 0 && (
          <Appbar.Action
            icon="email-open-multiple-outline"
            onPress={onMarkAllRead}
            disabled={!online}
            testID="mark-all-read-btn"
          />
        )}
      </Appbar.Header>

      {loading ? (
        <View style={styles.center}>
          <ActivityIndicator />
        </View>
      ) : items.length === 0 ? (
        <View style={styles.empty}>
          <MaterialCommunityIcons name="bell-off-outline" size={56} color={theme.colors.onSurfaceVariant} />
          <Text variant="titleMedium" style={{ marginTop: 12, color: theme.colors.onSurface }}>
            No notifications yet
          </Text>
          <Text
            variant="bodyMedium"
            style={{ marginTop: 4, color: theme.colors.onSurfaceVariant, textAlign: "center", paddingHorizontal: 24 }}
          >
            You'll be notified about order updates and new connection requests here.
          </Text>
          <Button mode="text" onPress={onRefresh} style={{ marginTop: 12 }}>
            Refresh
          </Button>
        </View>
      ) : (
        <FlatList
          data={items}
          keyExtractor={(n) => n.notificationId}
          contentContainerStyle={{ padding: 16, paddingBottom: 32 }}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
          ItemSeparatorComponent={() => <View style={{ height: 10 }} />}
          ListHeaderComponent={
            fromCache ? (
              <View style={[styles.cacheNote, { backgroundColor: theme.colors.surfaceVariant }]}>
                <MaterialCommunityIcons name="database-clock-outline" size={16} color={theme.colors.onSurfaceVariant} />
                <Text variant="labelMedium" style={{ marginLeft: 6, color: theme.colors.onSurfaceVariant }}>
                  Showing offline-saved notifications
                </Text>
              </View>
            ) : null
          }
          renderItem={({ item }) => {
            const icon = ICON_MAP[item.type] || "bell-outline";
            const unread = !item.readAt;
            return (
              <Card
                onPress={() => onTap(item)}
                mode={unread ? "elevated" : "outlined"}
                style={[
                  styles.card,
                  unread && { backgroundColor: theme.colors.primaryContainer },
                ]}
                testID={`notification-${item.notificationId}`}
              >
                <Card.Content style={styles.cardContent}>
                  <View style={[styles.iconWrap, { backgroundColor: theme.colors.surface }]}>
                    <MaterialCommunityIcons
                      name={icon as any}
                      size={22}
                      color={unread ? theme.colors.primary : theme.colors.onSurfaceVariant}
                    />
                  </View>
                  <View style={{ flex: 1 }}>
                    <View style={styles.titleRow}>
                      <Text
                        variant="titleSmall"
                        numberOfLines={1}
                        style={{ flex: 1, fontWeight: unread ? "700" : "500", color: unread ? theme.colors.onPrimaryContainer : theme.colors.onSurface }}
                      >
                        {item.title}
                      </Text>
                      {unread && <View style={[styles.dot, { backgroundColor: theme.colors.primary }]} />}
                    </View>
                    <Text
                      variant="bodySmall"
                      style={{ marginTop: 2, color: unread ? theme.colors.onPrimaryContainer : theme.colors.onSurfaceVariant }}
                      numberOfLines={3}
                    >
                      {item.body}
                    </Text>
                    <Text
                      variant="labelSmall"
                      style={{ marginTop: 6, color: theme.colors.onSurfaceVariant }}
                    >
                      {timeAgo(item.createdDate)}
                    </Text>
                  </View>
                </Card.Content>
              </Card>
            );
          }}
        />
      )}
      <Snackbar visible={!!snack} onDismiss={() => setSnack("")} duration={2500}>{snack}</Snackbar>
    </SafeAreaView>
  );
}

function timeAgo(iso: string): string {
  try {
    return formatDistanceToNow(new Date(iso), { addSuffix: true });
  } catch {
    return iso;
  }
}

const styles = StyleSheet.create({
  center: { flex: 1, alignItems: "center", justifyContent: "center" },
  empty: { flex: 1, alignItems: "center", justifyContent: "center", padding: 24 },
  card: { borderRadius: 16 },
  cardContent: { flexDirection: "row", alignItems: "flex-start", gap: 12 },
  iconWrap: {
    width: 40,
    height: 40,
    borderRadius: 20,
    alignItems: "center",
    justifyContent: "center",
  },
  titleRow: { flexDirection: "row", alignItems: "center" },
  dot: { width: 8, height: 8, borderRadius: 4, marginLeft: 8 },
  cacheNote: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 10,
    marginBottom: 12,
  },
});
