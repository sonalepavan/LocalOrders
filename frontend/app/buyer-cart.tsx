import { router, useFocusEffect } from "expo-router";
import { useCallback, useState } from "react";
import { FlatList, StyleSheet, View } from "react-native";
import { ActivityIndicator, Appbar, Button, Card, Divider, IconButton, Snackbar, Surface, Text, useTheme } from "react-native-paper";
import { SafeAreaView } from "react-native-safe-area-context";

import { api } from "@/src/lib/api";
import { Cart, CartLine, cartTotal, clearCart, getCart, saveCart, validateLineQty } from "@/src/lib/cart";
import { useNetwork } from "@/src/lib/network";

export default function BuyerCart() {
  const theme = useTheme();
  const { online } = useNetwork();
  const [cart, setCart] = useState<Cart | null>(null);
  const [loading, setLoading] = useState(true);
  const [placing, setPlacing] = useState(false);
  const [snack, setSnack] = useState("");

  const load = useCallback(async () => {
    const c = await getCart();
    setCart(c);
    setLoading(false);
  }, []);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const updateQty = async (itemId: string, delta: number) => {
    if (!cart) return;
    const next = { ...cart, lines: cart.lines.map((l) => ({ ...l })) };
    const idx = next.lines.findIndex((l) => l.itemId === itemId);
    if (idx < 0) return;
    const line = next.lines[idx];
    const newQty = +(line.quantity + delta * line.unitIncrement).toFixed(6);
    if (newQty < line.minimumOrderQuantity) { setSnack(`Min ${line.minimumOrderQuantity} ${line.unitType}`); return; }
    if (newQty > line.availableQuantity) { setSnack(`Only ${line.availableQuantity} available`); return; }
    next.lines[idx] = { ...line, quantity: newQty };
    setCart(next);
    await saveCart(next);
  };

  const removeLine = async (itemId: string) => {
    if (!cart) return;
    const next = { ...cart, lines: cart.lines.filter((l) => l.itemId !== itemId) };
    setCart(next.lines.length ? next : null);
    await saveCart(next.lines.length ? next : null);
  };

  const onClear = async () => {
    await clearCart();
    setCart(null);
  };

  const placeOrder = async () => {
    if (!cart || cart.lines.length === 0) return;
    if (!online) {
      setSnack("Order placement requires an internet connection");
      return;
    }
    for (const l of cart.lines) {
      const err = validateLineQty(l);
      if (err) { setSnack(err); return; }
    }
    setPlacing(true);
    try {
      const { order } = await api.createOrder(
        cart.sellerId,
        cart.lines.map((l) => ({ itemId: l.itemId, quantity: l.quantity })),
      );
      await clearCart();
      setCart(null);
      router.replace({ pathname: "/buyer-order-detail", params: { orderId: order.orderId } });
    } catch (e: any) {
      setSnack(e?.message || "Failed to place order");
    } finally {
      setPlacing(false);
    }
  };

  if (loading) {
    return (
      <SafeAreaView style={{ flex: 1, backgroundColor: theme.colors.background }} edges={["top"]}>
        <Appbar.Header mode="small" elevated>
          <Appbar.BackAction onPress={() => router.back()} testID="back-btn" />
          <Appbar.Content title="Cart" />
        </Appbar.Header>
        <View style={styles.center}><ActivityIndicator /></View>
      </SafeAreaView>
    );
  }

  if (!cart || cart.lines.length === 0) {
    return (
      <SafeAreaView style={{ flex: 1, backgroundColor: theme.colors.background }} edges={["top"]}>
        <Appbar.Header mode="small" elevated>
          <Appbar.BackAction onPress={() => router.back()} testID="back-btn" />
          <Appbar.Content title="Cart" />
        </Appbar.Header>
        <View style={styles.center}>
          <Text variant="titleMedium" testID="empty-cart">Your cart is empty</Text>
          <Text variant="bodyMedium" style={{ color: theme.colors.onSurfaceVariant, marginTop: 6 }}>
            Add items from a seller to get started.
          </Text>
        </View>
      </SafeAreaView>
    );
  }

  const total = cartTotal(cart);

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: theme.colors.background }} edges={["top"]}>
      <Appbar.Header mode="small" elevated>
        <Appbar.BackAction onPress={() => router.back()} testID="back-btn" />
        <Appbar.Content title="Cart" subtitle={cart.sellerName} />
        <Appbar.Action icon="trash-can-outline" onPress={onClear} testID="clear-cart-btn" />
      </Appbar.Header>
      <FlatList
        data={cart.lines}
        keyExtractor={(l) => l.itemId}
        contentContainerStyle={{ padding: 16, paddingBottom: 140 }}
        renderItem={({ item }) => <CartRow line={item} onInc={() => updateQty(item.itemId, +1)} onDec={() => updateQty(item.itemId, -1)} onRemove={() => removeLine(item.itemId)} />}
      />
      <Surface elevation={4} style={[styles.bottomBar, { backgroundColor: theme.colors.surface }]}>
        <View style={styles.totalRow}>
          <Text variant="titleMedium">Total</Text>
          <Text variant="titleLarge" style={{ fontWeight: "700" }} testID="cart-total">₹{total.toFixed(2)}</Text>
        </View>
        <Button
          mode="contained"
          icon="check"
          onPress={placeOrder}
          loading={placing}
          disabled={placing}
          contentStyle={{ height: 52 }}
          style={{ borderRadius: 16, marginTop: 8 }}
          testID="place-order-btn"
        >
          Place Order
        </Button>
      </Surface>
      <Snackbar visible={!!snack} onDismiss={() => setSnack("")} duration={2500}>{snack}</Snackbar>
    </SafeAreaView>
  );
}

function CartRow({ line, onInc, onDec, onRemove }: { line: CartLine; onInc: () => void; onDec: () => void; onRemove: () => void }) {
  const theme = useTheme();
  return (
    <Card style={{ marginBottom: 12, borderRadius: 16 }} testID={`cart-line-${line.itemId}`}>
      <Card.Content>
        <View style={{ flexDirection: "row", alignItems: "flex-start" }}>
          <View style={{ flex: 1 }}>
            <Text variant="titleMedium" style={{ fontWeight: "700" }}>{line.itemName}</Text>
            <Text variant="bodySmall" style={{ color: theme.colors.onSurfaceVariant, marginTop: 2 }}>
              ₹{line.pricePerUnit}/{line.unitType} · Step {line.unitIncrement}
            </Text>
          </View>
          <IconButton icon="close" onPress={onRemove} testID={`remove-line-${line.itemId}`} />
        </View>
        <Divider style={{ marginVertical: 8 }} />
        <View style={styles.qtyRow}>
          <View style={styles.stepper}>
            <IconButton icon="minus" mode="outlined" onPress={onDec} testID={`dec-${line.itemId}`} />
            <Text variant="titleMedium" style={{ minWidth: 48, textAlign: "center" }} testID={`qty-${line.itemId}`}>{line.quantity}</Text>
            <IconButton icon="plus" mode="outlined" onPress={onInc} testID={`inc-${line.itemId}`} />
          </View>
          <Text variant="titleMedium" style={{ fontWeight: "700" }}>₹{(line.quantity * line.pricePerUnit).toFixed(2)}</Text>
        </View>
      </Card.Content>
    </Card>
  );
}

const styles = StyleSheet.create({
  center: { flex: 1, alignItems: "center", justifyContent: "center", paddingHorizontal: 32 },
  bottomBar: { position: "absolute", left: 0, right: 0, bottom: 0, padding: 16, paddingBottom: 24, borderTopLeftRadius: 20, borderTopRightRadius: 20 },
  totalRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  qtyRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  stepper: { flexDirection: "row", alignItems: "center" },
});
