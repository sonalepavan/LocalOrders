import { MD3DarkTheme, MD3LightTheme } from "react-native-paper";

// LocalOrders brand palette — fresh, neighborhood-grocery green with a warm-amber accent.
const brandLight = {
  primary: "#1B5E20",
  onPrimary: "#FFFFFF",
  primaryContainer: "#B7F3BC",
  onPrimaryContainer: "#002106",
  secondary: "#F57C00",
  onSecondary: "#FFFFFF",
  secondaryContainer: "#FFE0B2",
  onSecondaryContainer: "#2D1600",
  tertiary: "#1A5276",
  onTertiary: "#FFFFFF",
  tertiaryContainer: "#CFE6FA",
  onTertiaryContainer: "#001D31",
  error: "#B3261E",
  onError: "#FFFFFF",
  errorContainer: "#F9DEDC",
  onErrorContainer: "#410E0B",
  background: "#F6F8F5",
  onBackground: "#0F1A12",
  surface: "#FFFFFF",
  onSurface: "#0F1A12",
  surfaceVariant: "#DCEAD7",
  onSurfaceVariant: "#3F4A40",
  outline: "#6F7A6E",
  outlineVariant: "#BFC9BB",
  inverseSurface: "#1A2C20",
  inverseOnSurface: "#E3F1DE",
  inversePrimary: "#5BD66D",
};

const brandDark = {
  primary: "#9CDF9F",
  onPrimary: "#003910",
  primaryContainer: "#16531B",
  onPrimaryContainer: "#B7F3BC",
  secondary: "#FFB95E",
  onSecondary: "#4A2600",
  secondaryContainer: "#693A00",
  onSecondaryContainer: "#FFE0B2",
  tertiary: "#92CCF2",
  onTertiary: "#00344F",
  tertiaryContainer: "#1A5276",
  onTertiaryContainer: "#CFE6FA",
  error: "#F2B8B5",
  onError: "#601410",
  errorContainer: "#8C1D18",
  onErrorContainer: "#F9DEDC",
  background: "#0E1410",
  onBackground: "#E4ECE3",
  surface: "#121A14",
  onSurface: "#E4ECE3",
  surfaceVariant: "#3F4A40",
  onSurfaceVariant: "#BFC9BB",
  outline: "#8B958A",
  outlineVariant: "#3F4A40",
  inverseSurface: "#E4ECE3",
  inverseOnSurface: "#1A2C20",
  inversePrimary: "#1B5E20",
};

export const lightTheme = {
  ...MD3LightTheme,
  roundness: 4,
  colors: { ...MD3LightTheme.colors, ...brandLight },
};

export const darkTheme = {
  ...MD3DarkTheme,
  roundness: 4,
  colors: { ...MD3DarkTheme.colors, ...brandDark },
};

export type ThemePreference = "light" | "dark" | "system";
