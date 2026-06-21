import { router, useFocusEffect } from "expo-router";
import { useCallback, useState } from "react";
import { FlatList, RefreshControl, StyleSheet, View } from "react-native";
import { ActivityIndicator, Appbar, Card, Chip, Text, useTheme } from "react-native-paper";
import { SafeAreaView } from "react-native-safe-area-context";

import { BuyerSummary, Order, api } from "@/src/lib/api";

type OrderWithBuyer = Order & { buyer: BuyerSummary | null };

export default function SellerOrders() {
  const theme = useTheme();
  const [orders, setOrders] = useState<OrderWithBuyer[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const { orders: list } = await api.sellerOrders();
      setOrders(list);
    } finally {
      setLoading(false);
    }
  }, []);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: theme.colors.background }} edges={["top"]}>
      <Appbar.Header mode="small" elevated>
        <Appbar.Content title="Orders" />
      </Appbar.Header>
      {loading ? (
        <View style={styles.center}><ActivityIndicator /></View>
      ) : (
        <FlatList
          data={orders}
          keyExtractor={(o) => o.orderId}
          contentContainerStyle={{ padding: 16, paddingBottom: 32 }}
          refreshControl={<RefreshControl refreshing={false} onRefresh={load} />}
          ListEmptyComponent={
            <View style={styles.empty}>
              <Text variant="titleMedium">No orders yet</Text>
              <Text variant="bodyMedium" style={{ color: theme.colors.onSurfaceVariant, marginTop: 4 }}>
                Orders placed by your connected buyers will appear here.
              </Text>
            </View>
          }
          renderItem={({ item }) => (
            <Card
              style={styles.card}
              onPress={() => router.push({ pathname: "/buyer-order-detail", params: { orderId: item.orderId } })}
              testID={`order-${item.orderNumber}`}
            >
              <Card.Content>
                <View style={styles.row}>
                  <Text variant="titleMedium" style={{ fontWeight: "700" }}>{item.orderNumber}</Text>
                  <Chip compact mode="outlined">{item.orderStatus}</Chip>
                </View>
                <Text variant="bodyMedium" style={{ color: theme.colors.onSurfaceVariant, marginTop: 4 }}>
                  {item.buyer ? `${item.buyer.firstName} ${item.buyer.lastName}` : "Buyer"} · {new Date(item.requestedDateTime).toLocaleDateString()}
                </Text>
                <Text variant="titleMedium" style={{ marginTop: 8, fontWeight: "700" }}>₹{item.totalAmount.toFixed(2)}</Text>
              </Card.Content>
            </Card>
          )}
        />
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  center: { flex: 1, alignItems: "center", justifyContent: "center" },
  empty: { alignItems: "center", paddingTop: 60 },
  card: { borderRadius: 16, marginBottom: 12 },
  row: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
});
