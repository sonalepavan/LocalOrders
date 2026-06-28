import { router, useLocalSearchParams } from "expo-router";
import { useEffect, useState } from "react";
import { StyleSheet, View } from "react-native";
import {
  ActivityIndicator,
  Appbar,
  Button,
  Card,
  Snackbar,
  Text,
  TextInput,
  useTheme,
} from "react-native-paper";
import { SafeAreaView } from "react-native-safe-area-context";

import {
  CUSTOM_REQUEST_MAX_LEN,
  CUSTOM_REQUEST_MIN_LEN,
  api,
} from "@/src/lib/api";

/**
 * Compose / edit a custom request to a specific seller.
 * Params:
 *  - sellerId         (required for create mode)
 *  - sellerName       (display only)
 *  - requestId        (edit mode — loads existing draft)
 */
export default function BuyerCustomRequest() {
  const theme = useTheme();
  const { sellerId, sellerName, requestId } = useLocalSearchParams<{
    sellerId?: string;
    sellerName?: string;
    requestId?: string;
  }>();
  const isEdit = !!requestId;

  const [details, setDetails] = useState("");
  const [displayName, setDisplayName] = useState(sellerName || "");
  const [loadedSellerId, setLoadedSellerId] = useState<string | undefined>(sellerId);
  const [loading, setLoading] = useState(isEdit);
  const [saving, setSaving] = useState(false);
  const [sending, setSending] = useState(false);
  const [snack, setSnack] = useState("");
  const [err, setErr] = useState("");

  // Edit mode → fetch existing draft
  useEffect(() => {
    if (!isEdit) return;
    (async () => {
      try {
        const res = await api.getCustomRequest(requestId!);
        setDetails(res.request.requestDetails);
        setLoadedSellerId(res.request.sellerId);
        if (res.counterparty && "businessName" in res.counterparty) {
          setDisplayName(
            res.counterparty.businessName ||
              `${res.counterparty.firstName} ${res.counterparty.lastName}`,
          );
        }
        if (res.request.status !== "SAVED") {
          setSnack("This request has already been sent and cannot be edited");
        }
      } catch (e: any) {
        setSnack(e?.message || "Failed to load request");
      } finally {
        setLoading(false);
      }
    })();
  }, [isEdit, requestId]);

  const trimmedLen = details.trim().length;
  const valid =
    trimmedLen >= CUSTOM_REQUEST_MIN_LEN && trimmedLen <= CUSTOM_REQUEST_MAX_LEN;

  const validate = (): boolean => {
    if (trimmedLen === 0) {
      setErr("Request details are required");
      return false;
    }
    if (trimmedLen < CUSTOM_REQUEST_MIN_LEN || trimmedLen > CUSTOM_REQUEST_MAX_LEN) {
      setErr(
        `Request details must be ${CUSTOM_REQUEST_MIN_LEN}-${CUSTOM_REQUEST_MAX_LEN} characters`,
      );
      return false;
    }
    setErr("");
    return true;
  };

  const onSave = async () => {
    if (!validate()) return;
    setSaving(true);
    try {
      if (isEdit) {
        await api.updateCustomRequest(requestId!, details.trim());
        setSnack("Request saved");
        setTimeout(() => router.back(), 500);
      } else {
        if (!loadedSellerId) {
          setSnack("Missing seller");
          setSaving(false);
          return;
        }
        await api.createCustomRequest(loadedSellerId, details.trim(), false);
        setSnack("Request saved as draft");
        setTimeout(() => router.replace("/buyer-saved-requests"), 500);
      }
    } catch (e: any) {
      setSnack(e?.message || "Failed to save");
    } finally {
      setSaving(false);
    }
  };

  const onSend = async () => {
    if (!validate()) return;
    setSending(true);
    try {
      if (isEdit) {
        await api.updateCustomRequest(requestId!, details.trim());
        await api.sendCustomRequest(requestId!);
      } else {
        if (!loadedSellerId) {
          setSnack("Missing seller");
          setSending(false);
          return;
        }
        await api.createCustomRequest(loadedSellerId, details.trim(), true);
      }
      setSnack("Request sent to seller");
      setTimeout(() => router.replace("/buyer-saved-requests"), 500);
    } catch (e: any) {
      setSnack(e?.message || "Failed to send");
    } finally {
      setSending(false);
    }
  };

  if (loading) {
    return (
      <SafeAreaView style={{ flex: 1, backgroundColor: theme.colors.background }} edges={["top"]}>
        <Appbar.Header mode="small" elevated>
          <Appbar.BackAction onPress={() => router.back()} testID="back-btn" />
          <Appbar.Content title="Custom Request" />
        </Appbar.Header>
        <View style={styles.center}>
          <ActivityIndicator />
        </View>
      </SafeAreaView>
    );
  }

  const busy = saving || sending;

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: theme.colors.background }} edges={["top"]}>
      <Appbar.Header mode="small" elevated>
        <Appbar.BackAction onPress={() => router.back()} testID="back-btn" />
        <Appbar.Content title={isEdit ? "Edit Request" : "New Request"} />
      </Appbar.Header>
      <View style={styles.body}>
        <Card style={styles.card}>
          <Card.Content>
            <Text variant="labelMedium" style={{ color: theme.colors.onSurfaceVariant }}>
              Seller Name
            </Text>
            <Text
              variant="titleMedium"
              style={{ marginTop: 4, fontWeight: "700" }}
              testID="custom-request-seller-name"
            >
              {displayName || "Seller"}
            </Text>
          </Card.Content>
        </Card>

        <TextInput
          label="Request Details"
          placeholder={`Describe what you'd like to order (${CUSTOM_REQUEST_MIN_LEN}-${CUSTOM_REQUEST_MAX_LEN} characters)`}
          value={details}
          onChangeText={(t) => {
            setDetails(t);
            if (err) setErr("");
          }}
          mode="outlined"
          multiline
          numberOfLines={6}
          maxLength={CUSTOM_REQUEST_MAX_LEN}
          error={!!err}
          style={styles.input}
          testID="custom-request-details-input"
        />
        <View style={styles.metaRow}>
          {!!err ? (
            <Text variant="labelSmall" style={{ color: theme.colors.error }} testID="custom-request-error">
              {err}
            </Text>
          ) : (
            <Text variant="labelSmall" style={{ color: theme.colors.onSurfaceVariant }}>
              Min {CUSTOM_REQUEST_MIN_LEN} characters
            </Text>
          )}
          <Text
            variant="labelSmall"
            style={{ color: theme.colors.onSurfaceVariant }}
            testID="custom-request-counter"
          >
            {trimmedLen}/{CUSTOM_REQUEST_MAX_LEN}
          </Text>
        </View>

        <Button
          mode="outlined"
          icon="content-save-outline"
          onPress={onSave}
          loading={saving}
          disabled={busy || !valid}
          style={styles.btn}
          contentStyle={{ height: 48 }}
          testID="save-request-btn"
        >
          Save Request
        </Button>
        <Button
          mode="contained"
          icon="send"
          onPress={onSend}
          loading={sending}
          disabled={busy || !valid}
          style={styles.btn}
          contentStyle={{ height: 48 }}
          testID="send-request-btn"
        >
          Send Request
        </Button>
      </View>
      <Snackbar visible={!!snack} onDismiss={() => setSnack("")} duration={2500}>
        {snack}
      </Snackbar>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  center: { flex: 1, alignItems: "center", justifyContent: "center" },
  body: { padding: 16 },
  card: { borderRadius: 16, marginBottom: 16 },
  input: { backgroundColor: "transparent", minHeight: 140 },
  metaRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    marginTop: 4,
    marginBottom: 16,
  },
  btn: { borderRadius: 14, marginTop: 12 },
});
