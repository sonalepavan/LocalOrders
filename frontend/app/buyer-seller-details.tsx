import { router, useLocalSearchParams } from "expo-router";
import { useMemo, useState } from "react";
import { ScrollView, StyleSheet, View } from "react-native";
import { Appbar, Button, Card, Chip, Divider, Snackbar, Text, useTheme } from "react-native-paper";
import { SafeAreaView } from "react-native-safe-area-context";

import { SellerSearchResult, api } from "@/src/lib/api";

export default function BuyerSellerDetails() {
  const theme = useTheme();
  const params = useLocalSearchParams<{ seller?: string }>();
  const [snack, setSnack] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [connStatus, setConnStatus] = useState<"Pending" | "Accepted" | null>(null);

  const seller = useMemo<SellerSearchResult | null>(() => {
    try {
      const parsed = params.seller ? (JSON.parse(params.seller as string) as SellerSearchResult) : null;
      if (parsed) setConnStatus(parsed.connectionStatus);
      return parsed;
    } catch {
      return null;
    }
  }, [params.seller]);

  if (!seller) {
    return (
      <SafeAreaView style={{ flex: 1, backgroundColor: theme.colors.background }} edges={["top", "bottom"]}>
        <Appbar.Header mode="small" elevated>
          <Appbar.BackAction onPress={() => router.back()} testID="back-btn" />
          <Appbar.Content title="Seller" />
        </Appbar.Header>
        <View style={styles.empty}>
          <Text variant="titleMedium">Seller not available</Text>
        </View>
      </SafeAreaView>
    );
  }

  const onSend = async () => {
    if (!seller.sellerCode) {
      setSnack("Seller code missing");
      return;
    }
    setSubmitting(true);
    try {
      const { connection } = await api.requestConnection(seller.sellerCode);
      setConnStatus(connection.status === "Accepted" ? "Accepted" : "Pending");
      setSnack(`Request sent to ${seller.businessName || "seller"}. Awaiting approval.`);
    } catch (e: any) {
      const msg = e?.message || "Failed to send request";
      // Backend returns 409 "Connection already exists (status: Pending|Accepted)"
      const m = /status:\s*(Pending|Accepted)/i.exec(msg);
      if (m) setConnStatus(m[1] as "Pending" | "Accepted");
      setSnack(msg);
    } finally {
      setSubmitting(false);
    }
  };

  const isPending = connStatus === "Pending";
  const isAccepted = connStatus === "Accepted";
  const ctaDisabled = submitting || isPending || isAccepted;
  let ctaLabel = "Send Connection Request";
  if (isPending) ctaLabel = "Request Pending";
  else if (isAccepted) ctaLabel = "Already Connected";

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: theme.colors.background }} edges={["top", "bottom"]}>
      <Appbar.Header mode="small" elevated>
        <Appbar.BackAction onPress={() => router.back()} testID="back-btn" />
        <Appbar.Content title="Seller Details" />
      </Appbar.Header>

      <ScrollView contentContainerStyle={styles.body}>
        <Card style={styles.card}>
          <Card.Content>
            <Text variant="headlineSmall" style={{ fontWeight: "700" }} testID="detail-business-name">
              {seller.businessName || `${seller.firstName} ${seller.lastName}`}
            </Text>
            <View style={styles.row}>
              {seller.sellerCode ? (
                <Chip compact style={styles.chip} icon="barcode" testID="detail-seller-code">
                  {seller.sellerCode}
                </Chip>
              ) : null}
              {seller.availabilityStatus ? (
                <Chip
                  compact
                  style={styles.chip}
                  icon={seller.availabilityStatus === "Open" ? "door-open" : "door-closed"}
                  testID="detail-availability"
                >
                  {seller.availabilityStatus}
                </Chip>
              ) : null}
              {connStatus ? (
                <Chip
                  compact
                  style={styles.chip}
                  icon={isAccepted ? "check-circle" : "clock-outline"}
                  testID="detail-connection-status"
                >
                  {isAccepted ? "Connected" : "Pending"}
                </Chip>
              ) : null}
            </View>

            <Divider style={styles.divider} />

            <Text variant="labelLarge" style={{ color: theme.colors.onSurfaceVariant }}>
              Owner
            </Text>
            <Text variant="bodyLarge" testID="detail-owner-name" style={styles.value}>
              {`${seller.firstName} ${seller.lastName}`.trim() || "—"}
            </Text>

            <Text variant="labelLarge" style={{ color: theme.colors.onSurfaceVariant, marginTop: 12 }}>
              Address
            </Text>
            <Text variant="bodyLarge" testID="detail-full-address" style={styles.value}>
              {seller.address || "—"}
            </Text>

            <Text variant="labelLarge" style={{ color: theme.colors.onSurfaceVariant, marginTop: 12 }}>
              Pincode
            </Text>
            <Text variant="bodyLarge" testID="detail-pincode" style={styles.value}>
              {seller.pincode || "—"}
            </Text>

            {seller.mobileNumber ? (
              <>
                <Text variant="labelLarge" style={{ color: theme.colors.onSurfaceVariant, marginTop: 12 }}>
                  Mobile
                </Text>
                <Text variant="bodyLarge" testID="detail-mobile" style={styles.value}>
                  {seller.mobileNumber}
                </Text>
              </>
            ) : null}
          </Card.Content>
        </Card>

        <Button
          mode="contained"
          icon={isAccepted ? "check" : isPending ? "clock-outline" : "send"}
          onPress={onSend}
          loading={submitting}
          disabled={ctaDisabled}
          contentStyle={{ height: 52 }}
          style={{ borderRadius: 16, marginTop: 16 }}
          testID="send-request-btn"
        >
          {ctaLabel}
        </Button>

        {(isPending || isAccepted) && (
          <Text
            variant="bodySmall"
            style={{ color: theme.colors.onSurfaceVariant, textAlign: "center", marginTop: 8 }}
            testID="connection-helper-text"
          >
            {isAccepted
              ? "You are already connected with this seller."
              : "Your connection request is awaiting the seller's approval."}
          </Text>
        )}
      </ScrollView>

      <Snackbar visible={!!snack} onDismiss={() => setSnack("")} duration={2500}>
        {snack}
      </Snackbar>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  body: { padding: 16 },
  card: { borderRadius: 16 },
  row: { flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: 12 },
  chip: {},
  divider: { marginVertical: 16 },
  value: { marginTop: 4 },
  empty: { flex: 1, alignItems: "center", justifyContent: "center" },
});
