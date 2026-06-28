import { MaterialCommunityIcons } from "@expo/vector-icons";
import { router } from "expo-router";
import { ScrollView, StyleSheet, View } from "react-native";
import { Appbar, Card, Surface, Text, useTheme } from "react-native-paper";
import { SafeAreaView } from "react-native-safe-area-context";

export default function AboutScreen() {
  const theme = useTheme();
  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: theme.colors.background }} edges={["top"]}>
      <Appbar.Header mode="small" elevated>
        <Appbar.BackAction onPress={() => router.back()} testID="about-back-btn" />
        <Appbar.Content title="About LocalOrders" />
      </Appbar.Header>
      <ScrollView contentContainerStyle={styles.body}>
        <Surface elevation={2} style={[styles.hero, { backgroundColor: theme.colors.primary }]}>
          <View style={[styles.logoWrap, { backgroundColor: theme.colors.onPrimary }]}>
            <Text variant="headlineMedium" style={{ color: theme.colors.primary, fontWeight: "800" }}>
              LO
            </Text>
          </View>
          <Text variant="headlineSmall" style={{ color: theme.colors.onPrimary, fontWeight: "700", marginTop: 12 }}>
            LocalOrders
          </Text>
          <Text variant="labelMedium" style={{ color: theme.colors.onPrimary, marginTop: 4, opacity: 0.85 }}>
            Buy and sell from local sellers around you
          </Text>
          <Text variant="labelSmall" style={{ color: theme.colors.onPrimary, marginTop: 12, opacity: 0.7 }}>
            Version 1.0.0
          </Text>
        </Surface>

        <Card style={styles.card}>
          <Card.Content>
            <Text variant="titleMedium" style={{ fontWeight: "700" }}>What is LocalOrders?</Text>
            <Text variant="bodyMedium" style={{ marginTop: 8, color: theme.colors.onSurfaceVariant }}>
              LocalOrders connects neighborhood buyers with local sellers — your kirana store, dairy,
              vegetable vendor or any small business — so you can browse their inventory, place orders
              and track delivery without endless phone calls.
            </Text>
          </Card.Content>
        </Card>

        <Card style={styles.card}>
          <Card.Content>
            <Text variant="titleMedium" style={{ fontWeight: "700" }}>Highlights</Text>
            <Feature theme={theme} icon="storefront-outline" title="Connect by code" desc="Use a seller's unique SELLER-#### code to add them." />
            <Feature theme={theme} icon="package-variant" title="Live inventory" desc="See real-time stock with low-inventory alerts." />
            <Feature theme={theme} icon="cart-outline" title="Easy ordering" desc="Build a cart, place an order, and track its status." />
            <Feature theme={theme} icon="bell-ring-outline" title="Notifications" desc="Get notified on order updates and connection requests." />
            <Feature theme={theme} icon="cloud-off-outline" title="Works offline" desc="Browse your inventory and orders even without a connection." />
          </Card.Content>
        </Card>

        <Card style={styles.card}>
          <Card.Content>
            <Text variant="titleMedium" style={{ fontWeight: "700" }}>Credits</Text>
            <Text variant="bodySmall" style={{ marginTop: 6, color: theme.colors.onSurfaceVariant }}>
              Built with Expo (React Native), FastAPI, MongoDB and React Native Paper. Icons by
              MaterialCommunityIcons.
            </Text>
          </Card.Content>
        </Card>

        <View style={{ alignItems: "center", marginTop: 16 }}>
          <Text variant="labelSmall" style={{ color: theme.colors.onSurfaceVariant }}>
            © 2026 LocalOrders. All rights reserved.
          </Text>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

function Feature({ theme, icon, title, desc }: { theme: any; icon: string; title: string; desc: string }) {
  return (
    <View style={{ flexDirection: "row", marginTop: 14, alignItems: "flex-start" }}>
      <View
        style={{
          width: 36,
          height: 36,
          borderRadius: 18,
          backgroundColor: theme.colors.primaryContainer,
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <MaterialCommunityIcons name={icon as any} size={20} color={theme.colors.onPrimaryContainer} />
      </View>
      <View style={{ flex: 1, marginLeft: 12 }}>
        <Text variant="titleSmall" style={{ fontWeight: "600" }}>{title}</Text>
        <Text variant="bodySmall" style={{ marginTop: 2, color: theme.colors.onSurfaceVariant }}>{desc}</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  body: { padding: 16, paddingBottom: 48 },
  hero: { borderRadius: 20, padding: 24, alignItems: "center" },
  logoWrap: {
    width: 64,
    height: 64,
    borderRadius: 16,
    alignItems: "center",
    justifyContent: "center",
  },
  card: { borderRadius: 16, marginTop: 16 },
});
