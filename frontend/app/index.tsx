import { router } from "expo-router";
import { useEffect } from "react";
import { ActivityIndicator, StyleSheet, View } from "react-native";
import { Button, Surface, Text, useTheme } from "react-native-paper";
import { SafeAreaView } from "react-native-safe-area-context";

import { useAuth } from "@/src/lib/auth-context";

export default function HomeScreen() {
  const { user, loading } = useAuth();
  const theme = useTheme();

  useEffect(() => {
    if (loading) return;
    if (user) {
      if (user.userType === "seller") router.replace("/(seller)/dashboard");
      else router.replace("/(buyer)/home");
    }
  }, [user, loading]);

  if (loading || user) {
    return (
      <View testID="loading-screen" style={[styles.loading, { backgroundColor: theme.colors.background }]}>
        <ActivityIndicator size="large" />
      </View>
    );
  }

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: theme.colors.background }]} edges={["top", "bottom"]}>
      <View style={styles.brand}>
        <Surface elevation={2} style={[styles.logo, { backgroundColor: theme.colors.primaryContainer }]}>
          <Text variant="headlineLarge" style={{ color: theme.colors.onPrimaryContainer, fontWeight: "700" }}>
            LO
          </Text>
        </Surface>
        <Text variant="displaySmall" style={styles.title}>
          LocalOrders
        </Text>
        <Text variant="bodyLarge" style={{ color: theme.colors.onSurfaceVariant, textAlign: "center", marginTop: 8 }}>
          Buy and sell from local sellers around you
        </Text>
      </View>

      <View style={styles.actions}>
        <Button
          mode="contained"
          icon="account-plus"
          testID="register-buyer-btn"
          contentStyle={styles.btnContent}
          style={styles.btn}
          onPress={() => router.push("/register-buyer")}
        >
          Register as Buyer
        </Button>
        <Button
          mode="contained-tonal"
          icon="storefront"
          testID="register-seller-btn"
          contentStyle={styles.btnContent}
          style={styles.btn}
          onPress={() => router.push("/register-seller")}
        >
          Register as Seller
        </Button>
        <Button
          mode="outlined"
          icon="login"
          testID="login-btn"
          contentStyle={styles.btnContent}
          style={styles.btn}
          onPress={() => router.push("/login")}
        >
          Login
        </Button>
      </View>

      <Text variant="bodySmall" style={{ textAlign: "center", color: theme.colors.onSurfaceVariant }}>
        Phase 1 build · OTP is mocked (use 123456)
      </Text>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  loading: { flex: 1, alignItems: "center", justifyContent: "center" },
  container: { flex: 1, padding: 24, justifyContent: "space-between" },
  brand: { alignItems: "center", marginTop: 32 },
  logo: { width: 88, height: 88, borderRadius: 24, alignItems: "center", justifyContent: "center" },
  title: { marginTop: 16, fontWeight: "700" },
  actions: { gap: 12 },
  btn: { borderRadius: 16 },
  btnContent: { height: 52 },
});
