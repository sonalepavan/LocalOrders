import { ItemForm } from "@/src/components/ItemForm";
import { api } from "@/src/lib/api";

export default function AddItem() {
  return (
    <ItemForm
      title="Add Item"
      submitLabel="Add Item"
      onSubmit={async (payload) => {
        await api.createItem(payload);
      }}
    />
  );
}
