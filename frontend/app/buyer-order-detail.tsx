import { router, useLocalSearchParams } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import { Linking, Platform, ScrollView, StyleSheet, View } from "react-native";
import {
  ActivityIndicator,
  Appbar,
  Button,
  Card,
  Chip,
  Dialog,
  Divider,
  Portal,
  Snackbar,
  Surface,
  Text,
  TextInput,
  useTheme,
} from "react-native-paper";
import { SafeAreaView } from "react-native-safe-area-context";

import { BuyerSummary, Order, OrderItem, OrderStatus, SellerSummary, api } from "@/src/lib/api";
import { useAuth } from "@/src/lib/auth-context";

type Action = "accept" | "reject" | "deliver" | "cancel" | null;

const STATUS_COLORS: Record<OrderStatus, { bg: string; fg: string }> = {
  Requested: { bg: "#FFF4E5", fg: "#8B4F00" },
  Accepted: { bg: "#E3F2FD", fg: "#0B4A78" },
  Rejected: { bg: "#FDECEA", fg: "#8A1F11" },
  Cancelled: { bg: "#F1F1F1", fg: "#444" },
  Delivered: { bg: "#E6F4EA", fg: "#1E5631" },
  Expired: { bg: "#F1F1F1", fg: "#444" },
};

export default function OrderDetail() {
  const { orderId } = useLocalSearchParams<{ orderId: string }>();
  const theme = useTheme();
  const { user } = useAuth();
  const [order, setOrder] = useState<Order | null>(null);
  const [items, setItems] = useState<OrderItem[]>([]);
  const [counterparty, setCounterparty] = useState<BuyerSummary | SellerSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [snack, setSnack] = useState("");
  const [pendingAction, setPendingAction] = useState<Action>(null);
  const [reason, setReason] = useState("");
  const [reasonErr, setReasonErr] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.orderDetail(orderId);
      setOrder(res.order);
      setItems(res.items);
      setCounterparty(res.counterparty);
    } catch (e: any) {
      setSnack(e?.message || "Failed to load order");
    } finally {
      setLoading(false);
    }
  }, [orderId]);

  useEffect(() => { load(); }, [load]);

  const isSeller = user?.userType === "seller";
  const isBuyer = user?.userType === "buyer";
  const status = order?.orderStatus;

  const partyTitle = counterparty
    ? "businessName" in counterparty && counterparty.businessName
      ? counterparty.businessName
      : `${counterparty.firstName} ${counterparty.lastName}`
    : "";
  const partyMobile = counterparty?.mobileNumber || "";

  const onCall = async () => {
    if (!partyMobile) return;
    const url = `tel:${partyMobile}`;
    const can = await Linking.canOpenURL(url);
    if (!can) { setSnack(Platform.OS === "web" ? "Calling is supported on Android/iOS only" : "Calling not supported"); return; }
    Linking.openURL(url);
  };

  const open = (a: Action) => {
    setPendingAction(a);
    setReason("");
    setReasonErr("");
  };

  const close = () => {
    if (busy) return;
    setPendingAction(null);
    setReason("");
    setReasonErr("");
  };

  const confirm = async () => {
    if (!pendingAction || !order) return;
    if (pendingAction === "reject" && !reason.trim()) {
      setReasonErr("Rejection reason is required");
      return;
    }
    setBusy(true);
    try {
      if (pendingAction === "accept") await api.acceptOrder(order.orderId);
      else if (pendingAction === "deliver") await api.deliverOrder(order.orderId);
      else if (pendingAction === "reject") await api.rejectOrder(order.orderId, reason.trim());
      else if (pendingAction === "cancel") await api.cancelOrder(order.orderId, reason.trim() || undefined);
      setPendingAction(null);
      setReason("");
      setReasonErr("");
      await load();
      setSnack(`Order ${pendingAction === "deliver" ? "marked delivered" : pendingAction + "ed"}`);
    } catch (e: any) {
      setSnack(e?.message || "Action failed");
    } finally {
      setBusy(false);
    }
  };

  if (loading || !order) {
    return (
      <SafeAreaView style={{ flex: 1, backgroundColor: theme.colors.background }} edges={["top"]}>
        <Appbar.Header mode="small" elevated>
          <Appbar.BackAction onPress={() => router.back()} testID="back-btn" />
          <Appbar.Content title="Order Details" />
        </Appbar.Header>
        <View style={styles.center}><ActivityIndicator /></View>
      </SafeAreaView>
    );
  }

  const sc = STATUS_COLORS[status!];
  const canSellerAct = isSeller && status === "Requested";
  const canSellerDeliver = isSeller && status === "Accepted";
  const canBuyerCancel = isBuyer && (status === "Requested" || status === "Accepted");

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: theme.colors.background }} edges={["top"]}>
      <Appbar.Header mode="small" elevated>
        <Appbar.BackAction onPress={() => router.back()} testID="back-btn" />
        <Appbar.Content title="Order Details" />
        {!!partyMobile && (
          <Appbar.Action icon="phone" onPress={onCall} testID="call-counterparty-btn" />
        )}
      </Appbar.Header>
      <ScrollView contentContainerStyle={styles.body}>
        <Surface elevation={2} style={[styles.hero, { backgroundColor: theme.colors.primaryContainer }]}>
          <View style={styles.row}>
            <View style={{ flex: 1 }}>
              <Text variant="labelLarge" style={{ color: theme.colors.onPrimaryContainer }}>Order</Text>
              <Text variant="headlineSmall" testID="order-number" style={{ color: theme.colors.onPrimaryContainer, fontWeight: "700", marginTop: 4 }}>
                {order.orderNumber}
              </Text>
            </View>
            <Chip
              compact
              style={{ backgroundColor: sc.bg }}
              textStyle={{ color: sc.fg, fontWeight: "700" }}
              testID="order-status"
            >
              {status}
            </Chip>
          </View>
          <Text variant="bodyMedium" style={{ color: theme.colors.onPrimaryContainer, marginTop: 10 }}>
            {partyTitle ? `${isBuyer ? "Seller" : "Buyer"}: ${partyTitle}` : ""}
          </Text>
          {!!partyMobile && (
            <Button
              icon="phone"
              mode="contained-tonal"
              onPress={onCall}
              style={{ alignSelf: "flex-start", marginTop: 12, borderRadius: 12 }}
              testID="call-btn"
            >
              Call {isBuyer ? "Seller" : "Buyer"} (+{partyMobile})
            </Button>
          )}
        </Surface>

        <Text variant="titleMedium" style={styles.section}>Items</Text>
        {items.map((i) => (
          <Card key={i.orderItemId} style={styles.card} testID={`order-item-${i.itemId}`}>
            <Card.Content>
              <View style={styles.row}>
                <Text variant="titleMedium" style={{ fontWeight: "700", flex: 1 }}>{i.itemName}</Text>
                <Text variant="titleMedium" style={{ fontWeight: "700" }}>₹{i.itemTotal.toFixed(2)}</Text>
              </View>
              <Text variant="bodySmall" style={{ color: theme.colors.onSurfaceVariant, marginTop: 4 }}>
                {i.quantity} {i.unitType} × ₹{i.pricePerUnit}/{i.unitType}
              </Text>
            </Card.Content>
          </Card>
        ))}

        <Divider style={{ marginVertical: 16 }} />
        <View style={styles.row}>
          <Text variant="titleMedium">Total</Text>
          <Text variant="headlineSmall" style={{ fontWeight: "700" }} testID="order-total">₹{order.totalAmount.toFixed(2)}</Text>
        </View>

        <Text variant="titleMedium" style={styles.section}>Timeline</Text>
        <Card style={styles.card}>
          <Card.Content>
            <Timeline label="Requested" at={order.requestedDateTime} />
            {order.acceptedDateTime && <Timeline label="Accepted" at={order.acceptedDateTime} />}
            {order.rejectedDateTime && <Timeline label="Rejected" at={order.rejectedDateTime} reason={order.rejectionReason || undefined} />}
            {order.cancelledDateTime && <Timeline label="Cancelled" at={order.cancelledDateTime} reason={order.cancellationReason || undefined} />}
            {order.deliveredDateTime && <Timeline label="Delivered" at={order.deliveredDateTime} />}
            {order.expiredDateTime && <Timeline label="Expired (24h)" at={order.expiredDateTime} />}
          </Card.Content>
        </Card>

        {(canSellerAct || canSellerDeliver || canBuyerCancel) && (
          <View style={styles.actions}>
            {canSellerAct && (
              <>
                <Button mode="contained" icon="check" onPress={() => open("accept")} contentStyle={{ height: 48 }} style={styles.actBtn} testID="accept-order-btn">
                  Accept
                </Button>
                <Button mode="outlined" icon="close" onPress={() => open("reject")} contentStyle={{ height: 48 }} style={styles.actBtn} testID="reject-order-btn">
                  Reject
                </Button>
              </>
            )}
            {canSellerDeliver && (
              <Button mode="contained" icon="truck-check" onPress={() => open("deliver")} contentStyle={{ height: 48 }} style={styles.actBtn} testID="deliver-order-btn">
                Mark Delivered
              </Button>
            )}
            {canBuyerCancel && (
              <Button mode="outlined" icon="cancel" onPress={() => open("cancel")} contentStyle={{ height: 48 }} style={styles.actBtn} testID="cancel-order-btn">
                Cancel Order
              </Button>
            )}
          </View>
        )}
      </ScrollView>

      <Portal>
        <Dialog visible={pendingAction !== null} onDismiss={close}>
          <Dialog.Title>
            {pendingAction === "accept" && "Accept this order?"}
            {pendingAction === "reject" && "Reject order"}
            {pendingAction === "deliver" && "Mark as delivered?"}
            {pendingAction === "cancel" && "Cancel order"}
          </Dialog.Title>
          <Dialog.Content>
            {pendingAction === "reject" && (
              <>
                <Text variant="bodyMedium" style={{ marginBottom: 8 }}>Please tell the buyer why you are rejecting.</Text>
                <TextInput
                  label="Rejection reason"
                  value={reason}
                  onChangeText={(t) => { setReason(t); if (t.trim()) setReasonErr(""); }}
                  mode="outlined"
                  multiline
                  numberOfLines={3}
                  testID="reason-input"
                  error={!!reasonErr}
                />
                {!!reasonErr && <Text style={{ color: theme.colors.error, marginTop: 4 }}>{reasonErr}</Text>}
              </>
            )}
            {pendingAction === "cancel" && (
              <TextInput
                label="Reason (optional)"
                value={reason}
                onChangeText={setReason}
                mode="outlined"
                multiline
                numberOfLines={3}
                testID="reason-input"
              />
            )}
            {pendingAction === "accept" && <Text>This will mark the order as Accepted and notify the buyer.</Text>}
            {pendingAction === "deliver" && <Text>This will mark the order as Delivered.</Text>}
          </Dialog.Content>
          <Dialog.Actions>
            <Button onPress={close} disabled={busy} testID="dialog-cancel-btn">Close</Button>
            <Button onPress={confirm} loading={busy} disabled={busy} mode="contained" testID="dialog-confirm-btn">Confirm</Button>
          </Dialog.Actions>
        </Dialog>
      </Portal>

      <Snackbar visible={!!snack} onDismiss={() => setSnack("")} duration={2800}>{snack}</Snackbar>
    </SafeAreaView>
  );
}

function Timeline({ label, at, reason }: { label: string; at: string; reason?: string }) {
  const theme = useTheme();
  return (
    <View style={{ marginBottom: 8 }}>
      <View style={styles.row}>
        <Text variant="labelLarge">{label}</Text>
        <Text variant="bodySmall" style={{ color: theme.colors.onSurfaceVariant }}>
          {new Date(at).toLocaleString()}
        </Text>
      </View>
      {!!reason && (
        <Text variant="bodySmall" style={{ color: theme.colors.onSurfaceVariant, marginTop: 2 }}>
          Reason: {reason}
        </Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  center: { flex: 1, alignItems: "center", justifyContent: "center" },
  body: { padding: 16, paddingBottom: 32 },
  hero: { padding: 20, borderRadius: 20 },
  section: { marginTop: 24, marginBottom: 12 },
  card: { borderRadius: 16, marginBottom: 12 },
  row: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  actions: { marginTop: 24, gap: 12 },
  actBtn: { borderRadius: 14 },
});
