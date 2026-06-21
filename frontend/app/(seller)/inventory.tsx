import { router, useFocusEffect } from "expo-router";
import { useCallback, useState } from "react";
import { FlatList, StyleSheet, View } from "react-native";
import { ActivityIndicator, Appbar, Card, Chip, FAB, IconButton, SegmentedButtons, Snackbar, Text, useTheme } from "react-native-paper";
import { SafeAreaView } from "react-native-safe-area-context";

import { SellerItem, api } from "@/src/lib/api";

export default function Inventory() {
  const theme = useTheme();
  const [items, setItems] = useState<SellerItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<"active" | "all">("active");
  const [snack, setSnack] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { items: list } = await api.listItems(filter === "all");
      setItems(list);
    } catch (e: any) {
      setSnack(e?.message || "Failed to load items");
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load]),
  );

  const onDelete = async (id: string) => {
    try {
      await api.deleteItem(id);
      setSnack("Item marked inactive");
      load();
    } catch (e: any) {
      setSnack(e?.message || "Failed to delete");
    }
  };

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: theme.colors.background }} edges={["top"]}>
      <Appbar.Header mode="small" elevated>
        <Appbar.Content title="Inventory" />
      </Appbar.Header>

      <View style={styles.filterRow}>
        <SegmentedButtons
          value={filter}
          onValueChange={(v) => setFilter(v as any)}
          buttons={[
            { value: "active", label: "Active", testID: "filter-active" },
            { value: "all", label: "All", testID: "filter-all" },
          ]}
        />
      </View>

      {loading ? (
        <View style={styles.center}>
          <ActivityIndicator />
        </View>
      ) : items.length === 0 ? (
        <View style={styles.center}>
          <Text variant="titleMedium" style={{ marginBottom: 4 }}>No items yet</Text>
          <Text variant="bodyMedium" style={{ color: theme.colors.onSurfaceVariant, textAlign: "center", paddingHorizontal: 32 }}>
            Tap the + button to add your first inventory item.
          </Text>
        </View>
      ) : (
        <FlatList
          data={items}
          keyExtractor={(i) => i.itemId}
          contentContainerStyle={{ padding: 16, paddingBottom: 96 }}
          renderItem={({ item }) => (
            <Card style={styles.card} testID={`item-card-${item.itemId}`}>
              <Card.Content>
                <View style={styles.cardHeader}>
                  <View style={{ flex: 1 }}>
                    <View style={{ flexDirection: "row", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
                      <Text variant="titleMedium" style={{ fontWeight: "700" }}>{item.itemName}</Text>
                      {item.lowInventory && item.isActive && (
                        <Chip compact icon="alert" mode="flat" testID={`low-${item.itemId}`} style={{ backgroundColor: theme.colors.errorContainer }} textStyle={{ color: theme.colors.onErrorContainer }}>
                          Low
                        </Chip>
                      )}
                    </View>
                    <Text variant="bodySmall" style={{ color: theme.colors.onSurfaceVariant, marginTop: 2 }}>
                      Unit: {item.unitType} · {item.isActive ? "Active" : "Inactive"}
                    </Text>
                  </View>
                  <View style={styles.actions}>
                    <IconButton icon="pencil" onPress={() => router.push({ pathname: "/seller-edit-item", params: { itemId: item.itemId } })} testID={`edit-${item.itemId}`} />
                    {item.isActive && (
                      <IconButton icon="delete" onPress={() => onDelete(item.itemId)} testID={`delete-${item.itemId}`} />
                    )}
                  </View>
                </View>
                <View style={styles.kvRow}>
                  <KV label="Price" value={`₹${item.pricePerUnit}/${item.unitType}`} />
                  <KV label="Available" value={`${item.availableQuantity}`} />
                  <KV label="Reserved" value={`${item.reservedQuantity}`} />
                  <KV label="Min Qty" value={`${item.minimumOrderQuantity}`} />
                  <KV label="Step" value={`${item.unitIncrement}`} />
                </View>
              </Card.Content>
            </Card>
          )}
        />
      )}

      <FAB icon="plus" style={styles.fab} onPress={() => router.push("/seller-add-item")} testID="add-item-fab" />

      <Snackbar visible={!!snack} onDismiss={() => setSnack("")} duration={2500}>
        {snack}
      </Snackbar>
    </SafeAreaView>
  );
}

function KV({ label, value }: { label: string; value: string }) {
  const theme = useTheme();
  return (
    <View style={styles.kv}>
      <Text variant="labelSmall" style={{ color: theme.colors.onSurfaceVariant }}>{label}</Text>
      <Text variant="bodyMedium" style={{ fontWeight: "600", marginTop: 2 }}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  filterRow: { paddingHorizontal: 16, paddingTop: 12 },
  center: { flex: 1, alignItems: "center", justifyContent: "center" },
  card: { borderRadius: 16, marginBottom: 12 },
  cardHeader: { flexDirection: "row", alignItems: "center" },
  actions: { flexDirection: "row" },
  kvRow: { flexDirection: "row", flexWrap: "wrap", gap: 16, marginTop: 12 },
  kv: { minWidth: 70 },
  fab: { position: "absolute", right: 16, bottom: 24, borderRadius: 16 },
});
