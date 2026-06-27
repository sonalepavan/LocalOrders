import { router, useFocusEffect, useLocalSearchParams } from "expo-router";
import { useCallback, useEffect, useMemo, useState } from "react";
import { FlatList, StyleSheet, View } from "react-native";
import { ActivityIndicator, Appbar, Badge, Button, Card, Chip, Divider, IconButton, Searchbar, Snackbar, Text, useTheme } from "react-native-paper";
import { SafeAreaView } from "react-native-safe-area-context";

import { SellerItem, SellerSummary, api } from "@/src/lib/api";
import { Cart, getCart, saveCart, validateLineQty } from "@/src/lib/cart";

export default function BuyerSellerItems() {
  const { sellerId } = useLocalSearchParams<{ sellerId: string }>();
  const theme = useTheme();
  const [seller, setSeller] = useState<SellerSummary | null>(null);
  const [items, setItems] = useState<SellerItem[]>([]);
  const [cart, setCart] = useState<Cart | null>(null);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [snack, setSnack] = useState("");
  // Per-item selected quantity (defaults to MOQ when items load)
  const [qtyMap, setQtyMap] = useState<Record<string, number>>({});

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [{ seller: s, items: list }, c] = await Promise.all([api.browseSellerItems(sellerId), getCart()]);
      setSeller(s);
      setItems(list);
      setCart(c);
      // Initialize quantities to each item's MOQ
      const initial: Record<string, number> = {};
      list.forEach((it) => { initial[it.itemId] = it.minimumOrderQuantity; });
      setQtyMap(initial);
    } catch (e: any) {
      setSnack(e?.message || "Failed to load");
    } finally {
      setLoading(false);
    }
  }, [sellerId]);

  useEffect(() => { load(); }, [load]);

  // Re-sync the cart from storage whenever this screen regains focus
  // (e.g. after returning from /buyer-cart where items may have been removed,
  // the cart cleared, or an order placed). This keeps the cart badge in the
  // header in sync with the actual cart state without re-fetching items.
  useFocusEffect(
    useCallback(() => {
      let cancelled = false;
      (async () => {
        const c = await getCart();
        if (!cancelled) setCart(c);
      })();
      return () => { cancelled = true; };
    }, []),
  );

  const filtered = useMemo(() => {
    if (!query.trim()) return items;
    const q = query.trim().toLowerCase();
    return items.filter((i) => i.itemName.toLowerCase().includes(q));
  }, [items, query]);

  const cartCount = cart?.lines.length || 0;
  const sameSeller = !cart || cart.sellerId === sellerId;
  const isClosed = seller?.availabilityStatus === "Closed";

  const getQty = (item: SellerItem) => {
    const q = qtyMap[item.itemId];
    return typeof q === "number" ? q : item.minimumOrderQuantity;
  };

  const stepQty = (item: SellerItem, delta: 1 | -1) => {
    const current = getQty(item);
    const next = +(current + delta * item.unitIncrement).toFixed(6);
    if (next < item.minimumOrderQuantity) {
      setSnack(`Min ${item.minimumOrderQuantity} ${item.unitType}`);
      return;
    }
    if (next > item.availableQuantity) {
      setSnack(`Only ${item.availableQuantity} available`);
      return;
    }
    setQtyMap((prev) => ({ ...prev, [item.itemId]: next }));
  };

  // Adds the selected quantity to the cart (replaces existing line's qty for this item),
  // returning the updated cart on success or null on failure.
  const addSelectedToCart = async (item: SellerItem): Promise<Cart | null> => {
    if (isClosed) {
      setSnack("Seller currently unavailable.");
      return null;
    }
    if (cart && cart.sellerId !== sellerId) {
      setSnack("Cart contains items from a different seller. Clear or place that order first.");
      return null;
    }
    const qty = getQty(item);
    const err = validateLineQty({
      quantity: qty,
      minimumOrderQuantity: item.minimumOrderQuantity,
      unitIncrement: item.unitIncrement,
      availableQuantity: item.availableQuantity,
      itemName: item.itemName,
    });
    if (err) { setSnack(err); return null; }
    const existing: Cart = cart || {
      sellerId,
      sellerName: seller?.businessName || "Seller",
      sellerCode: seller?.sellerCode || "",
      lines: [],
    };
    const idx = existing.lines.findIndex((l) => l.itemId === item.itemId);
    if (idx >= 0) {
      existing.lines[idx] = {
        ...existing.lines[idx],
        quantity: qty,
        availableQuantity: item.availableQuantity,
        pricePerUnit: item.pricePerUnit,
      };
    } else {
      existing.lines.push({
        itemId: item.itemId,
        itemName: item.itemName,
        unitType: item.unitType,
        pricePerUnit: item.pricePerUnit,
        minimumOrderQuantity: item.minimumOrderQuantity,
        unitIncrement: item.unitIncrement,
        availableQuantity: item.availableQuantity,
        quantity: qty,
      });
    }
    await saveCart(existing);
    setCart({ ...existing });
    return existing;
  };

  const onAddToCart = async (item: SellerItem) => {
    const updated = await addSelectedToCart(item);
    if (!updated) return;
    router.push("/buyer-cart");
  };

  const onPlaceOrderNow = async (item: SellerItem) => {
    const updated = await addSelectedToCart(item);
    if (!updated) return;
    // Reuse existing Cart + Place Order flow by signalling auto-place via route param.
    router.push({ pathname: "/buyer-cart", params: { autoPlace: "1" } });
  };

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: theme.colors.background }} edges={["top"]}>
      <Appbar.Header mode="small" elevated>
        <Appbar.BackAction onPress={() => router.back()} testID="back-btn" />
        <Appbar.Content title={seller?.businessName || "Items"} subtitle={seller?.sellerCode || ""} />
        <View>
          <IconButton icon="cart" onPress={() => router.push("/buyer-cart")} testID="cart-btn" />
          {cartCount > 0 && <Badge style={styles.badge}>{cartCount}</Badge>}
        </View>
      </Appbar.Header>

      <View style={styles.searchWrap}>
        <Searchbar placeholder="Search items" value={query} onChangeText={setQuery} testID="search-items-input" />
      </View>

      {isClosed && (
        <View style={{ paddingHorizontal: 16, paddingBottom: 8 }}>
          <Card style={{ backgroundColor: theme.colors.errorContainer, borderRadius: 12 }} testID="seller-closed-banner">
            <Card.Content>
              <Text variant="titleSmall" style={{ color: theme.colors.onErrorContainer, fontWeight: "700" }}>
                Seller currently unavailable.
              </Text>
              <Text variant="bodySmall" style={{ color: theme.colors.onErrorContainer, marginTop: 4 }}>
                You can browse items, but orders cannot be placed until the seller is Open.
              </Text>
            </Card.Content>
          </Card>
        </View>
      )}

      {loading ? (
        <View style={styles.center}><ActivityIndicator /></View>
      ) : (
        <FlatList
          data={filtered}
          keyExtractor={(i) => i.itemId}
          contentContainerStyle={{ padding: 16, paddingBottom: 32 }}
          ListEmptyComponent={
            <View style={styles.empty}>
              <Text variant="titleMedium" style={{ marginBottom: 4 }}>No items found</Text>
              <Text variant="bodyMedium" style={{ color: theme.colors.onSurfaceVariant, textAlign: "center", paddingHorizontal: 32 }}>
                {query ? "Try a different search term." : "Seller has no active items yet."}
              </Text>
            </View>
          }
          renderItem={({ item }) => {
            const qty = getQty(item);
            const disabled = !sameSeller || isClosed || item.availableQuantity < item.minimumOrderQuantity;
            return (
              <Card style={styles.card} testID={`browse-item-${item.itemId}`}>
                <Card.Content>
                  <Text variant="titleMedium" style={{ fontWeight: "700" }}>{item.itemName}</Text>
                  <View style={styles.chipsRow}>
                    <Chip compact style={styles.chip}>{item.unitType}</Chip>
                    <Chip compact style={styles.chip}>₹{item.pricePerUnit}/{item.unitType}</Chip>
                    <Chip compact style={styles.chip}>{item.availableQuantity} avail</Chip>
                    {item.lowInventory && (
                      <Chip compact icon="alert" style={{ backgroundColor: theme.colors.errorContainer }} textStyle={{ color: theme.colors.onErrorContainer }}>
                        Low
                      </Chip>
                    )}
                  </View>
                  <Text variant="bodySmall" style={{ color: theme.colors.onSurfaceVariant, marginTop: 8 }}>
                    Min: {item.minimumOrderQuantity} · Step: {item.unitIncrement}
                  </Text>

                  <Divider style={{ marginVertical: 12 }} />

                  <View style={styles.qtyRow}>
                    <Text variant="bodyMedium" style={{ color: theme.colors.onSurfaceVariant }}>Quantity</Text>
                    <View style={styles.stepper}>
                      <IconButton
                        icon="minus"
                        mode="outlined"
                        onPress={() => stepQty(item, -1)}
                        disabled={disabled || qty <= item.minimumOrderQuantity}
                        testID={`item-dec-${item.itemId}`}
                      />
                      <Text
                        variant="titleMedium"
                        style={{ minWidth: 56, textAlign: "center", fontWeight: "700" }}
                        testID={`item-qty-${item.itemId}`}
                      >
                        {qty}
                      </Text>
                      <IconButton
                        icon="plus"
                        mode="outlined"
                        onPress={() => stepQty(item, 1)}
                        disabled={disabled || qty + item.unitIncrement > item.availableQuantity}
                        testID={`item-inc-${item.itemId}`}
                      />
                    </View>
                  </View>

                  <Button
                    mode="contained-tonal"
                    icon="cart-plus"
                    onPress={() => onAddToCart(item)}
                    disabled={disabled}
                    style={{ marginTop: 8, borderRadius: 12 }}
                    testID={`add-to-cart-${item.itemId}`}
                  >
                    {isClosed ? "Unavailable" : "Add to Cart"}
                  </Button>
                  <Button
                    mode="contained"
                    icon="flash"
                    onPress={() => onPlaceOrderNow(item)}
                    disabled={disabled}
                    style={{ marginTop: 8, borderRadius: 12 }}
                    testID={`place-order-now-${item.itemId}`}
                  >
                    Place Order Now
                  </Button>
                </Card.Content>
              </Card>
            );
          }}
        />
      )}

      <Snackbar visible={!!snack} onDismiss={() => setSnack("")} duration={2500}>{snack}</Snackbar>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  searchWrap: { padding: 16, paddingBottom: 8 },
  center: { flex: 1, alignItems: "center", justifyContent: "center" },
  empty: { alignItems: "center", paddingTop: 60 },
  card: { borderRadius: 16, marginBottom: 12 },
  chipsRow: { flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: 8 },
  chip: {},
  badge: { position: "absolute", top: 4, right: 4 },
  qtyRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  stepper: { flexDirection: "row", alignItems: "center" },
});
