import { MaterialCommunityIcons } from "@expo/vector-icons";
import { StyleSheet, View } from "react-native";
import { Text, useTheme } from "react-native-paper";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { useNetwork } from "@/src/lib/network";

export function OfflineBanner() {
  const theme = useTheme();
  const { online } = useNetwork();
  const insets = useSafeAreaInsets();

  if (online) return null;

  return (
    <View
      testID="offline-banner"
      style={[
        styles.banner,
        {
          paddingTop: insets.top + 6,
          backgroundColor: theme.colors.errorContainer,
          borderBottomColor: theme.colors.outlineVariant,
        },
      ]}
    >
      <MaterialCommunityIcons
        name="wifi-off"
        size={16}
        color={theme.colors.onErrorContainer}
      />
      <Text
        variant="labelMedium"
        style={{ color: theme.colors.onErrorContainer, marginLeft: 6, fontWeight: "600" }}
      >
        You're offline · showing saved data
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  banner: {
    position: "absolute",
    top: 0,
    left: 0,
    right: 0,
    zIndex: 1000,
    paddingBottom: 6,
    paddingHorizontal: 12,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
});
