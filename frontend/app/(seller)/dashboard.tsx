import { router, useFocusEffect } from "expo-router";
import { useCallback, useState } from "react";
import { ScrollView, StyleSheet, View } from "react-native";
import { Appbar, Button, Card, Snackbar, Surface, Switch, Text, useTheme } from "react-native-paper";
import { SafeAreaView } from "react-native-safe-area-context";

import { api } from "@/src/lib/api";
import { useAuth } from "@/src/lib/auth-context";

type Stats = {
  activeItems: number;
  lowInventoryCount: number;
  pendingRequests: number;
  openOrders: number;
  lowInventoryThreshold: number;
  availabilityStatus: "Open" | "Closed";
};

export default function SellerDashboard() {
  const theme = useTheme();
  const { user, refresh, signOut } = useAuth();
  const [stats, setStats] = useState<Stats | null>(null);
  const [snack, setSnack] = useState("");
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try {
      const s = await api.sellerDashboard();
      setStats(s);
    } catch (e: any) {
      setSnack(e?.message || "Failed to load dashboard");
    }
  }, []);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  if (!user) return null;

  const isOpen = (stats?.availabilityStatus || user.availabilityStatus || "Open") === "Open";

  const onToggle = async (next: boolean) => {
    setSaving(true);
    try {
      await api.setAvailability(next ? "Open" : "Closed");
      await refresh();
      await load();
      setSnack(next ? "You are Open for orders" : "You are Closed for new orders");
    } catch (e: any) {
      setSnack(e?.message || "Failed to update availability");
    } finally {
      setSaving(false);
    }
  };

  const onLogout = async () => {
    await signOut();
    router.replace("/");
  };

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: theme.colors.background }} edges={["top"]}>
      <Appbar.Header mode="small" elevated>
        <Appbar.Content title="Dashboard" />
        <Appbar.Action icon="logout" onPress={onLogout} testID="logout-btn" />
      </Appbar.Header>
      <ScrollView contentContainerStyle={styles.body}>
        <Surface elevation={2} style={[styles.hero, { backgroundColor: theme.colors.primaryContainer }]}>
          <Text variant="labelLarge" style={{ color: theme.colors.onPrimaryContainer }}>
            Business
          </Text>
          <Text variant="headlineSmall" testID="business-name" style={{ color: theme.colors.onPrimaryContainer, fontWeight: "700", marginTop: 4 }}>
            {user.businessName}
          </Text>
          <View style={styles.codeRow}>
            <Text variant="labelMedium" style={{ color: theme.colors.onPrimaryContainer }}>
              Seller Code:{" "}
            </Text>
            <Text variant="titleMedium" testID="seller-code" style={{ color: theme.colors.onPrimaryContainer, fontWeight: "700" }}>
              {user.sellerCode}
            </Text>
          </View>
        </Surface>

        <Card style={[styles.card, { borderColor: isOpen ? theme.colors.primary : theme.colors.outline, borderWidth: 1 }]} testID="availability-card">
          <Card.Content>
            <View style={styles.rowBetween}>
              <View style={{ flex: 1 }}>
                <Text variant="labelMedium" style={{ color: theme.colors.onSurfaceVariant }}>Availability</Text>
                <Text variant="titleMedium" style={{ marginTop: 2, fontWeight: "700" }} testID="availability-status">
                  {isOpen ? "Open · Accepting orders" : "Closed · Not accepting new orders"}
                </Text>
                <Text variant="bodySmall" style={{ marginTop: 4, color: theme.colors.onSurfaceVariant }}>
                  Buyers can still browse your items when closed.
                </Text>
              </View>
              <Switch value={isOpen} onValueChange={onToggle} disabled={saving} testID="availability-switch" />
            </View>
          </Card.Content>
        </Card>

        <View style={styles.tilesRow}>
          <Tile label="Active items" value={stats?.activeItems ?? "—"} icon="📦" />
          <Tile label="Low inventory" value={stats?.lowInventoryCount ?? "—"} icon="⚠️" warn={(stats?.lowInventoryCount ?? 0) > 0} testID="low-inventory-tile" />
        </View>
        <View style={styles.tilesRow}>
          <Tile label="Pending requests" value={stats?.pendingRequests ?? "—"} icon="🤝" />
          <Tile label="Open orders" value={stats?.openOrders ?? "—"} icon="📋" />
        </View>

        {!!stats && stats.lowInventoryCount > 0 && (
          <Card style={[styles.card, { backgroundColor: theme.colors.errorContainer }]} testID="low-inventory-banner">
            <Card.Content>
              <Text variant="titleSmall" style={{ color: theme.colors.onErrorContainer, fontWeight: "700" }}>
                Low Inventory
              </Text>
              <Text variant="bodyMedium" style={{ color: theme.colors.onErrorContainer, marginTop: 4 }}>
                {stats.lowInventoryCount} item{stats.lowInventoryCount > 1 ? "s" : ""} below {stats.lowInventoryThreshold}. Restock from Inventory.
              </Text>
              <Button mode="contained-tonal" style={{ marginTop: 12, borderRadius: 12, alignSelf: "flex-start" }} onPress={() => router.push("/(seller)/inventory")} testID="go-inventory-btn">
                Open Inventory
              </Button>
            </Card.Content>
          </Card>
        )}

        <Button mode="contained" onPress={() => router.push("/seller-add-item")} icon="plus" style={{ marginTop: 16, borderRadius: 16 }} contentStyle={{ height: 52 }} testID="dashboard-add-item-btn">
          Add a new item
        </Button>
      </ScrollView>
      <Snackbar visible={!!snack} onDismiss={() => setSnack("")} duration={2500}>{snack}</Snackbar>
    </SafeAreaView>
  );
}

function Tile({ label, value, icon, warn, testID }: { label: string; value: number | string; icon: string; warn?: boolean; testID?: string }) {
  const theme = useTheme();
  return (
    <Surface elevation={1} style={[styles.tile, warn && { backgroundColor: theme.colors.errorContainer }]} testID={testID}>
      <Text style={{ fontSize: 22 }}>{icon}</Text>
      <Text variant="headlineSmall" style={{ fontWeight: "800", marginTop: 4, color: warn ? theme.colors.onErrorContainer : theme.colors.onSurface }}>
        {value}
      </Text>
      <Text variant="bodySmall" style={{ color: warn ? theme.colors.onErrorContainer : theme.colors.onSurfaceVariant, marginTop: 2 }}>
        {label}
      </Text>
    </Surface>
  );
}

const styles = StyleSheet.create({
  body: { padding: 16, paddingBottom: 32 },
  hero: { padding: 20, borderRadius: 20 },
  codeRow: { flexDirection: "row", alignItems: "baseline", marginTop: 12 },
  card: { borderRadius: 16, marginTop: 16 },
  rowBetween: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  tilesRow: { flexDirection: "row", gap: 12, marginTop: 16 },
  tile: { flex: 1, padding: 16, borderRadius: 16 },
});
