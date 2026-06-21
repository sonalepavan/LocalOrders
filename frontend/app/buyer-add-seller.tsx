import { router } from "expo-router";
import { useState } from "react";
import { StyleSheet, View } from "react-native";
import { Appbar, Button, HelperText, Snackbar, Text, TextInput, useTheme } from "react-native-paper";
import { SafeAreaView } from "react-native-safe-area-context";

import { api } from "@/src/lib/api";

export default function BuyerAddSeller() {
  const theme = useTheme();
  const [code, setCode] = useState("");
  const [err, setErr] = useState("");
  const [snack, setSnack] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async () => {
    const c = code.trim().toUpperCase();
    if (!/^SELLER-\d+$/.test(c)) {
      setErr("Format: SELLER-1001");
      return;
    }
    setErr("");
    setLoading(true);
    try {
      const { connection } = await api.requestConnection(c);
      setSnack(`Request sent to ${connection.seller?.businessName || "seller"}. Awaiting approval.`);
      setCode("");
      setTimeout(() => router.back(), 1200);
    } catch (e: any) {
      setSnack(e?.message || "Failed to send request");
    } finally {
      setLoading(false);
    }
  };

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: theme.colors.background }} edges={["top", "bottom"]}>
      <Appbar.Header mode="small" elevated>
        <Appbar.BackAction onPress={() => router.back()} testID="back-btn" />
        <Appbar.Content title="Connect to Seller" />
      </Appbar.Header>
      <View style={styles.body}>
        <Text variant="bodyMedium" style={{ color: theme.colors.onSurfaceVariant, marginBottom: 16 }}>
          Enter the Seller Code shared by your local seller. The seller will get a request and can accept or reject.
        </Text>
        <TextInput
          label="Seller Code"
          value={code}
          onChangeText={(t) => setCode(t.toUpperCase())}
          mode="outlined"
          autoCapitalize="characters"
          placeholder="SELLER-1001"
          left={<TextInput.Icon icon="barcode" />}
          testID="seller-code-input"
        />
        <HelperText type="error" visible={!!err}>{err}</HelperText>
        <Button mode="contained" onPress={submit} loading={loading} disabled={loading} contentStyle={{ height: 52 }} style={{ borderRadius: 16, marginTop: 8 }} testID="send-request-btn">
          Send Connection Request
        </Button>
      </View>
      <Snackbar visible={!!snack} onDismiss={() => setSnack("")} duration={2500}>{snack}</Snackbar>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  body: { padding: 16 },
});
