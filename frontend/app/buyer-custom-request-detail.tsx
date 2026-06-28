import { router, useLocalSearchParams } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import { ScrollView, StyleSheet, View } from "react-native";
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
  useTheme,
} from "react-native-paper";
import { SafeAreaView } from "react-native-safe-area-context";

import { CustomRequest, CustomRequestStatus, SellerSummary, api } from "@/src/lib/api";

type Action = "send" | "delete" | "accept" | "reject" | null;

const STATUS_COLOR: Record<CustomRequestStatus, { bg: string; fg: string; label: string }> = {
  SAVED: { bg: "#F3F4F6", fg: "#52525B", label: "Saved" },
  NEW_REQUEST: { bg: "#FFF3E0", fg: "#A65B00", label: "Sent" },
  QUOTE_SENT: { bg: "#DBEAFE", fg: "#1A5276", label: "Quote received" },
  ACCEPTED: { bg: "#E8F5E9", fg: "#1B5E20", label: "Accepted" },
  COMPLETED: { bg: "#DEF7EC", fg: "#03543F", label: "Completed" },
  REJECTED_BY_BUYER: { bg: "#FDECEA", fg: "#8C1D18", label: "Rejected by you" },
  REJECTED_BY_SELLER: { bg: "#FDECEA", fg: "#8C1D18", label: "Rejected by seller" },
};

export default function BuyerCustomRequestDetail() {
  const theme = useTheme();
  const { requestId } = useLocalSearchParams<{ requestId: string }>();
  const [req, setReq] = useState<CustomRequest | null>(null);
  const [seller, setSeller] = useState<SellerSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [snack, setSnack] = useState("");
  const [pending, setPending] = useState<Action>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.getCustomRequest(requestId);
      setReq(res.request);
      // counterparty is SellerSummary for a buyer
      setSeller(res.counterparty as SellerSummary | null);
    } catch (e: any) {
      setSnack(e?.message || "Failed to load");
    } finally {
      setLoading(false);
    }
  }, [requestId]);

  useEffect(() => { load(); }, [load]);

  const open = (a: Action) => setPending(a);
  const close = () => { if (!busy) setPending(null); };

  const confirm = async () => {
    if (!pending || !req) return;
    setBusy(true);
    try {
      if (pending === "send") {
        await api.sendCustomRequest(req.requestId);
        setSnack("Request sent to seller");
      } else if (pending === "delete") {
        await api.deleteCustomRequest(req.requestId);
        setPending(null);
        setBusy(false);
        router.back();
        return;
      } else if (pending === "accept") {
        await api.acceptQuote(req.requestId);
        setSnack("Quote accepted");
      } else if (pending === "reject") {
        await api.rejectQuote(req.requestId);
        setSnack("Quote rejected");
      }
      setPending(null);
      await load();
    } catch (e: any) {
      setSnack(e?.message || "Action failed");
    } finally {
      setBusy(false);
    }
  };

  if (loading || !req) {
    return (
      <SafeAreaView style={{ flex: 1, backgroundColor: theme.colors.background }} edges={["top"]}>
        <Appbar.Header mode="small" elevated>
          <Appbar.BackAction onPress={() => router.back()} testID="back-btn" />
          <Appbar.Content title="Custom Request" />
        </Appbar.Header>
        <View style={styles.center}><ActivityIndicator /></View>
      </SafeAreaView>
    );
  }

  const sc = STATUS_COLOR[req.status];
  const sellerName =
    seller?.businessName || (seller ? `${seller.firstName} ${seller.lastName}` : "Seller");

  const canEdit = req.status === "SAVED";
  const canDelete = req.status === "SAVED";
  const canSend = req.status === "SAVED";
  const canAct = req.status === "QUOTE_SENT";

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: theme.colors.background }} edges={["top"]}>
      <Appbar.Header mode="small" elevated>
        <Appbar.BackAction onPress={() => router.back()} testID="back-btn" />
        <Appbar.Content title="Custom Request" />
        {canEdit && (
          <Appbar.Action
            icon="pencil"
            onPress={() =>
              router.push({
                pathname: "/buyer-custom-request",
                params: { requestId: req.requestId },
              })
            }
            testID="edit-request-btn"
          />
        )}
      </Appbar.Header>
      <ScrollView contentContainerStyle={styles.body}>
        <Surface elevation={2} style={[styles.hero, { backgroundColor: theme.colors.primaryContainer }]}>
          <View style={styles.row}>
            <View style={{ flex: 1 }}>
              <Text variant="labelLarge" style={{ color: theme.colors.onPrimaryContainer }}>Seller</Text>
              <Text
                variant="headlineSmall"
                testID="custom-request-detail-seller-name"
                style={{ color: theme.colors.onPrimaryContainer, fontWeight: "700", marginTop: 4 }}
              >
                {sellerName}
              </Text>
            </View>
            <Chip
              compact
              style={{ backgroundColor: sc.bg }}
              textStyle={{ color: sc.fg, fontWeight: "700" }}
              testID="custom-request-detail-status"
            >
              {sc.label}
            </Chip>
          </View>
        </Surface>

        <Text variant="titleMedium" style={styles.section}>Request Details</Text>
        <Card style={styles.card}>
          <Card.Content>
            <Text variant="bodyMedium" testID="custom-request-detail-text">
              {req.requestDetails}
            </Text>
          </Card.Content>
        </Card>

        {(req.status === "QUOTE_SENT" ||
          req.status === "ACCEPTED" ||
          req.status === "COMPLETED" ||
          req.status === "REJECTED_BY_BUYER") &&
          req.quoteAmount != null && (
            <>
              <Text variant="titleMedium" style={styles.section}>Quote</Text>
              <Card style={styles.card}>
                <Card.Content>
                  <View style={styles.row}>
                    <Text variant="titleMedium" style={{ fontWeight: "700" }}>Quote Amount</Text>
                    <Text
                      variant="headlineSmall"
                      style={{ fontWeight: "700" }}
                      testID="custom-request-quote-amount"
                    >
                      ₹{req.quoteAmount.toFixed(2)}
                    </Text>
                  </View>
                  {!!req.sellerMessage && (
                    <>
                      <Divider style={{ marginVertical: 12 }} />
                      <Text variant="labelMedium" style={{ color: theme.colors.onSurfaceVariant }}>
                        Seller Message
                      </Text>
                      <Text
                        variant="bodyMedium"
                        style={{ marginTop: 4 }}
                        testID="custom-request-seller-message"
                      >
                        {req.sellerMessage}
                      </Text>
                    </>
                  )}
                </Card.Content>
              </Card>
            </>
          )}

        {req.status === "REJECTED_BY_SELLER" && !!req.rejectionReason && (
          <>
            <Text variant="titleMedium" style={styles.section}>Rejection Reason</Text>
            <Card style={styles.card}>
              <Card.Content>
                <Text variant="bodyMedium" testID="custom-request-rejection-reason">
                  {req.rejectionReason}
                </Text>
              </Card.Content>
            </Card>
          </>
        )}

        {(canSend || canDelete || canAct) && (
          <View style={styles.actions}>
            {canAct && (
              <>
                <Button
                  mode="contained"
                  icon="check"
                  onPress={() => open("accept")}
                  contentStyle={{ height: 48 }}
                  style={styles.actBtn}
                  testID="accept-quote-btn"
                >
                  Accept Quote
                </Button>
                <Button
                  mode="outlined"
                  icon="close"
                  onPress={() => open("reject")}
                  contentStyle={{ height: 48 }}
                  style={styles.actBtn}
                  testID="reject-quote-btn"
                >
                  Reject Quote
                </Button>
              </>
            )}
            {canSend && (
              <Button
                mode="contained"
                icon="send"
                onPress={() => open("send")}
                contentStyle={{ height: 48 }}
                style={styles.actBtn}
                testID="send-saved-request-btn"
              >
                Send Request
              </Button>
            )}
            {canDelete && (
              <Button
                mode="outlined"
                icon="trash-can-outline"
                onPress={() => open("delete")}
                contentStyle={{ height: 48 }}
                style={styles.actBtn}
                testID="delete-request-btn"
              >
                Delete
              </Button>
            )}
          </View>
        )}
      </ScrollView>

      <Portal>
        <Dialog visible={pending !== null} onDismiss={close}>
          <Dialog.Title>
            {pending === "send" && "Send request?"}
            {pending === "delete" && "Delete this request?"}
            {pending === "accept" && "Accept this quote?"}
            {pending === "reject" && "Reject this quote?"}
          </Dialog.Title>
          <Dialog.Content>
            {pending === "send" && <Text>The seller will be notified.</Text>}
            {pending === "delete" && (
              <Text>This saved draft will be permanently removed.</Text>
            )}
            {pending === "accept" && (
              <Text>The seller will be notified of your acceptance.</Text>
            )}
            {pending === "reject" && (
              <Text>The seller will be notified that you rejected the quote.</Text>
            )}
          </Dialog.Content>
          <Dialog.Actions>
            <Button onPress={close} disabled={busy} testID="dialog-cancel-btn">Cancel</Button>
            <Button
              onPress={confirm}
              loading={busy}
              disabled={busy}
              mode="contained"
              testID="dialog-confirm-btn"
            >
              Confirm
            </Button>
          </Dialog.Actions>
        </Dialog>
      </Portal>

      <Snackbar visible={!!snack} onDismiss={() => setSnack("")} duration={2500}>
        {snack}
      </Snackbar>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  center: { flex: 1, alignItems: "center", justifyContent: "center" },
  body: { padding: 16, paddingBottom: 32 },
  hero: { padding: 20, borderRadius: 20 },
  section: { marginTop: 24, marginBottom: 12 },
  card: { borderRadius: 16 },
  row: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  actions: { marginTop: 24, gap: 12 },
  actBtn: { borderRadius: 14 },
});
