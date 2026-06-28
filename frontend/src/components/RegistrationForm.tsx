import { router, Stack } from "expo-router";
import { useState } from "react";
import { Platform, ScrollView, StyleSheet, View } from "react-native";
import { Appbar, Button, HelperText, Snackbar, Text, TextInput, useTheme } from "react-native-paper";
import { SafeAreaView } from "react-native-safe-area-context";

import { api } from "@/src/lib/api";

type Errors = Partial<Record<"firstName" | "lastName" | "mobile" | "address" | "pincode" | "pin" | "confirmPin" | "businessName", string>>;

type Props = { userType: "buyer" | "seller" };

export function RegistrationForm({ userType }: Props) {
  const theme = useTheme();
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [mobile, setMobile] = useState("");
  const [address, setAddress] = useState("");
  const [pincode, setPincode] = useState("");
  const [businessName, setBusinessName] = useState("");
  const [pin, setPin] = useState("");
  const [confirmPin, setConfirmPin] = useState("");
  const [errors, setErrors] = useState<Errors>({});
  const [snack, setSnack] = useState<string>("");
  const [loading, setLoading] = useState(false);

  const validate = (): Errors => {
    const e: Errors = {};
    if (!firstName.trim()) e.firstName = "First name required";
    if (!lastName.trim()) e.lastName = "Last name required";
    if (!/^\d{10,15}$/.test(mobile.trim())) e.mobile = "Enter a valid mobile number";
    if (!address.trim()) e.address = "Address required";
    if (!/^\d{4,10}$/.test(pincode.trim())) e.pincode = "Enter a valid pincode";
    if (userType === "seller" && !businessName.trim()) e.businessName = "Business name required";
    if (!/^\d{4}$/.test(pin)) e.pin = "PIN must be 4 digits";
    if (pin !== confirmPin) e.confirmPin = "PINs do not match";
    return e;
  };

  const onContinue = async () => {
    const e = validate();
    setErrors(e);
    if (Object.keys(e).length) return;
    setLoading(true);
    try {
      await api.sendOtp(mobile.trim(), userType);
      router.push({
        pathname: "/otp",
        params: {
          userType,
          firstName: firstName.trim(),
          lastName: lastName.trim(),
          mobileNumber: mobile.trim(),
          address: address.trim(),
          pincode: pincode.trim(),
          businessName: businessName.trim(),
          pin,
          confirmPin,
        },
      });
    } catch (err: any) {
      setSnack(err?.message || "Failed to send OTP");
    } finally {
      setLoading(false);
    }
  };

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: theme.colors.background }} edges={["top", "bottom"]}>
      <Stack.Screen options={{ headerShown: false }} />
      <Appbar.Header mode="small" elevated>
        <Appbar.BackAction onPress={() => router.back()} testID="back-btn" />
        <Appbar.Content title={userType === "seller" ? "Register as Seller" : "Register as Buyer"} />
      </Appbar.Header>
      <ScrollView
        contentContainerStyle={styles.scroll}
        keyboardShouldPersistTaps="handled"
        keyboardDismissMode={Platform.OS === "ios" ? "interactive" : "on-drag"}
      >
        <Text variant="bodyMedium" style={{ color: theme.colors.onSurfaceVariant, marginBottom: 12 }}>
          Fill the details to create your account. We will verify your mobile number with an OTP.
        </Text>

        <View style={styles.row}>
          <View style={{ flex: 1 }}>
            <TextInput label="First Name" value={firstName} onChangeText={setFirstName} mode="outlined" testID="firstname-input" />
            <HelperText type="error" visible={!!errors.firstName}>{errors.firstName}</HelperText>
          </View>
          <View style={{ width: 12 }} />
          <View style={{ flex: 1 }}>
            <TextInput label="Last Name" value={lastName} onChangeText={setLastName} mode="outlined" testID="lastname-input" />
            <HelperText type="error" visible={!!errors.lastName}>{errors.lastName}</HelperText>
          </View>
        </View>

        <TextInput
          label="Mobile Number"
          value={mobile}
          onChangeText={(t) => setMobile(t.replace(/[^0-9]/g, ""))}
          mode="outlined"
          keyboardType="phone-pad"
          left={<TextInput.Icon icon="phone" />}
          testID="mobile-input"
        />
        <HelperText type="error" visible={!!errors.mobile}>{errors.mobile}</HelperText>

        <TextInput label="Address" value={address} onChangeText={setAddress} mode="outlined" multiline numberOfLines={2} testID="address-input" />
        <HelperText type="error" visible={!!errors.address}>{errors.address}</HelperText>

        <TextInput
          label="Pincode"
          value={pincode}
          onChangeText={(t) => setPincode(t.replace(/[^0-9]/g, ""))}
          mode="outlined"
          keyboardType="number-pad"
          testID="pincode-input"
        />
        <HelperText type="error" visible={!!errors.pincode}>{errors.pincode}</HelperText>

        {userType === "seller" && (
          <>
            <TextInput label="Business Name" value={businessName} onChangeText={setBusinessName} mode="outlined" left={<TextInput.Icon icon="storefront" />} testID="businessname-input" />
            <HelperText type="error" visible={!!errors.businessName}>{errors.businessName}</HelperText>
          </>
        )}

        <View style={styles.row}>
          <View style={{ flex: 1 }}>
            <TextInput
              label="Create 4-Digit PIN"
              value={pin}
              onChangeText={(t) => setPin(t.replace(/[^0-9]/g, "").slice(0, 4))}
              mode="outlined"
              secureTextEntry
              keyboardType="number-pad"
              maxLength={4}
              testID="pin-input"
            />
            <HelperText type="error" visible={!!errors.pin}>{errors.pin}</HelperText>
          </View>
          <View style={{ width: 12 }} />
          <View style={{ flex: 1 }}>
            <TextInput
              label="Confirm PIN"
              value={confirmPin}
              onChangeText={(t) => setConfirmPin(t.replace(/[^0-9]/g, "").slice(0, 4))}
              mode="outlined"
              secureTextEntry
              keyboardType="number-pad"
              maxLength={4}
              testID="confirm-pin-input"
            />
            <HelperText type="error" visible={!!errors.confirmPin}>{errors.confirmPin}</HelperText>
          </View>
        </View>

        <Button
          mode="contained"
          onPress={onContinue}
          loading={loading}
          disabled={loading}
          contentStyle={{ height: 52 }}
          style={{ borderRadius: 16, marginTop: 8 }}
          testID="send-otp-btn"
        >
          Send OTP
        </Button>
      </ScrollView>
      <Snackbar visible={!!snack} onDismiss={() => setSnack("")} duration={3500}>
        {snack}
      </Snackbar>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  scroll: { padding: 16, paddingBottom: 32 },
  row: { flexDirection: "row" },
});
