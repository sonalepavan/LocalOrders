import { router, useFocusEffect } from "expo-router";
import { useCallback, useState } from "react";
import { BackHandler, FlatList, RefreshControl, StyleSheet, View } from "react-native";
import { ActivityIndicator, Appbar, Banner, Card, Chip, FAB, Snackbar, Text, useTheme } from "react-native-paper";
import { SafeAreaView } from "react-native-safe-area-context";

import { NotificationBell } from "@/src/components/NotificationBell";
import { Connection, api } from "@/src/lib/api";
import { useAuth } from "@/src/lib/auth-context";
import { Cart, getCart } from "@/src/lib/cart";

export default function BuyerDashboard() {
  const theme = useTheme();
  const { user, signOut } = useAuth();
  const [connections, setConnections] = useState<Connection[]>([]);
  const [loading, setLoading] = useState(true);
  const [cart, setCart] = useState<Cart | null>(null);
  const [snack, setSnack] = useState("");

  const load = useCallback(async () => {
    try {
      const [{ connections: conns }, c] = await Promise.all([api.buyerConnections(), getCart()]);
      setConnections(conns);
      setCart(c);
    } catch (e: any) {
      setSnack(e?.message || "Failed to load");
    } finally {
      setLoading(false);
    }
  }, []);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  // Android hardware back on Home → logout and go to Login (replace, no back-stack)
  useFocusEffect(
    useCallback(() => {
      const onBack = () => {
        (async () => {
          await signOut();
          router.replace("/login");
        })();
        return true; // prevent default (which would re-enter the index.tsx loading loop)
      };
      const sub = BackHandler.addEventListener("hardwareBackPress", onBack);
      return () => sub.remove();
    }, [signOut]),
  );

  if (!user) return null;

  const accepted = connections.filter((c) => c.status === "Accepted");
  const pending = connections.filter((c) => c.status === "Pending");

  const onLogout = async () => {
    await signOut();
    router.replace("/login");
  };

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: theme.colors.background }} edges={["top"]}>
      <Appbar.Header mode="small" elevated>
        <Appbar.Content title="Sellers" />
        <NotificationBell testID="buyer-home-bell" />
        <Appbar.Action icon="magnify" onPress={() => router.push("/buyer-add-seller")} testID="search-seller-btn" />
        <Appbar.Action icon="logout" onPress={onLogout} testID="logout-btn" />
      </Appbar.Header>

      {cart && cart.lines.length > 0 && (
        <Banner
          visible
          icon="cart"
          actions={[{ label: "View Cart", onPress: () => router.push("/buyer-cart") }]}
        >
          <Text>Cart: {cart.lines.length} items from {cart.sellerName}</Text>
        </Banner>
      )}

      {loading ? (
        <View style={styles.center}><ActivityIndicator /></View>
      ) : (
        <FlatList
          data={accepted}
          keyExtractor={(c) => c.connectionId}
          contentContainerStyle={{ padding: 16, paddingBottom: 96 }}
          refreshControl={<RefreshControl refreshing={false} onRefresh={load} />}
          ListHeaderComponent={
            <View>
              <Text variant="titleMedium" style={styles.section}>
                Connected Sellers ({accepted.length})
              </Text>
              {pending.length > 0 && (
                <Card style={[styles.pendingCard, { backgroundColor: theme.colors.tertiaryContainer }]} testID="pending-card">
                  <Card.Content>
                    <Text variant="titleSmall" style={{ color: theme.colors.onTertiaryContainer }}>
                      {pending.length} pending request{pending.length > 1 ? "s" : ""}
                    </Text>
                    <Text variant="bodySmall" style={{ color: theme.colors.onTertiaryContainer, marginTop: 4 }}>
                      Awaiting seller approval. Requests expire in 7 days.
                    </Text>
                  </Card.Content>
                </Card>
              )}
            </View>
          }
          renderItem={({ item }) => (
            <Card
              style={styles.card}
              onPress={() => router.push({ pathname: "/buyer-seller-items", params: { sellerId: item.sellerId } })}
              testID={`seller-card-${item.sellerId}`}
            >
              <Card.Content>
                <Text variant="titleMedium" style={{ fontWeight: "700" }}>{item.seller?.businessName || "Seller"}</Text>
                <View style={styles.row}>
                  <Chip compact style={styles.chip} icon="barcode">{item.seller?.sellerCode}</Chip>
                  {item.seller?.pincode ? <Chip compact style={styles.chip} icon="map-marker">{item.seller.pincode}</Chip> : null}
                </View>
              </Card.Content>
            </Card>
          )}
          ListEmptyComponent={
            <View style={styles.empty}>
              <Text variant="titleMedium" style={{ marginBottom: 4 }}>No connected sellers</Text>
              <Text variant="bodyMedium" style={{ color: theme.colors.onSurfaceVariant, textAlign: "center", paddingHorizontal: 32 }}>
                Tap the + button to connect using a Seller Code.
              </Text>
            </View>
          }
        />
      )}
      <FAB icon="plus" style={styles.fab} onPress={() => router.push("/buyer-add-seller")} testID="add-seller-fab" />
      <Snackbar visible={!!snack} onDismiss={() => setSnack("")} duration={3000}>{snack}</Snackbar>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  center: { flex: 1, alignItems: "center", justifyContent: "center" },
  section: { marginBottom: 12 },
  pendingCard: { borderRadius: 16, marginBottom: 12 },
  card: { borderRadius: 16, marginBottom: 12 },
  row: { flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: 8 },
  chip: {},
  empty: { alignItems: "center", paddingTop: 60 },
  fab: { position: "absolute", right: 16, bottom: 24, borderRadius: 16 },
});
