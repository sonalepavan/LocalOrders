import { router } from "expo-router";
import { useState } from "react";
import { StyleSheet, View } from "react-native";
import { Appbar, Button, HelperText, Snackbar, Text, TextInput, useTheme } from "react-native-paper";
import { SafeAreaView } from "react-native-safe-area-context";

import { api } from "@/src/lib/api";
import { useAuth } from "@/src/lib/auth-context";

export default function LoginScreen() {
  const theme = useTheme();
  const { setSession } = useAuth();
  const [mobile, setMobile] = useState("");
  const [pin, setPin] = useState("");
  const [errMobile, setErrMobile] = useState("");
  const [errPin, setErrPin] = useState("");
  const [snack, setSnack] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async () => {
    let ok = true;
    if (!/^\d{10,15}$/.test(mobile.trim())) {
      setErrMobile("Enter a valid mobile number");
      ok = false;
    } else setErrMobile("");
    if (!/^\d{4}$/.test(pin)) {
      setErrPin("Enter your 4-digit PIN");
      ok = false;
    } else setErrPin("");
    if (!ok) return;

    setLoading(true);
    try {
      const res = await api.login(mobile.trim(), pin);
      await setSession(res.token, res.user);
      if (res.user.userType === "seller") router.replace("/(seller)/dashboard");
      else router.replace("/(buyer)/home");
    } catch (e: any) {
      setSnack(e?.message || "Login failed");
      setPin("");
    } finally {
      setLoading(false);
    }
  };

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: theme.colors.background }} edges={["top", "bottom"]}>
      <Appbar.Header mode="small" elevated>
        <Appbar.BackAction onPress={() => router.back()} testID="back-btn" />
        <Appbar.Content title="Login" />
      </Appbar.Header>
      <View style={styles.body}>
        <Text variant="headlineSmall" style={{ marginBottom: 4 }}>Welcome back</Text>
        <Text variant="bodyMedium" style={{ color: theme.colors.onSurfaceVariant, marginBottom: 16 }}>
          Login with your mobile number and 4-digit PIN.
        </Text>
        <TextInput
          label="Mobile Number"
          value={mobile}
          onChangeText={(t) => setMobile(t.replace(/[^0-9]/g, ""))}
          mode="outlined"
          keyboardType="phone-pad"
          left={<TextInput.Icon icon="phone" />}
          testID="login-mobile-input"
        />
        <HelperText type="error" visible={!!errMobile}>{errMobile}</HelperText>
        <TextInput
          label="4-Digit PIN"
          value={pin}
          onChangeText={(t) => setPin(t.replace(/[^0-9]/g, "").slice(0, 4))}
          mode="outlined"
          secureTextEntry
          keyboardType="number-pad"
          maxLength={4}
          left={<TextInput.Icon icon="lock" />}
          testID="login-pin-input"
        />
        <HelperText type="error" visible={!!errPin}>{errPin}</HelperText>

        <Button
          mode="contained"
          onPress={submit}
          loading={loading}
          disabled={loading}
          contentStyle={{ height: 52 }}
          style={{ borderRadius: 16, marginTop: 8 }}
          testID="login-submit-btn"
        >
          Login
        </Button>
      </View>
      <Snackbar visible={!!snack} onDismiss={() => setSnack("")} duration={4500}>
        {snack}
      </Snackbar>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  body: { padding: 16 },
});
