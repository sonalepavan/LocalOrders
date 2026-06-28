import { router } from "expo-router";
import { ScrollView, StyleSheet, View } from "react-native";
import { Appbar, Text, useTheme } from "react-native-paper";
import { SafeAreaView } from "react-native-safe-area-context";

export default function PrivacyPolicyScreen() {
  const theme = useTheme();
  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: theme.colors.background }} edges={["top"]}>
      <Appbar.Header mode="small" elevated>
        <Appbar.BackAction onPress={() => router.back()} testID="privacy-back-btn" />
        <Appbar.Content title="Privacy Policy" />
      </Appbar.Header>
      <ScrollView contentContainerStyle={styles.body}>
        <Text variant="labelMedium" style={{ color: theme.colors.onSurfaceVariant }}>
          Last updated: February 2026
        </Text>

        <Section title="1. Overview" body={
          "LocalOrders (\"we\", \"our\", \"the app\") respects your privacy. This policy explains what information we collect, how we use it, and the choices you have. By using LocalOrders you agree to the practices described here."
        } />
        <Section title="2. Information we collect" body={
          "We collect only the information needed to operate the app:\n\n• Account details — your name, mobile number, address and pincode (and, for sellers, your business name).\n• A bcrypt hash of your 4-digit PIN (we never store the PIN itself).\n• Inventory listings, connection requests, orders and notifications you create or receive.\n• Device push token, only if you enable push notifications, so we can deliver order updates."
        } />
        <Section title="3. How we use it" body={
          "Your data is used solely to provide the service:\n\n• Authenticate you and keep your account secure.\n• Connect you with sellers/buyers, show inventories and process orders.\n• Send you notifications about order updates and connection requests.\n• Maintain low-inventory and availability alerts."
        } />
        <Section title="4. What we never do" body={
          "We do NOT sell your personal information to third parties. We do not place tracking ads. We do not share your mobile number with strangers — only with the buyer/seller you have an accepted connection with."
        } />
        <Section title="5. Data retention" body={
          "Your account data is retained while your account is active. Soft-deleted inventory items remain associated with prior orders for historical accuracy. You can request full deletion of your account by contacting support."
        } />
        <Section title="6. Security" body={
          "Authentication uses bcrypt for PINs and signed JWTs for sessions. Tokens are stored on-device in the platform secure store. Transport is over HTTPS."
        } />
        <Section title="7. Children" body={
          "LocalOrders is intended for users 18 years or older. We do not knowingly collect data from minors."
        } />
        <Section title="8. Changes to this policy" body={
          "We may update this policy from time to time. We will notify you in-app when material changes are made."
        } />
        <Section title="9. Contact" body={
          "For questions about privacy or to request account deletion, email support@localorders.app."
        } />

        <View style={{ height: 24 }} />
      </ScrollView>
    </SafeAreaView>
  );
}

function Section({ title, body }: { title: string; body: string }) {
  return (
    <View style={{ marginTop: 22 }}>
      <Text variant="titleMedium" style={{ fontWeight: "700" }}>{title}</Text>
      <Text variant="bodyMedium" style={{ marginTop: 8, lineHeight: 22 }}>{body}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  body: { padding: 20, paddingBottom: 48 },
});
