import { storage } from "@/src/utils/storage";

export const CUSTOM_MESSAGE_MAX_LENGTH = 500;

/** Normalize a buyer's custom message exactly the way the backend does:
 *  trim whitespace and treat an empty string as "no message" (undefined). */
export function sanitizeCustomMessage(raw: string | null | undefined): string | undefined {
  if (!raw) return undefined;
  const trimmed = raw.trim();
  return trimmed.length === 0 ? undefined : trimmed;
}

export type CartLine = {
  itemId: string;
  itemName: string;
  unitType: string;
  pricePerUnit: number;
  minimumOrderQuantity: number;
  unitIncrement: number;
  availableQuantity: number;
  quantity: number;
  // Optional per-item buyer note to the seller. Stored trimmed (or omitted).
  // Capped at CUSTOM_MESSAGE_MAX_LENGTH characters; older carts without this
  // field continue to work since it is optional.
  customMessage?: string;
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
