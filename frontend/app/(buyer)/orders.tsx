import { router, useFocusEffect } from "expo-router";
import { useCallback, useState } from "react";
import { FlatList, RefreshControl, StyleSheet, View } from "react-native";
import { ActivityIndicator, Appbar, Card, Chip, Text, useTheme } from "react-native-paper";
import { SafeAreaView } from "react-native-safe-area-context";

import { NotificationBell } from "@/src/components/NotificationBell";
import { Order, SellerSummary, api } from "@/src/lib/api";
import { useAuth } from "@/src/lib/auth-context";
import { useNetwork } from "@/src/lib/network";
import { CACHE_SCOPES, offlineCache } from "@/src/lib/offline-cache";

type OrderWithSeller = Order & { seller: SellerSummary | null };

const STATUS_COLOR: Record<string, { bg: string; fg: string }> = {
  Requested: { bg: "#FFF3E0", fg: "#A65B00" },
  Accepted: { bg: "#E8F5E9", fg: "#1B5E20" },
  Delivered: { bg: "#DBEAFE", fg: "#1A5276" },
  Rejected: { bg: "#FDECEA", fg: "#8C1D18" },
  Cancelled: { bg: "#F3F4F6", fg: "#52525B" },
  Expired: { bg: "#F3F4F6", fg: "#52525B" },
};

export default function BuyerOrders() {
  const theme = useTheme();
  const { user } = useAuth();
  const { online } = useNetwork();
  const [orders, setOrders] = useState<OrderWithSeller[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [fromCache, setFromCache] = useState(false);

  const load = useCallback(async () => {
    if (!user) return;
    if (!online) {
      const cached = await offlineCache.load<OrderWithSeller[]>(
        CACHE_SCOPES.buyerOrders,
        user.userId,
        [],
      );
      setOrders(cached);
      setFromCache(true);
      setLoading(false);
      return;
    }
    try {
      const { orders: list } = await api.buyerOrders();
      setOrders(list);
      setFromCache(false);
      await offlineCache.save(CACHE_SCOPES.buyerOrders, user.userId, list);
    } catch {
      const cached = await offlineCache.load<OrderWithSeller[]>(
        CACHE_SCOPES.buyerOrders,
        user.userId,
        [],
      );
      setOrders(cached);
      setFromCache(true);
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

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: theme.colors.background }} edges={["top"]}>
      <Appbar.Header mode="small" elevated>
        <Appbar.Content title="My Orders" />
        <NotificationBell testID="buyer-orders-bell" />
      </Appbar.Header>
      {loading ? (
        <View style={styles.center}><ActivityIndicator /></View>
      ) : (
        <FlatList
          data={orders}
          keyExtractor={(o) => o.orderId}
          contentContainerStyle={{ padding: 16, paddingBottom: 32 }}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
          ItemSeparatorComponent={() => <View style={{ height: 12 }} />}
          ListHeaderComponent={
            fromCache ? (
              <View style={[styles.cacheNote, { backgroundColor: theme.colors.surfaceVariant }]}>
                <Text variant="labelMedium" style={{ color: theme.colors.onSurfaceVariant }}>
                  Showing offline-saved orders
                </Text>
              </View>
            ) : null
          }
          ListEmptyComponent={
            <View style={styles.empty}>
              <Text variant="titleMedium" style={{ marginBottom: 4 }}>No orders yet</Text>
              <Text variant="bodyMedium" style={{ color: theme.colors.onSurfaceVariant, textAlign: "center", paddingHorizontal: 32 }}>
                Browse a connected seller and place your first order.
              </Text>
            </View>
          }
          renderItem={({ item }) => {
            const c = STATUS_COLOR[item.orderStatus] || { bg: theme.colors.surfaceVariant, fg: theme.colors.onSurfaceVariant };
            return (
              <Card
                style={styles.card}
                onPress={() => router.push({ pathname: "/buyer-order-detail", params: { orderId: item.orderId } })}
                testID={`order-${item.orderNumber}`}
              >
                <Card.Content>
                  <View style={styles.row}>
                    <Text variant="titleMedium" style={{ fontWeight: "700" }}>{item.orderNumber}</Text>
                    <Chip compact style={{ backgroundColor: c.bg }} textStyle={{ color: c.fg, fontWeight: "700" }}>
                      {item.orderStatus}
                    </Chip>
                  </View>
                  <Text variant="bodyMedium" style={{ color: theme.colors.onSurfaceVariant, marginTop: 4 }}>
                    {item.seller?.businessName || "Seller"} · {new Date(item.requestedDateTime).toLocaleDateString()}
                  </Text>
                  <Text variant="titleMedium" style={{ marginTop: 8, fontWeight: "700" }}>₹{item.totalAmount.toFixed(2)}</Text>
                </Card.Content>
              </Card>
            );
          }}
        />
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  center: { flex: 1, alignItems: "center", justifyContent: "center" },
  empty: { alignItems: "center", paddingTop: 60 },
  card: { borderRadius: 16 },
  row: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  cacheNote: {
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 10,
    marginBottom: 12,
    alignItems: "center",
  },
});
