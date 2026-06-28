import { MaterialCommunityIcons } from "@expo/vector-icons";
import { router } from "expo-router";
import { ScrollView, StyleSheet, View } from "react-native";
import { Appbar, Card, Divider, List, RadioButton, Text, useTheme } from "react-native-paper";
import { SafeAreaView } from "react-native-safe-area-context";

import { useAuth } from "@/src/lib/auth-context";
import { useThemePref } from "@/src/lib/theme-context";

export default function SettingsScreen() {
  const theme = useTheme();
  const { user } = useAuth();
  const { preference, setPreference } = useThemePref();

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: theme.colors.background }} edges={["top"]}>
      <Appbar.Header mode="small" elevated>
        <Appbar.BackAction onPress={() => router.back()} testID="settings-back-btn" />
        <Appbar.Content title="Settings" />
      </Appbar.Header>
      <ScrollView contentContainerStyle={styles.body}>
        <Text variant="labelLarge" style={[styles.sectionLabel, { color: theme.colors.onSurfaceVariant }]}>
          APPEARANCE
        </Text>
        <Card style={styles.card} mode="elevated">
          <RadioButton.Group onValueChange={(v) => setPreference(v as any)} value={preference}>
            <List.Item
              title="Light"
              left={(p) => <List.Icon {...p} icon="white-balance-sunny" />}
              right={() => <RadioButton value="light" testID="theme-light" />}
              onPress={() => setPreference("light")}
              testID="theme-light-row"
            />
            <Divider />
            <List.Item
              title="Dark"
              left={(p) => <List.Icon {...p} icon="weather-night" />}
              right={() => <RadioButton value="dark" testID="theme-dark" />}
              onPress={() => setPreference("dark")}
              testID="theme-dark-row"
            />
            <Divider />
            <List.Item
              title="Follow System"
              description="Match your device's theme"
              left={(p) => <List.Icon {...p} icon="theme-light-dark" />}
              right={() => <RadioButton value="system" testID="theme-system" />}
              onPress={() => setPreference("system")}
              testID="theme-system-row"
            />
          </RadioButton.Group>
        </Card>

        <Text variant="labelLarge" style={[styles.sectionLabel, { color: theme.colors.onSurfaceVariant, marginTop: 24 }]}>
          ABOUT
        </Text>
        <Card style={styles.card} mode="elevated">
          <List.Item
            title="About LocalOrders"
            description="App information & credits"
            left={(p) => <List.Icon {...p} icon="information-outline" />}
            right={(p) => <MaterialCommunityIcons {...p} name="chevron-right" size={20} />}
            onPress={() => router.push("/about" as any)}
            testID="about-row"
          />
          <Divider />
          <List.Item
            title="Privacy Policy"
            description="How we handle your data"
            left={(p) => <List.Icon {...p} icon="shield-lock-outline" />}
            right={(p) => <MaterialCommunityIcons {...p} name="chevron-right" size={20} />}
            onPress={() => router.push("/privacy-policy" as any)}
            testID="privacy-row"
          />
        </Card>

        {!!user && (
          <>
            <Text
              variant="labelLarge"
              style={[styles.sectionLabel, { color: theme.colors.onSurfaceVariant, marginTop: 24 }]}
            >
              ACCOUNT
            </Text>
            <Card style={styles.card} mode="elevated">
              <List.Item
                title={`${user.firstName} ${user.lastName}`}
                description={`+${user.mobileNumber} · ${user.userType === "seller" ? user.sellerCode ?? "Seller" : "Buyer"}`}
                left={(p) => <List.Icon {...p} icon="account-circle-outline" />}
              />
            </Card>
          </>
        )}

        <View style={{ alignItems: "center", marginTop: 32 }}>
          <Text variant="labelSmall" style={{ color: theme.colors.onSurfaceVariant }}>
            LocalOrders · v1.0.0
          </Text>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  body: { padding: 16, paddingBottom: 48 },
  sectionLabel: { marginLeft: 8, marginBottom: 8, letterSpacing: 0.6 },
  card: { borderRadius: 16, overflow: "hidden" },
});
