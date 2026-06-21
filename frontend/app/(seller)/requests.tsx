import { useFocusEffect } from "expo-router";
import { useCallback, useState } from "react";
import { FlatList, RefreshControl, StyleSheet, View } from "react-native";
import { ActivityIndicator, Appbar, Button, Card, Chip, SegmentedButtons, Snackbar, Text, useTheme } from "react-native-paper";
import { SafeAreaView } from "react-native-safe-area-context";

import { Connection, api } from "@/src/lib/api";

export default function SellerRequests() {
  const theme = useTheme();
  const [filter, setFilter] = useState<"Pending" | "Accepted" | "Rejected">("Pending");
  const [connections, setConnections] = useState<Connection[]>([]);
  const [loading, setLoading] = useState(true);
  const [snack, setSnack] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { connections: list } = await api.sellerConnections(filter);
      setConnections(list);
    } catch (e: any) {
      setSnack(e?.message || "Failed to load");
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const onAccept = async (id: string) => {
    try {
      await api.acceptConnection(id);
      setSnack("Buyer connected");
      load();
    } catch (e: any) {
      setSnack(e?.message || "Failed");
    }
  };

  const onReject = async (id: string) => {
    try {
      await api.rejectConnection(id);
      setSnack("Request rejected");
      load();
    } catch (e: any) {
      setSnack(e?.message || "Failed");
    }
  };

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: theme.colors.background }} edges={["top"]}>
      <Appbar.Header mode="small" elevated>
        <Appbar.Content title="Buyer Requests" />
      </Appbar.Header>
      <View style={styles.filterRow}>
        <SegmentedButtons
          value={filter}
          onValueChange={(v) => setFilter(v as any)}
          buttons={[
            { value: "Pending", label: "Pending", testID: "filter-pending" },
            { value: "Accepted", label: "Accepted", testID: "filter-accepted" },
            { value: "Rejected", label: "Rejected", testID: "filter-rejected" },
          ]}
        />
      </View>
      {loading ? (
        <View style={styles.center}><ActivityIndicator /></View>
      ) : (
        <FlatList
          data={connections}
          keyExtractor={(c) => c.connectionId}
          contentContainerStyle={{ padding: 16, paddingBottom: 32 }}
          refreshControl={<RefreshControl refreshing={false} onRefresh={load} />}
          ListEmptyComponent={
            <View style={styles.empty}>
              <Text variant="titleMedium">No {filter.toLowerCase()} requests</Text>
            </View>
          }
          renderItem={({ item }) => (
            <Card style={styles.card} testID={`request-${item.connectionId}`}>
              <Card.Content>
                <View style={styles.row}>
                  <View style={{ flex: 1 }}>
                    <Text variant="titleMedium" style={{ fontWeight: "700" }}>
                      {item.buyer ? `${item.buyer.firstName} ${item.buyer.lastName}` : "Buyer"}
                    </Text>
                    <Text variant="bodySmall" style={{ color: theme.colors.onSurfaceVariant, marginTop: 2 }}>
                      {item.buyer?.mobileNumber ? `+${item.buyer.mobileNumber}` : ""}{item.buyer?.pincode ? ` · ${item.buyer.pincode}` : ""}
                    </Text>
                    <Text variant="bodySmall" style={{ color: theme.colors.onSurfaceVariant, marginTop: 4 }}>
                      Requested {new Date(item.requestedDateTime).toLocaleDateString()}
                    </Text>
                  </View>
                  <Chip compact mode="outlined">{item.status}</Chip>
                </View>
                {filter === "Pending" && (
                  <View style={styles.actions}>
                    <Button mode="contained" icon="check" onPress={() => onAccept(item.connectionId)} style={styles.btn} testID={`accept-${item.connectionId}`}>
                      Accept
                    </Button>
                    <Button mode="outlined" icon="close" onPress={() => onReject(item.connectionId)} style={styles.btn} testID={`reject-${item.connectionId}`}>
                      Reject
                    </Button>
                  </View>
                )}
              </Card.Content>
            </Card>
          )}
        />
      )}
      <Snackbar visible={!!snack} onDismiss={() => setSnack("")} duration={2500}>{snack}</Snackbar>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  filterRow: { paddingHorizontal: 16, paddingTop: 12 },
  center: { flex: 1, alignItems: "center", justifyContent: "center" },
  empty: { alignItems: "center", paddingTop: 60 },
  card: { borderRadius: 16, marginBottom: 12 },
  row: { flexDirection: "row", alignItems: "flex-start" },
  actions: { flexDirection: "row", gap: 12, marginTop: 12 },
  btn: { flex: 1, borderRadius: 12 },
});
