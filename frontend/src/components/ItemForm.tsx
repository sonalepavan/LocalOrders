import { router } from "expo-router";
import { useState } from "react";
import { Platform, ScrollView, StyleSheet, View } from "react-native";
import { Appbar, Button, HelperText, Menu, Snackbar, TextInput, useTheme } from "react-native-paper";
import { SafeAreaView } from "react-native-safe-area-context";

import { SellerItem } from "@/src/lib/api";

const UNIT_TYPES = ["Piece", "Bottle", "Packet", "Kg", "Gram", "Litre", "ml", "Dozen", "Can", "Box"];

type Props = {
  initial?: SellerItem;
  onSubmit: (payload: any) => Promise<void>;
  title: string;
  submitLabel: string;
};

export function ItemForm({ initial, onSubmit, title, submitLabel }: Props) {
  const theme = useTheme();
  const [itemName, setItemName] = useState(initial?.itemName || "");
  const [unitType, setUnitType] = useState(initial?.unitType || "Piece");
  const [availableQty, setAvailableQty] = useState(initial ? String(initial.availableQuantity) : "");
  const [price, setPrice] = useState(initial ? String(initial.pricePerUnit) : "");
  const [minQty, setMinQty] = useState(initial ? String(initial.minimumOrderQuantity) : "1");
  const [increment, setIncrement] = useState(initial ? String(initial.unitIncrement) : "1");
  const [menuOpen, setMenuOpen] = useState(false);
  const [err, setErr] = useState<Record<string, string>>({});
  const [snack, setSnack] = useState("");
  const [saving, setSaving] = useState(false);

  const validate = () => {
    const e: Record<string, string> = {};
    if (!itemName.trim()) e.itemName = "Item name required";
    if (!UNIT_TYPES.includes(unitType)) e.unitType = "Pick a unit type";
    const num = (s: string) => s !== "" && !isNaN(Number(s)) && Number(s) >= 0;
    if (!num(availableQty)) e.availableQty = "Enter a valid quantity";
    if (!num(price) || Number(price) <= 0) e.price = "Enter a valid price";
    if (!num(minQty) || Number(minQty) <= 0) e.minQty = "Enter min order qty";
    if (!num(increment) || Number(increment) <= 0) e.increment = "Enter unit increment";
    return e;
  };

  const submit = async () => {
    const e = validate();
    setErr(e);
    if (Object.keys(e).length) return;
    setSaving(true);
    try {
      await onSubmit({
        itemName: itemName.trim(),
        unitType,
        availableQuantity: Number(availableQty),
        pricePerUnit: Number(price),
        minimumOrderQuantity: Number(minQty),
        unitIncrement: Number(increment),
      });
      router.back();
    } catch (er: any) {
      setSnack(er?.message || "Failed to save");
    } finally {
      setSaving(false);
    }
  };

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: theme.colors.background }} edges={["top", "bottom"]}>
      <Appbar.Header mode="small" elevated>
        <Appbar.BackAction onPress={() => router.back()} testID="back-btn" />
        <Appbar.Content title={title} />
      </Appbar.Header>
      <ScrollView
        contentContainerStyle={styles.body}
        keyboardShouldPersistTaps="handled"
        keyboardDismissMode={Platform.OS === "ios" ? "interactive" : "on-drag"}
      >
        <TextInput label="Item Name" value={itemName} onChangeText={setItemName} mode="outlined" testID="item-name-input" />
        <HelperText type="error" visible={!!err.itemName}>{err.itemName}</HelperText>

        <Menu
          visible={menuOpen}
          onDismiss={() => setMenuOpen(false)}
          anchor={
            <Button mode="outlined" onPress={() => setMenuOpen(true)} contentStyle={{ height: 52, justifyContent: "flex-start" }} style={styles.menuBtn} testID="unit-type-btn">
              Unit Type: {unitType}
            </Button>
          }
        >
          {UNIT_TYPES.map((u) => (
            <Menu.Item
              key={u}
              title={u}
              onPress={() => { setUnitType(u); setMenuOpen(false); }}
              testID={`unit-${u}`}
            />
          ))}
        </Menu>

        <View style={styles.rowGap}>
          <View style={{ flex: 1 }}>
            <TextInput label="Available Quantity" value={availableQty} onChangeText={(t) => setAvailableQty(t.replace(/[^0-9.]/g, ""))} keyboardType="decimal-pad" mode="outlined" testID="qty-input" />
            <HelperText type="error" visible={!!err.availableQty}>{err.availableQty}</HelperText>
          </View>
          <View style={{ width: 12 }} />
          <View style={{ flex: 1 }}>
            <TextInput label="Price Per Unit (₹)" value={price} onChangeText={(t) => setPrice(t.replace(/[^0-9.]/g, ""))} keyboardType="decimal-pad" mode="outlined" testID="price-input" />
            <HelperText type="error" visible={!!err.price}>{err.price}</HelperText>
          </View>
        </View>

        <View style={styles.rowGap}>
          <View style={{ flex: 1 }}>
            <TextInput label="Minimum Order Quantity" value={minQty} onChangeText={(t) => setMinQty(t.replace(/[^0-9.]/g, ""))} keyboardType="decimal-pad" mode="outlined" testID="min-qty-input" />
            <HelperText type="error" visible={!!err.minQty}>{err.minQty}</HelperText>
          </View>
          <View style={{ width: 12 }} />
          <View style={{ flex: 1 }}>
            <TextInput label="Unit Increment" value={increment} onChangeText={(t) => setIncrement(t.replace(/[^0-9.]/g, ""))} keyboardType="decimal-pad" mode="outlined" testID="increment-input" />
            <HelperText type="error" visible={!!err.increment}>{err.increment}</HelperText>
          </View>
        </View>

        <Button mode="contained" onPress={submit} loading={saving} disabled={saving} contentStyle={{ height: 52 }} style={{ borderRadius: 16, marginTop: 8 }} testID="submit-item-btn">
          {submitLabel}
        </Button>
      </ScrollView>
      <Snackbar visible={!!snack} onDismiss={() => setSnack("")} duration={3500}>
        {snack}
      </Snackbar>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  body: { padding: 16, paddingBottom: 32 },
  menuBtn: { borderRadius: 12, marginBottom: 16 },
  rowGap: { flexDirection: "row" },
});
