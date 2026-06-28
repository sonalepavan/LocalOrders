import { storage } from "@/src/utils/storage";

const BASE_URL = process.env.EXPO_PUBLIC_BACKEND_URL;
export const TOKEN_KEY = "lo.token";

export type UserType = "buyer" | "seller";

export type AppUser = {
  userId: string;
  userType: UserType;
  firstName: string;
  lastName: string;
  mobileNumber: string;
  address: string;
  pincode: string;
  businessName?: string | null;
  sellerCode?: string | null;
  isMobileVerified: boolean;
  createdDate: string;
  availabilityStatus?: "Open" | "Closed";
};

export type SellerItem = {
  itemId: string;
  sellerId: string;
  itemName: string;
  unitType: string;
  availableQuantity: number;
  reservedQuantity: number;
  pricePerUnit: number;
  minimumOrderQuantity: number;
  unitIncrement: number;
  isActive: boolean;
  lowInventory: boolean;
  createdDate: string;
  updatedDate: string;
};

class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init: RequestInit = {}, auth = false): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...((init.headers as Record<string, string>) || {}),
  };
  if (auth) {
    const token = await storage.secureGet<string>(TOKEN_KEY, "");
    if (token) headers["Authorization"] = `Bearer ${token}`;
  }
  const res = await fetch(`${BASE_URL}/api${path}`, { ...init, headers });
  const text = await res.text();
  const data = text ? safeJson(text) : null;
  if (!res.ok) {
    const detail = (data && (data.detail || data.message)) || `Request failed (${res.status})`;
    throw new ApiError(res.status, typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return data as T;
}

function safeJson(t: string) {
  try {
    return JSON.parse(t);
  } catch {
    return null;
  }
}

export const api = {
  sendOtp: (mobileNumber: string, userType: UserType) =>
    request<{ sent: boolean; mockOtp?: string; message: string }>("/auth/otp/send", {
      method: "POST",
      body: JSON.stringify({ mobileNumber, userType }),
    }),
  registerBuyer: (payload: any) =>
    request<{ token: string; user: AppUser }>("/auth/register/buyer", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  registerSeller: (payload: any) =>
    request<{ token: string; user: AppUser }>("/auth/register/seller", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  login: (mobileNumber: string, pin: string) =>
    request<{ token: string; user: AppUser }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ mobileNumber, pin }),
    }),
  me: () => request<{ user: AppUser }>("/auth/me", {}, true),
  updateProfile: (payload: Partial<AppUser>) =>
    request<{ user: AppUser }>("/users/me", {
      method: "PUT",
      body: JSON.stringify(payload),
    }, true),
  listItems: (includeInactive = false) =>
    request<{ items: SellerItem[] }>(`/seller/items?include_inactive=${includeInactive}`, {}, true),
  createItem: (payload: Omit<SellerItem, "itemId" | "sellerId" | "isActive" | "createdDate" | "updatedDate">) =>
    request<{ item: SellerItem }>("/seller/items", {
      method: "POST",
      body: JSON.stringify(payload),
    }, true),
  updateItem: (itemId: string, payload: Omit<SellerItem, "itemId" | "sellerId" | "isActive" | "createdDate" | "updatedDate">) =>
    request<{ item: SellerItem }>(`/seller/items/${itemId}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    }, true),
  deleteItem: (itemId: string) =>
    request<{ ok: boolean }>(`/seller/items/${itemId}`, { method: "DELETE" }, true),
  unitTypes: () => request<{ unitTypes: string[] }>("/meta/unit-types"),

  // ----- Phase 2: connections & orders -----
  searchSellers: (q: string) =>
    request<{ sellers: SellerSearchResult[] }>(
      `/buyer/sellers/search?q=${encodeURIComponent(q)}`,
      {},
      true,
    ),
  requestConnection: (sellerCode: string) =>
    request<{ connection: Connection }>("/buyer/connections", {
      method: "POST",
      body: JSON.stringify({ sellerCode }),
    }, true),
  buyerConnections: (status?: string) =>
    request<{ connections: Connection[] }>(`/buyer/connections${status ? `?status=${status}` : ""}`, {}, true),
  sellerConnections: (status?: string) =>
    request<{ connections: Connection[] }>(`/seller/connections${status ? `?status=${status}` : ""}`, {}, true),
  acceptConnection: (id: string) =>
    request<{ connection: Connection }>(`/seller/connections/${id}/accept`, { method: "POST" }, true),
  rejectConnection: (id: string) =>
    request<{ connection: Connection }>(`/seller/connections/${id}/reject`, { method: "POST" }, true),
  browseSellerItems: (sellerId: string, q?: string) =>
    request<{ seller: SellerSummary; items: SellerItem[] }>(
      `/buyer/sellers/${sellerId}/items${q ? `?q=${encodeURIComponent(q)}` : ""}`,
      {},
      true,
    ),
  createOrder: (sellerId: string, items: { itemId: string; quantity: number; customMessage?: string }[]) =>
    request<{ order: Order; items: OrderItem[] }>("/buyer/orders", {
      method: "POST",
      body: JSON.stringify({ sellerId, items }),
    }, true),
  buyerOrders: () => request<{ orders: (Order & { seller: SellerSummary | null })[] }>("/buyer/orders", {}, true),
  sellerOrders: () => request<{ orders: (Order & { buyer: BuyerSummary | null })[] }>("/seller/orders", {}, true),
  orderDetail: (orderId: string) =>
    request<{ order: Order; items: OrderItem[]; counterparty: BuyerSummary | SellerSummary | null }>(
      `/orders/${orderId}`,
      {},
      true,
    ),

  // ----- Phase 3: order management -----
  acceptOrder: (orderId: string) =>
    request<{ order: Order }>(`/seller/orders/${orderId}/accept`, { method: "POST" }, true),
  rejectOrder: (orderId: string, reason: string) =>
    request<{ order: Order }>(`/seller/orders/${orderId}/reject`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    }, true),
  deliverOrder: (orderId: string) =>
    request<{ order: Order }>(`/seller/orders/${orderId}/deliver`, { method: "POST" }, true),
  cancelOrder: (orderId: string, reason?: string) =>
    request<{ order: Order }>(`/buyer/orders/${orderId}/cancel`, {
      method: "POST",
      body: JSON.stringify({ reason: reason || null }),
    }, true),

  // ----- Phase 4: availability & dashboard -----
  setAvailability: (status: "Open" | "Closed") =>
    request<{ user: AppUser }>("/seller/availability", {
      method: "PUT",
      body: JSON.stringify({ status }),
    }, true),
  sellerDashboard: () =>
    request<{
      activeItems: number;
      lowInventoryCount: number;
      pendingRequests: number;
      openOrders: number;
      lowInventoryThreshold: number;
      availabilityStatus: "Open" | "Closed";
    }>("/seller/dashboard", {}, true),

  // ----- Notifications & Push -----
  registerPush: (platform: string, deviceToken: string) =>
    request<{ status: string }>("/register-push", {
      method: "POST",
      body: JSON.stringify({ platform, device_token: deviceToken }),
    }, true),
  listNotifications: (limit = 50) =>
    request<{ notifications: AppNotification[]; unreadCount: number }>(
      `/notifications?limit=${limit}`,
      {},
      true,
    ),
  unreadCount: () =>
    request<{ unreadCount: number }>("/notifications/unread-count", {}, true),
  markRead: (notificationId: string) =>
    request<{ notification: AppNotification }>(
      `/notifications/${notificationId}/read`,
      { method: "POST" },
      true,
    ),
  markAllRead: () =>
    request<{ markedCount: number }>("/notifications/read-all", { method: "POST" }, true),

  // ----- Custom Requests ("Need Something Not Listed?") -----
  createCustomRequest: (sellerId: string, requestDetails: string, send: boolean) =>
    request<{ request: CustomRequest }>("/buyer/custom-requests", {
      method: "POST",
      body: JSON.stringify({ sellerId, requestDetails, send }),
    }, true),
  listBuyerCustomRequests: () =>
    request<{ requests: (CustomRequest & { seller: SellerSummary | null })[] }>(
      "/buyer/custom-requests",
      {},
      true,
    ),
  getCustomRequest: (id: string) =>
    request<{ request: CustomRequest; counterparty: BuyerSummary | SellerSummary | null }>(
      `/custom-requests/${id}`,
      {},
      true,
    ),
  updateCustomRequest: (id: string, requestDetails: string) =>
    request<{ request: CustomRequest }>(`/buyer/custom-requests/${id}`, {
      method: "PUT",
      body: JSON.stringify({ requestDetails }),
    }, true),
  deleteCustomRequest: (id: string) =>
    request<{ ok: boolean }>(`/buyer/custom-requests/${id}`, { method: "DELETE" }, true),
  sendCustomRequest: (id: string) =>
    request<{ request: CustomRequest }>(`/buyer/custom-requests/${id}/send`, { method: "POST" }, true),
  acceptQuote: (id: string) =>
    request<{ request: CustomRequest }>(`/buyer/custom-requests/${id}/accept-quote`, { method: "POST" }, true),
  rejectQuote: (id: string) =>
    request<{ request: CustomRequest }>(`/buyer/custom-requests/${id}/reject-quote`, { method: "POST" }, true),
  listSellerCustomRequests: () =>
    request<{ requests: (CustomRequest & { buyer: BuyerSummary | null })[] }>(
      "/seller/custom-requests",
      {},
      true,
    ),
  sellerSendQuote: (id: string, quoteAmount: number, sellerMessage?: string) =>
    request<{ request: CustomRequest }>(`/seller/custom-requests/${id}/quote`, {
      method: "POST",
      body: JSON.stringify({ quoteAmount, sellerMessage: sellerMessage || null }),
    }, true),
  sellerAcceptCustomRequest: (id: string) =>
    request<{ request: CustomRequest }>(`/seller/custom-requests/${id}/accept`, { method: "POST" }, true),
  sellerRejectCustomRequest: (id: string, rejectionReason?: string) =>
    request<{ request: CustomRequest }>(`/seller/custom-requests/${id}/reject`, {
      method: "POST",
      body: JSON.stringify({ rejectionReason: rejectionReason || null }),
    }, true),
  sellerCompleteCustomRequest: (id: string) =>
    request<{ request: CustomRequest }>(`/seller/custom-requests/${id}/complete`, { method: "POST" }, true),
};

export type AppNotification = {
  notificationId: string;
  userId: string;
  type: string;
  title: string;
  body: string;
  data: Record<string, any>;
  readAt: string | null;
  createdDate: string;
};

export type SellerSearchResult = {
  userId: string;
  businessName: string | null;
  sellerCode: string | null;
  firstName: string;
  lastName: string;
  mobileNumber: string;
  address: string;
  pincode: string;
  availabilityStatus?: "Open" | "Closed";
  connectionStatus: "Pending" | "Accepted" | null;
  connectionId: string | null;
};

export type ConnectionStatus = "Pending" | "Accepted" | "Rejected" | "Expired";
export type SellerSummary = {
  userId: string;
  businessName: string | null;
  sellerCode: string | null;
  firstName: string;
  lastName: string;
  mobileNumber: string;
  address: string;
  pincode: string;
  availabilityStatus?: "Open" | "Closed";
};
export type BuyerSummary = {
  userId: string;
  firstName: string;
  lastName: string;
  mobileNumber: string;
  pincode: string;
};
export type Connection = {
  connectionId: string;
  buyerId: string;
  sellerId: string;
  status: ConnectionStatus;
  requestedDateTime: string;
  approvedDateTime: string | null;
  buyer?: BuyerSummary;
  seller?: SellerSummary;
};
export type OrderStatus = "Requested" | "Accepted" | "Rejected" | "Cancelled" | "Delivered" | "Expired";

export type Order = {
  orderId: string;
  orderNumber: string;
  buyerId: string;
  sellerId: string;
  orderStatus: OrderStatus;
  totalAmount: number;
  requestedDateTime: string;
  acceptedDateTime?: string | null;
  rejectedDateTime?: string | null;
  cancelledDateTime?: string | null;
  deliveredDateTime?: string | null;
  expiredDateTime?: string | null;
  rejectionReason?: string | null;
  cancellationReason?: string | null;
};
export type OrderItem = {
  orderItemId: string;
  orderId: string;
  itemId: string;
  itemName: string;
  quantity: number;
  unitType: string;
  pricePerUnit: number;
  itemTotal: number;
  // Optional per-line note from the buyer. May be omitted/null on legacy
  // order_items written before the Custom Message feature was introduced.
  customMessage?: string | null;
};

export { ApiError };

export type CustomRequestStatus =
  | "SAVED"
  | "NEW_REQUEST"
  | "QUOTE_SENT"
  | "ACCEPTED"
  | "COMPLETED"
  | "REJECTED_BY_BUYER"
  | "REJECTED_BY_SELLER";

export type CustomRequest = {
  requestId: string;
  buyerId: string;
  sellerId: string;
  requestDetails: string;
  status: CustomRequestStatus;
  quoteAmount: number | null;
  sellerMessage: string | null;
  rejectionReason: string | null;
  completedAt: string | null;
  createdAt: string;
  updatedAt: string;
};

export const CUSTOM_REQUEST_MIN_LEN = 5;
export const CUSTOM_REQUEST_MAX_LEN = 500;
