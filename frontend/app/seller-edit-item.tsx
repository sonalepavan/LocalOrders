import { useLocalSearchParams } from "expo-router";
import { useEffect, useState } from "react";
import { ActivityIndicator, View } from "react-native";

import { ItemForm } from "@/src/components/ItemForm";
import { SellerItem, api } from "@/src/lib/api";

export default function EditItem() {
  const { itemId } = useLocalSearchParams<{ itemId: string }>();
  const [item, setItem] = useState<SellerItem | null>(null);

  useEffect(() => {
    (async () => {
      const { items } = await api.listItems(true);
      const found = items.find((i) => i.itemId === itemId) || null;
      setItem(found);
    })();
  }, [itemId]);

  if (!item) {
    return (
      <View style={{ flex: 1, alignItems: "center", justifyContent: "center" }}>
        <ActivityIndicator />
      </View>
    );
  }

  return (
    <ItemForm
      title="Edit Item"
      submitLabel="Save Changes"
      initial={item}
      onSubmit={async (payload) => {
        await api.updateItem(item.itemId, payload);
      }}
    />
  );
}
