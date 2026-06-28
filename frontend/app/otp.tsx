import { router, useLocalSearchParams } from "expo-router";
import { useState } from "react";
import { StyleSheet, View } from "react-native";
import { Appbar, Banner, Button, HelperText, Snackbar, Text, TextInput, useTheme } from "react-native-paper";
import { SafeAreaView } from "react-native-safe-area-context";

import { api } from "@/src/lib/api";
import { useAuth } from "@/src/lib/auth-context";

export default function OtpScreen() {
  const theme = useTheme();
  const params = useLocalSearchParams<{
    userType: "buyer" | "seller";
    firstName: string;
    lastName: string;
    mobileNumber: string;
    address: string;
    pincode: string;
    businessName?: string;
    pin: string;
    confirmPin: string;
  }>();
  const { setSession } = useAuth();
  const [otp, setOtp] = useState("");
  const [err, setErr] = useState("");
  const [snack, setSnack] = useState("");
  const [loading, setLoading] = useState(false);

  const verify = async () => {
    if (!/^\d{6}$/.test(otp)) {
      setErr("Enter the 6-digit OTP");
      return;
    }
    setErr("");
    setLoading(true);
    try {
      const payload = {
        firstName: params.firstName,
        lastName: params.lastName,
        mobileNumber: params.mobileNumber,
        address: params.address,
        pincode: params.pincode,
        pin: params.pin,
        confirmPin: params.confirmPin,
        otp,
        ...(params.userType === "seller" ? { businessName: params.businessName || "" } : {}),
      };
      const res =
        params.userType === "seller"
          ? await api.registerSeller(payload)
          : await api.registerBuyer(payload);
      await setSession(res.token, res.user);
      if (res.user.userType === "seller") router.replace("/(seller)/dashboard");
      else router.replace("/(buyer)/home");
    } catch (e: any) {
      setSnack(e?.message || "Verification failed");
    } finally {
      setLoading(false);
    }
  };

  const resend = async () => {
    try {
      await api.sendOtp(params.mobileNumber, params.userType);
      setSnack("OTP resent (mock: 123456)");
    } catch (e: any) {
      setSnack(e?.message || "Failed to resend OTP");
    }
  };

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: theme.colors.background }} edges={["top", "bottom"]}>
      <Appbar.Header mode="small" elevated>
        <Appbar.BackAction onPress={() => router.back()} testID="back-btn" />
        <Appbar.Content title="Verify Mobile" />
      </Appbar.Header>
      <View style={styles.body}>
        <Banner visible icon="information" actions={[]}>
          Mock OTP for Phase 1: enter <Text style={{ fontWeight: "700" }}>123456</Text>
        </Banner>
        <Text variant="bodyMedium" style={{ color: theme.colors.onSurfaceVariant, marginTop: 16 }}>
          We sent a verification code to +{params.mobileNumber}.
        </Text>
        <TextInput
          label="6-digit OTP"
          value={otp}
          onChangeText={(t) => setOtp(t.replace(/[^0-9]/g, "").slice(0, 6))}
          mode="outlined"
          keyboardType="number-pad"
          maxLength={6}
          style={{ marginTop: 16 }}
          testID="otp-input"
        />
        <HelperText type="error" visible={!!err}>{err}</HelperText>

        <Button
          mode="contained"
          onPress={verify}
          loading={loading}
          disabled={loading}
          contentStyle={{ height: 52 }}
          style={{ borderRadius: 16, marginTop: 8 }}
          testID="verify-otp-btn"
        >
          Verify & Create Account
        </Button>
        <Button mode="text" onPress={resend} style={{ marginTop: 8 }} testID="resend-otp-btn">
          Resend OTP
        </Button>
      </View>
      <Snackbar visible={!!snack} onDismiss={() => setSnack("")} duration={3500}>
        {snack}
      </Snackbar>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  body: { padding: 16 },
});
