import { router } from "expo-router";
import { useCallback, useEffect, useRef, useState } from "react";
import { FlatList, StyleSheet, View } from "react-native";
import { ActivityIndicator, Appbar, Card, Chip, Snackbar, Text, TextInput, useTheme } from "react-native-paper";
import { SafeAreaView } from "react-native-safe-area-context";

import { SellerSearchResult, api } from "@/src/lib/api";

function shortAddress(addr: string): string {
  if (!addr) return "";
  const firstLine = addr.split(/[\n,]/)[0].trim();
  if (firstLine.length <= 60) return firstLine;
  return firstLine.slice(0, 57).trimEnd() + "...";
}

export default function BuyerSearchSellers() {
  const theme = useTheme();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SellerSearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);
  const [snack, setSnack] = useState("");
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const runSearch = useCallback(async (q: string) => {
    const trimmed = q.trim();
    if (trimmed.length === 0) {
      setResults([]);
      setHasSearched(false);
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const { sellers } = await api.searchSellers(trimmed);
      setResults(sellers);
      setHasSearched(true);
    } catch (e: any) {
      setSnack(e?.message || "Search failed");
      setResults([]);
      setHasSearched(true);
    } finally {
      setLoading(false);
    }
  }, []);

  // Debounce text input → search
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => runSearch(query), 350);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [query, runSearch]);

  const openDetails = (seller: SellerSearchResult) => {
    router.push({
      pathname: "/buyer-seller-details",
      params: { seller: JSON.stringify(seller) },
    });
  };

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: theme.colors.background }} edges={["top", "bottom"]}>
      <Appbar.Header mode="small" elevated>
        <Appbar.BackAction onPress={() => router.back()} testID="back-btn" />
        <Appbar.Content title="Search Sellers" />
      </Appbar.Header>

      <View style={styles.searchBox}>
        <TextInput
          mode="outlined"
          value={query}
          onChangeText={setQuery}
          placeholder="Search by code, name, address or pincode"
          left={<TextInput.Icon icon="magnify" />}
          right={query.length > 0 ? <TextInput.Icon icon="close" onPress={() => setQuery("")} /> : undefined}
          autoCapitalize="none"
          autoCorrect={false}
          testID="seller-search-input"
          dense
        />
      </View>

      {loading ? (
        <View style={styles.center} testID="search-loading">
          <ActivityIndicator />
        </View>
      ) : (
        <FlatList
          data={results}
          keyExtractor={(s) => s.userId}
          contentContainerStyle={{ padding: 16, paddingBottom: 32 }}
          keyboardShouldPersistTaps="handled"
          renderItem={({ item }) => (
            <Card
              style={styles.card}
              onPress={() => openDetails(item)}
              testID={`search-result-${item.sellerCode || item.userId}`}
            >
              <Card.Content>
                <Text variant="titleMedium" style={{ fontWeight: "700" }}>
                  {item.businessName || `${item.firstName} ${item.lastName}`}
                </Text>
                <View style={styles.row}>
                  {item.sellerCode ? (
                    <Chip compact style={styles.chip} icon="barcode" testID={`chip-code-${item.userId}`}>
                      {item.sellerCode}
                    </Chip>
                  ) : null}
                  {item.pincode ? (
                    <Chip compact style={styles.chip} icon="map-marker" testID={`chip-pincode-${item.userId}`}>
                      {item.pincode}
                    </Chip>
                  ) : null}
                  {item.connectionStatus ? (
                    <Chip
                      compact
                      style={styles.chip}
                      icon={item.connectionStatus === "Accepted" ? "check-circle" : "clock-outline"}
                      testID={`chip-status-${item.userId}`}
                    >
                      {item.connectionStatus === "Accepted" ? "Connected" : "Pending"}
                    </Chip>
                  ) : null}
                </View>
                {item.address ? (
                  <Text variant="bodySmall" style={{ color: theme.colors.onSurfaceVariant, marginTop: 8 }}>
                    {shortAddress(item.address)}
                  </Text>
                ) : null}
              </Card.Content>
            </Card>
          )}
          ListEmptyComponent={
            <View style={styles.empty}>
              {hasSearched ? (
                <>
                  <Text variant="titleMedium" testID="empty-title" style={{ marginBottom: 4 }}>
                    No sellers found
                  </Text>
                  <Text
                    variant="bodyMedium"
                    style={{ color: theme.colors.onSurfaceVariant, textAlign: "center", paddingHorizontal: 32 }}
                  >
                    Try a different code, business name, address or pincode.
                  </Text>
                </>
              ) : (
                <Text
                  variant="bodyMedium"
                  style={{ color: theme.colors.onSurfaceVariant, textAlign: "center", paddingHorizontal: 32 }}
                >
                  Start typing to search local sellers.
                </Text>
              )}
            </View>
          }
        />
      )}

      <Snackbar visible={!!snack} onDismiss={() => setSnack("")} duration={2500}>
        {snack}
      </Snackbar>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  searchBox: { paddingHorizontal: 16, paddingTop: 12, paddingBottom: 4 },
  center: { flex: 1, alignItems: "center", justifyContent: "center" },
  card: { borderRadius: 16, marginBottom: 12 },
  row: { flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: 8 },
  chip: {},
  empty: { alignItems: "center", paddingTop: 60 },
});
