import { storage } from "@/src/utils/storage";

export type CartLine = {
  itemId: string;
  itemName: string;
  unitType: string;
  pricePerUnit: number;
  minimumOrderQuantity: number;
  unitIncrement: number;
  availableQuantity: number;
  quantity: number;
};

export type Cart = {
  sellerId: string;
  sellerName: string;
  sellerCode: string;
  lines: CartLine[];
};

const CART_KEY = "lo.cart";

export async function getCart(): Promise<Cart | null> {
  const raw = await storage.getItem<string>(CART_KEY, "");
  if (!raw) return null;
  try {
    return JSON.parse(raw) as Cart;
  } catch {
    return null;
  }
}

export async function saveCart(c: Cart | null): Promise<void> {
  if (!c || c.lines.length === 0) {
    await storage.removeItem(CART_KEY);
    return;
  }
  await storage.setItem(CART_KEY, JSON.stringify(c));
}

export async function clearCart(): Promise<void> {
  await storage.removeItem(CART_KEY);
}

export function cartTotal(c: Cart | null): number {
  if (!c) return 0;
  return c.lines.reduce((s, l) => s + l.quantity * l.pricePerUnit, 0);
}

export function validateLineQty(line: { quantity: number; minimumOrderQuantity: number; unitIncrement: number; availableQuantity: number; itemName: string }): string | null {
  if (line.quantity <= 0) return `${line.itemName}: quantity must be positive`;
  if (line.quantity < line.minimumOrderQuantity) return `${line.itemName}: minimum is ${line.minimumOrderQuantity}`;
  if (line.quantity > line.availableQuantity) return `${line.itemName}: only ${line.availableQuantity} available`;
  if (line.unitIncrement > 0) {
    const diff = line.quantity - line.minimumOrderQuantity;
    const steps = diff / line.unitIncrement;
    if (Math.abs(steps - Math.round(steps)) > 1e-6) {
      return `${line.itemName}: must be ${line.minimumOrderQuantity} + multiples of ${line.unitIncrement}`;
    }
  }
  return null;
}
