import { router } from "expo-router";
import { useEffect, useState } from "react";
import { ScrollView, StyleSheet, View } from "react-native";
import { Appbar, Button, Card, Divider, HelperText, List, Snackbar, Text, TextInput, useTheme } from "react-native-paper";
import { SafeAreaView } from "react-native-safe-area-context";

import { api } from "@/src/lib/api";
import { useAuth } from "@/src/lib/auth-context";

export function ProfileScreen() {
  const theme = useTheme();
  const { user, refresh, signOut } = useAuth();
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [address, setAddress] = useState("");
  const [businessName, setBusinessName] = useState("");
  const [saving, setSaving] = useState(false);
  const [snack, setSnack] = useState("");

  useEffect(() => {
    if (!user) return;
    setFirstName(user.firstName);
    setLastName(user.lastName);
    setAddress(user.address);
    setBusinessName(user.businessName || "");
  }, [user]);

  if (!user) return null;

  const save = async () => {
    setSaving(true);
    try {
      const payload: any = {
        firstName,
        lastName,
        address,
      };
      if (user.userType === "seller") payload.businessName = businessName;
      await api.updateProfile(payload);
      await refresh();
      setSnack("Profile updated");
    } catch (e: any) {
      setSnack(e?.message || "Failed to update");
    } finally {
      setSaving(false);
    }
  };

  const onLogout = async () => {
    await signOut();
    router.replace("/");
  };

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: theme.colors.background }} edges={["top"]}>
      <Appbar.Header mode="small" elevated>
        <Appbar.Content title="Profile" />
        <Appbar.Action icon="logout" onPress={onLogout} testID="logout-btn" />
      </Appbar.Header>
      <ScrollView contentContainerStyle={styles.body} keyboardShouldPersistTaps="handled">
        <Card style={styles.card}>
          <Card.Content>
            <Text variant="labelMedium" style={{ color: theme.colors.onSurfaceVariant }}>Account</Text>
            <Text variant="titleMedium" style={{ marginTop: 4 }}>{user.userType === "seller" ? "Seller" : "Buyer"}</Text>
            <View style={{ height: 12 }} />
            <Text variant="labelMedium" style={{ color: theme.colors.onSurfaceVariant }}>Mobile</Text>
            <Text variant="titleMedium" style={{ marginTop: 4 }} testID="profile-mobile">+{user.mobileNumber}</Text>
            <HelperText type="info" visible>
              Changing your mobile number requires OTP verification (available in next phase).
            </HelperText>
            {user.userType === "seller" && (
              <>
                <Text variant="labelMedium" style={{ color: theme.colors.onSurfaceVariant }}>Seller Code</Text>
                <Text variant="titleMedium" style={{ marginTop: 4 }} testID="profile-seller-code">{user.sellerCode}</Text>
              </>
            )}
          </Card.Content>
        </Card>

        <TextInput label="First Name" value={firstName} onChangeText={setFirstName} mode="outlined" style={styles.input} testID="profile-firstname-input" />
        <TextInput label="Last Name" value={lastName} onChangeText={setLastName} mode="outlined" style={styles.input} testID="profile-lastname-input" />
        <TextInput label="Address" value={address} onChangeText={setAddress} mode="outlined" multiline numberOfLines={2} style={styles.input} testID="profile-address-input" />
        {user.userType === "seller" && (
          <TextInput label="Business Name" value={businessName} onChangeText={setBusinessName} mode="outlined" style={styles.input} testID="profile-businessname-input" />
        )}
        <TextInput label="Pincode" value={user.pincode} mode="outlined" disabled style={styles.input} />

        <Button mode="contained" onPress={save} loading={saving} disabled={saving} contentStyle={{ height: 52 }} style={{ borderRadius: 16, marginTop: 8 }} testID="save-profile-btn">
          Save Changes
        </Button>

        <Card style={[styles.card, { marginTop: 16 }]}>
          <List.Item
            title="Settings"
            description="Theme, About, Privacy Policy"
            left={(p) => <List.Icon {...p} icon="cog-outline" />}
            right={(p) => <List.Icon {...p} icon="chevron-right" />}
            onPress={() => router.push("/settings" as any)}
            testID="open-settings-btn"
          />
          <Divider />
          <List.Item
            title="Notifications"
            description="View order updates & alerts"
            left={(p) => <List.Icon {...p} icon="bell-outline" />}
            right={(p) => <List.Icon {...p} icon="chevron-right" />}
            onPress={() => router.push("/notifications" as any)}
            testID="open-notifications-btn"
          />
        </Card>
      </ScrollView>
      <Snackbar visible={!!snack} onDismiss={() => setSnack("")} duration={2500}>
        {snack}
      </Snackbar>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  body: { padding: 16, paddingBottom: 32 },
  card: { borderRadius: 16, marginBottom: 16 },
  input: { marginTop: 8 },
});
