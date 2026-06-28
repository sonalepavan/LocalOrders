import { router, useFocusEffect } from "expo-router";
import { useCallback, useMemo, useState } from "react";
import { FlatList, RefreshControl, StyleSheet, View } from "react-native";
import {
  ActivityIndicator,
  Appbar,
  Card,
  Chip,
  SegmentedButtons,
  Snackbar,
  Text,
  useTheme,
} from "react-native-paper";
import { SafeAreaView } from "react-native-safe-area-context";

import { NotificationBell } from "@/src/components/NotificationBell";
import {
  CustomRequest,
  CustomRequestStatus,
  SellerSummary,
  api,
} from "@/src/lib/api";

type Row = CustomRequest & { seller: SellerSummary | null };

// Reused status-chip palette — mirrors STATUS_COLOR from orders screens
const STATUS_COLOR: Record<CustomRequestStatus, { bg: string; fg: string; label: string }> = {
  SAVED: { bg: "#F3F4F6", fg: "#52525B", label: "Saved" },
  NEW_REQUEST: { bg: "#FFF3E0", fg: "#A65B00", label: "Sent" },
  QUOTE_SENT: { bg: "#DBEAFE", fg: "#1A5276", label: "Quote received" },
  ACCEPTED: { bg: "#E8F5E9", fg: "#1B5E20", label: "Accepted" },
  COMPLETED: { bg: "#DEF7EC", fg: "#03543F", label: "Completed" },
  REJECTED_BY_BUYER: { bg: "#FDECEA", fg: "#8C1D18", label: "Rejected by you" },
  REJECTED_BY_SELLER: { bg: "#FDECEA", fg: "#8C1D18", label: "Rejected by seller" },
};

// Active vs History grouping (buyer view)
const ACTIVE_STATUSES: CustomRequestStatus[] = ["SAVED", "NEW_REQUEST", "QUOTE_SENT", "ACCEPTED"];
const HISTORY_STATUSES: CustomRequestStatus[] = ["COMPLETED", "REJECTED_BY_BUYER", "REJECTED_BY_SELLER"];

export default function BuyerSavedRequests() {
  const theme = useTheme();
  const [rows, setRows] = useState<Row[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [snack, setSnack] = useState("");
  const [tab, setTab] = useState<"active" | "history">("active");

  const load = useCallback(async () => {
    try {
      const { requests } = await api.listBuyerCustomRequests();
      setRows(requests);
    } catch (e: any) {
      setSnack(e?.message || "Failed to load requests");
    } finally {
      setLoading(false);
    }
  }, []);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const onRefresh = useCallback(async () => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  }, [load]);

  const visible = useMemo(() => {
    const set = tab === "active" ? ACTIVE_STATUSES : HISTORY_STATUSES;
    return rows.filter((r) => set.includes(r.status));
  }, [rows, tab]);

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: theme.colors.background }} edges={["top"]}>
      <Appbar.Header mode="small" elevated>
        <Appbar.BackAction onPress={() => router.back()} testID="back-btn" />
        <Appbar.Content title="My Saved Requests" />
        <NotificationBell testID="saved-requests-bell" />
      </Appbar.Header>

      {loading ? (
        <View style={styles.center}>
          <ActivityIndicator />
        </View>
      ) : (
        <FlatList
          data={visible}
          keyExtractor={(r) => r.requestId}
          contentContainerStyle={{ padding: 16, paddingBottom: 32 }}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
          ItemSeparatorComponent={() => <View style={{ height: 12 }} />}
          ListHeaderComponent={
            <View style={{ marginBottom: 12 }}>
              <SegmentedButtons
                value={tab}
                onValueChange={(v) => setTab(v as "active" | "history")}
                buttons={[
                  { value: "active", label: "Active", testID: "tab-active" },
                  { value: "history", label: "History", testID: "tab-history" },
                ]}
              />
            </View>
          }
          ListEmptyComponent={
            <View style={styles.empty}>
              <Text variant="titleMedium" style={{ marginBottom: 4 }}>
                {tab === "active" ? "No active requests" : "No history yet"}
              </Text>
              <Text
                variant="bodyMedium"
                style={{
                  color: theme.colors.onSurfaceVariant,
                  textAlign: "center",
                  paddingHorizontal: 32,
                }}
              >
                {tab === "active"
                  ? "Send a custom request to a seller from their items page."
                  : "Completed and rejected requests will appear here."}
              </Text>
            </View>
          }
          renderItem={({ item }) => {
            const c = STATUS_COLOR[item.status];
            const sellerName =
              item.seller?.businessName ||
              (item.seller ? `${item.seller.firstName} ${item.seller.lastName}` : "Seller");
            return (
              <Card
                style={styles.card}
                onPress={() =>
                  router.push({
                    pathname: "/buyer-custom-request-detail",
                    params: { requestId: item.requestId },
                  })
                }
                testID={`custom-request-${item.requestId}`}
              >
                <Card.Content>
                  <View style={styles.row}>
                    <Text
                      variant="titleMedium"
                      style={{ fontWeight: "700", flex: 1 }}
                      numberOfLines={1}
                    >
                      {sellerName}
                    </Text>
                    <Chip
                      compact
                      style={{ backgroundColor: c.bg }}
                      textStyle={{ color: c.fg, fontWeight: "700" }}
                      testID={`custom-request-status-${item.requestId}`}
                    >
                      {c.label}
                    </Chip>
                  </View>
                  <Text
                    variant="bodyMedium"
                    style={{
                      marginTop: 8,
                      color: theme.colors.onSurfaceVariant,
                    }}
                    numberOfLines={3}
                  >
                    {item.requestDetails}
                  </Text>
                  <View style={styles.metaRow}>
                    <Text variant="labelSmall" style={{ color: theme.colors.onSurfaceVariant }}>
                      {new Date(item.createdAt).toLocaleDateString()}
                    </Text>
                    {item.status === "QUOTE_SENT" && item.quoteAmount != null && (
                      <Text
                        variant="labelMedium"
                        style={{ color: theme.colors.primary, fontWeight: "700" }}
                      >
                        Quote ₹{item.quoteAmount.toFixed(2)}
                      </Text>
                    )}
                    {item.status === "ACCEPTED" && item.quoteAmount != null && (
                      <Text
                        variant="labelMedium"
                        style={{ color: theme.colors.primary, fontWeight: "700" }}
                      >
                        ₹{item.quoteAmount.toFixed(2)}
                      </Text>
                    )}
                  </View>
                </Card.Content>
              </Card>
            );
          }}
        />
      )}

      <Snackbar visible={!!snack} onDismiss={() => setSnack("")} duration={2500}>
        {snack}
      </Snackbar>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  center: { flex: 1, alignItems: "center", justifyContent: "center" },
  empty: { alignItems: "center", paddingTop: 60 },
  card: { borderRadius: 16 },
  row: { flexDirection: "row", alignItems: "center", gap: 12 },
  metaRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginTop: 12,
  },
});
