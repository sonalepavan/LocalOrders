# LocalOrders — PRD (Phase 1 → 4)

## Overview
LocalOrders connects local Buyers to local Sellers. Built on **Expo (React Native)** + **react-native-paper (MD3)**, **FastAPI + MongoDB** backend (Firestore-shaped collections), **mock OTP** (`123456`) in place of Firebase Phone Auth.

## Phase 1 — Auth + Inventory (shipped)
- Mock-OTP registration / login (mobile + 4-digit PIN); bcrypt; 5-fail / 15-min lockout
- Seller inventory CRUD (10 unit types), soft delete
- Profile edit

## Phase 2 — Connections & Ordering (shipped)
- Buyer → SELLER-#### connection (Pending → Accept/Reject), 7-day Pending expiry
- Browse seller inventory, client-side cart (1 seller per cart)
- Order creation with min/increment/available validation; `ORD-#####` counter

## Phase 3 — Order Management (shipped)
- Statuses: Requested / Accepted / Rejected / Cancelled / Delivered / Expired
- Seller: accept, reject (mandatory reason), deliver
- Buyer: cancel from Requested or Accepted (optional reason); blocked otherwise
- 24h auto-expire of Requested orders (lazy on read)
- Click-to-call (`tel:`) on order detail

## Phase 4 — Inventory Reservation + Seller Availability (this phase)
### Inventory reservation
- `seller_items` now persists `reservedQuantity` (default 0); responses include derived `lowInventory: availableQuantity < 10`
- **Accept**: atomic claim → reserve each line with conditional `$inc` requiring `availableQuantity >= qty`; if any line fails, prior lines are rolled back and the order is reverted to Requested → 400 "Insufficient stock for ..."
- **Cancel from Accepted**: restore availableQuantity, decrease reservedQuantity
- **Cancel from Requested** / **Reject**: no inventory change (nothing was reserved)
- **Deliver from Accepted**: decrease reservedQuantity, keep availableQuantity reduced
- Race-safety: order status transitions use atomic `find_one_and_update` filtered on expected status (prevents double-accept)
- Negative inventory impossible — guaranteed by conditional update + rollback

### Low inventory alert
- Per-item: `Low` chip on Seller Inventory rows and Buyer Browse cards
- Dashboard: `Low inventory` tile + dedicated banner ("X items below 10. Restock from Inventory.")

### Seller availability
- `users.availabilityStatus`: `Open` (default) | `Closed`
- `PUT /api/seller/availability` body `{ status: "Open"|"Closed" }`
- Buyer browse is allowed regardless; the browse response includes `seller.availabilityStatus`
- Order placement blocked when seller is Closed → **400 "Seller currently unavailable."**
- Seller Dashboard has a Material 3 Switch to toggle Open/Closed in one tap

### Seller dashboard endpoint
`GET /api/seller/dashboard` → `{ activeItems, lowInventoryCount, pendingRequests, openOrders, lowInventoryThreshold: 10, availabilityStatus }`

## Data Model additions
- `seller_items.reservedQuantity` (number, default 0)
- `users.availabilityStatus` ("Open" | "Closed", default "Open")

## REST API additions
- `PUT /api/seller/availability`
- `GET /api/seller/dashboard`

## MOCKED (unchanged)
Firebase Phone OTP → fixed `123456` in `POST /api/auth/otp/send` and the register endpoints.

## Tests
- Phase 4: 23/23 backend
- Full regression: **99/99** backend tests (Phase 1: 26 + Phase 2: 24 + Phase 3: 26 + Phase 4: 23)
- Concurrency: simultaneous double-accept verified — exactly one 200, one 400, single reservation
