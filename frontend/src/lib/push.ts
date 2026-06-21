import { Platform } from "react-native";
import * as Notifications from "expo-notifications";

import { api } from "./api";

/**
 * Request push permission, fetch the native device push token, and register it with the backend.
 * Safe to call repeatedly (e.g. on every app open & after login).
 * The backend pulls userId from the auth token; we just send the device token.
 * Never throws — push failures must not block app usage.
 */
export async function registerForPush(): Promise<boolean> {
  if (Platform.OS === "web") return false;
  try {
    const settings = await Notifications.getPermissionsAsync();
    let status = settings.status;
    if (status !== "granted" && settings.canAskAgain) {
      const ask = await Notifications.requestPermissionsAsync();
      status = ask.status;
    }
    if (status !== "granted") return false;
    const token = await Notifications.getDevicePushTokenAsync();
    if (!token?.data) return false;
    await api.registerPush(Platform.OS, String(token.data));
    return true;
  } catch (e) {
    // Swallow errors — push is best-effort
    console.warn("[push] registerForPush failed (non-blocking):", e);
    return false;
  }
}
