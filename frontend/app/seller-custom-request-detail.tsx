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
  TextInput,
  useTheme,
} from "react-native-paper";
import { SafeAreaView } from "react-native-safe-area-context";

import { BuyerSummary, CustomRequest, CustomRequestStatus, api } from "@/src/lib/api";

type Action = "quote" | "accept" | "reject" | "complete" | null;

const STATUS_COLOR: Record<CustomRequestStatus, { bg: string; fg: string; label: string }> = {
  SAVED: { bg: "#F3F4F6", fg: "#52525B", label: "Saved" },
  NEW_REQUEST: { bg: "#FFF3E0", fg: "#A65B00", label: "New" },
  QUOTE_SENT: { bg: "#DBEAFE", fg: "#1A5276", label: "Quote sent" },
  ACCEPTED: { bg: "#E8F5E9", fg: "#1B5E20", label: "Accepted" },
  COMPLETED: { bg: "#DEF7EC", fg: "#03543F", label: "Completed" },
  REJECTED_BY_BUYER: { bg: "#FDECEA", fg: "#8C1D18", label: "Rejected by buyer" },
  REJECTED_BY_SELLER: { bg: "#FDECEA", fg: "#8C1D18", label: "Rejected by you" },
};

const SELLER_MESSAGE_MAX = 500;
const REJECTION_REASON_MAX = 500;

export default function SellerCustomRequestDetail() {
  const theme = useTheme();
  const { requestId } = useLocalSearchParams<{ requestId: string }>();
  const [req, setReq] = useState<CustomRequest | null>(null);
  const [buyer, setBuyer] = useState<BuyerSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [snack, setSnack] = useState("");
  const [pending, setPending] = useState<Action>(null);
  const [quoteAmount, setQuoteAmount] = useState("");
  const [sellerMessage, setSellerMessage] = useState("");
  const [rejectionReason, setRejectionReason] = useState("");
  const [amountErr, setAmountErr] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.getCustomRequest(requestId);
      setReq(res.request);
      setBuyer(res.counterparty as BuyerSummary | null);
    } catch (e: any) {
      setSnack(e?.message || "Failed to load");
    } finally {
      setLoading(false);
    }
  }, [requestId]);

  useEffect(() => { load(); }, [load]);

  const open = (a: Action) => {
    setPending(a);
    setQuoteAmount("");
    setSellerMessage("");
    setRejectionReason("");
    setAmountErr("");
  };
  const close = () => { if (!busy) setPending(null); };

  const confirm = async () => {
    if (!pending || !req) return;
    if (pending === "quote") {
      const n = Number(quoteAmount);
      if (!Number.isFinite(n) || n <= 0) {
        setAmountErr("Enter a quote amount greater than 0");
        return;
      }
    }
    setBusy(true);
    try {
      if (pending === "quote") {
        await api.sellerSendQuote(req.requestId, Number(quoteAmount), sellerMessage || undefined);
        setSnack("Quote sent");
      } else if (pending === "accept") {
        await api.sellerAcceptCustomRequest(req.requestId);
        setSnack("Request accepted");
      } else if (pending === "reject") {
        await api.sellerRejectCustomRequest(req.requestId, rejectionReason || undefined);
        setSnack("Request rejected");
      } else if (pending === "complete") {
        await api.sellerCompleteCustomRequest(req.requestId);
        setSnack("Request marked as completed");
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
  const buyerName = buyer ? `${buyer.firstName} ${buyer.lastName}` : "Buyer";
  const canAct = req.status === "NEW_REQUEST";
  const canComplete = req.status === "ACCEPTED";

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: theme.colors.background }} edges={["top"]}>
      <Appbar.Header mode="small" elevated>
        <Appbar.BackAction onPress={() => router.back()} testID="back-btn" />
        <Appbar.Content title="Custom Request" />
      </Appbar.Header>
      <ScrollView contentContainerStyle={styles.body}>
        <Surface elevation={2} style={[styles.hero, { backgroundColor: theme.colors.primaryContainer }]}>
          <View style={styles.row}>
            <View style={{ flex: 1 }}>
              <Text variant="labelLarge" style={{ color: theme.colors.onPrimaryContainer }}>Buyer</Text>
              <Text
                variant="headlineSmall"
                testID="seller-detail-buyer-name"
                style={{ color: theme.colors.onPrimaryContainer, fontWeight: "700", marginTop: 4 }}
              >
                {buyerName}
              </Text>
            </View>
            <Chip
              compact
              style={{ backgroundColor: sc.bg }}
              textStyle={{ color: sc.fg, fontWeight: "700" }}
              testID="seller-detail-status"
            >
              {sc.label}
            </Chip>
          </View>
        </Surface>

        <Text variant="titleMedium" style={styles.section}>Request Details</Text>
        <Card style={styles.card}>
          <Card.Content>
            <Text variant="bodyMedium" testID="seller-detail-text">
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
              <Text variant="titleMedium" style={styles.section}>Your Quote</Text>
              <Card style={styles.card}>
                <Card.Content>
                  <View style={styles.row}>
                    <Text variant="titleMedium" style={{ fontWeight: "700" }}>Quote Amount</Text>
                    <Text
                      variant="headlineSmall"
                      style={{ fontWeight: "700" }}
                      testID="seller-detail-quote-amount"
                    >
                      ₹{req.quoteAmount.toFixed(2)}
                    </Text>
                  </View>
                  {!!req.sellerMessage && (
                    <>
                      <Divider style={{ marginVertical: 12 }} />
                      <Text variant="labelMedium" style={{ color: theme.colors.onSurfaceVariant }}>
                        Your Message
                      </Text>
                      <Text variant="bodyMedium" style={{ marginTop: 4 }}>
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
                <Text variant="bodyMedium">{req.rejectionReason}</Text>
              </Card.Content>
            </Card>
          </>
        )}

        {canAct && (
          <View style={styles.actions}>
            <Button
              mode="contained"
              icon="cash"
              onPress={() => open("quote")}
              contentStyle={{ height: 48 }}
              style={styles.actBtn}
              testID="send-quote-btn"
            >
              Send Quote
            </Button>
            <Button
              mode="contained-tonal"
              icon="check"
              onPress={() => open("accept")}
              contentStyle={{ height: 48 }}
              style={styles.actBtn}
              testID="accept-request-btn"
            >
              Accept Request
            </Button>
            <Button
              mode="outlined"
              icon="close"
              onPress={() => open("reject")}
              contentStyle={{ height: 48 }}
              style={styles.actBtn}
              testID="reject-request-btn"
            >
              Reject Request
            </Button>
          </View>
        )}

        {canComplete && (
          <View style={styles.actions}>
            <Button
              mode="contained"
              icon="check-decagram"
              onPress={() => open("complete")}
              contentStyle={{ height: 48 }}
              style={styles.actBtn}
              testID="mark-completed-btn"
            >
              Mark Completed
            </Button>
          </View>
        )}
      </ScrollView>

      <Portal>
        <Dialog visible={pending !== null} onDismiss={close}>
          <Dialog.Title>
            {pending === "quote" && "Send Quote"}
            {pending === "accept" && "Accept this request?"}
            {pending === "reject" && "Reject this request?"}
            {pending === "complete" && "Mark as completed?"}
          </Dialog.Title>
          <Dialog.Content>
            {pending === "quote" && (
              <>
                <TextInput
                  label="Quote Amount (₹)"
                  value={quoteAmount}
                  onChangeText={(t) => {
                    setQuoteAmount(t);
                    if (amountErr) setAmountErr("");
                  }}
                  mode="outlined"
                  keyboardType="decimal-pad"
                  error={!!amountErr}
                  style={{ marginBottom: 8 }}
                  testID="quote-amount-input"
                />
                {!!amountErr && (
                  <Text style={{ color: theme.colors.error, marginBottom: 8 }}>{amountErr}</Text>
                )}
                <TextInput
                  label="Message (optional)"
                  value={sellerMessage}
                  onChangeText={setSellerMessage}
                  mode="outlined"
                  multiline
                  numberOfLines={3}
                  maxLength={SELLER_MESSAGE_MAX}
                  testID="seller-message-input"
                />
              </>
            )}
            {pending === "accept" && (
              <Text>The buyer will be notified that you accepted their request.</Text>
            )}
            {pending === "complete" && (
              <Text>The buyer will be notified that this request is completed.</Text>
            )}
            {pending === "reject" && (
              <TextInput
                label="Reason (optional)"
                value={rejectionReason}
                onChangeText={setRejectionReason}
                mode="outlined"
                multiline
                numberOfLines={3}
                maxLength={REJECTION_REASON_MAX}
                testID="rejection-reason-input"
              />
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
