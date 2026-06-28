# LocalOrders — Project Handover Document

**Version:** Phase 1 → 4 shipped · **Phase 5 pending**
**Last updated:** 2026-06-20
**Status:** Backend 99/99 tests green · Frontend bundles cleanly · Preview live

---

## 1. Current Architecture

### 1.1 High-level

```
┌─────────────────────────────┐        HTTPS (ingress)
│  Expo / React Native (web   │  ───────────────────────►  ┌──────────────────────┐
│  preview + Expo Go QR)      │       /api/*  → :8001       │  FastAPI (Uvicorn)   │
│  · expo-router               │       /*      → :3000       │  /api/...            │
│  · react-native-paper (MD3)  │                             │  bcrypt PINs         │
│  · expo-secure-store         │                             │  JWT (HS256, 30d)    │
│  · client-side cart (JSON)   │                             │  Motor (async Mongo) │
└─────────────────────────────┘                             └──────────┬───────────┘
                                                                       │
                                                            mongodb://localhost:27017
                                                                       │
                                                            ┌──────────▼───────────┐
                                                            │  MongoDB (standalone)│
                                                            │  Firestore-shaped    │
                                                            │  collections         │
                                                            └──────────────────────┘
```

### 1.2 Process layout (Supervisor)

| Process  | Port | Command                                       |
|----------|------|-----------------------------------------------|
| `expo`   | 3000 | `yarn expo start --port 3000` (Metro bundler) |
| `backend`| 8001 | `uvicorn server:app --host 0.0.0.0 --port 8001 --reload` |
| `mongo`  | 27017| Local MongoDB                                  |

All external traffic enters via Kubernetes ingress:
- `/api/*` → backend `:8001`
- `/*` → expo metro `:3000`

### 1.3 Frontend route map (expo-router file-based)

```
app/
├── _layout.tsx                    # PaperProvider + SafeAreaProvider + AuthProvider
├── index.tsx                      # Home (3 buttons) + auto-login redirect
├── login.tsx                      # Mobile + 4-digit PIN
├── register-buyer.tsx             # Buyer form → OTP screen
├── register-seller.tsx            # Seller form → OTP screen
├── otp.tsx                        # 6-digit OTP (mock = 123456)
├── (buyer)/                       # Buyer bottom tabs
│   ├── _layout.tsx
│   ├── home.tsx                   # Sellers dashboard
│   ├── orders.tsx                 # My Orders
│   └── profile.tsx
├── (seller)/                      # Seller bottom tabs
│   ├── _layout.tsx
│   ├── dashboard.tsx              # Availability switch + tiles + low-inv banner
│   ├── inventory.tsx              # CRUD + Low chip + reserved
│   ├── requests.tsx               # Pending/Accepted/Rejected connections
│   ├── orders.tsx                 # Incoming orders
│   └── profile.tsx
├── buyer-add-seller.tsx           # Connect via SELLER-#### code
├── buyer-seller-items.tsx         # Browse + add to cart (banner when Closed)
├── buyer-cart.tsx                 # Cart + place order
├── buyer-order-detail.tsx         # Shared order detail (buyer + seller)
├── seller-add-item.tsx
└── seller-edit-item.tsx

src/
├── lib/
│   ├── api.ts                     # Typed REST client
│   ├── auth-context.tsx           # Session + auto-login
│   ├── cart.ts                    # Client-side cart (storage)
│   └── theme.ts                   # MD3 light/dark
├── components/
│   ├── RegistrationForm.tsx       # Shared by buyer + seller registration
│   ├── ProfileScreen.tsx          # Shared by both roles
│   └── ItemForm.tsx               # Shared by add/edit item
└── utils/storage/                 # Pre-shipped key-value storage (secureSet/get)
```

### 1.4 Backend layout

Single file: `/app/backend/server.py` (~1080 lines). Sections (top → bottom):

1. Config / helpers (`hash_pin`, `make_token`, `next_seller_code`, `next_order_number`)
2. Pydantic request models
3. Auth routes (`/auth/*`)
4. Profile (`/users/me`)
5. Seller inventory (`/seller/items/*`)
6. **Phase 4** seller availability + dashboard (`/seller/availability`, `/seller/dashboard`)
7. **Phase 2** connections (`/buyer/connections`, `/seller/connections/*`)
8. **Phase 2** buyer browse (`/buyer/sellers/{id}/items`)
9. Orders (`/buyer/orders`, `/seller/orders`, `/orders/{id}`)
10. **Phase 3 + 4** order management (`accept`, `reject`, `deliver`, `cancel`) with race-safe atomic `find_one_and_update`, inventory reservation, and rollback

---

## 2. Database Schema (MongoDB — Firestore-equivalent)

All documents use **string `userId` / `itemId` / `orderId` / `connectionId`** (`uuid4`). MongoDB's internal `_id` is never returned over the wire (verified by automated `_id` scanner).

### 2.1 `users`
| Field                | Type             | Notes                                                |
|----------------------|------------------|------------------------------------------------------|
| `userId`             | string (uuid4)   | PK                                                   |
| `userType`           | "buyer" \| "seller" |                                                   |
| `firstName`          | string           |                                                      |
| `lastName`           | string           |                                                      |
| `mobileNumber`       | string (digits)  | **unique**                                           |
| `address`            | string           |                                                      |
| `pincode`            | string           |                                                      |
| `businessName`       | string \| null   | sellers only                                         |
| `sellerCode`         | string \| null   | sellers only, `SELLER-#####` from counter ≥ 1001     |
| `availabilityStatus` | "Open" \| "Closed" | **Phase 4**, sellers only, default `"Open"`       |
| `isMobileVerified`   | bool             | always true after OTP                                |
| `pinHash`            | string           | bcrypt; never returned                               |
| `failedAttempts`     | int              | reset on success, lock at 5                          |
| `lockedUntil`        | ISO string \| null | 15-min lockout                                     |
| `createdDate`        | ISO string       | UTC                                                  |

### 2.2 `seller_items`
| Field                | Type             | Notes                                                |
|----------------------|------------------|------------------------------------------------------|
| `itemId`             | string (uuid4)   | PK                                                   |
| `sellerId`           | string           | FK → users.userId                                    |
| `itemName`           | string           |                                                      |
| `unitType`           | enum (10 values) | Piece, Bottle, Packet, Kg, Gram, Litre, ml, Dozen, Can, Box |
| `availableQuantity`  | number           |                                                      |
| `reservedQuantity`   | number           | **Phase 4**, default 0                               |
| `pricePerUnit`       | number           |                                                      |
| `minimumOrderQuantity` | number         |                                                      |
| `unitIncrement`      | number           |                                                      |
| `isActive`           | bool             | soft delete                                          |
| `createdDate` / `updatedDate` | ISO string |                                                    |

Derived (in API responses, not stored): `lowInventory: availableQuantity < 10`.

### 2.3 `buyer_seller_connections`
| Field               | Type            | Notes                                         |
|---------------------|-----------------|-----------------------------------------------|
| `connectionId`      | string (uuid4)  | PK                                            |
| `buyerId`           | string          | FK → users                                    |
| `sellerId`          | string          | FK → users                                    |
| `status`            | enum            | Pending \| Accepted \| Rejected \| Expired    |
| `requestedDateTime` | ISO string      |                                               |
| `approvedDateTime`  | ISO string \| null |                                            |

**Lazy expiry**: Pending older than **7 days** flipped to `Expired` on every list-read.

### 2.4 `orders`
| Field               | Type           | Notes                                          |
|---------------------|----------------|------------------------------------------------|
| `orderId`           | string (uuid4) | PK                                             |
| `orderNumber`       | string         | `ORD-#####` from counter ≥ 100001              |
| `buyerId`           | string         |                                                |
| `sellerId`          | string         |                                                |
| `orderStatus`       | enum           | Requested \| Accepted \| Rejected \| Cancelled \| Delivered \| Expired |
| `totalAmount`       | number         | server-computed                                |
| `requestedDateTime` | ISO            |                                                |
| `acceptedDateTime`  | ISO \| null    | Phase 3                                        |
| `rejectedDateTime`  | ISO \| null    | Phase 3                                        |
| `cancelledDateTime` | ISO \| null    | Phase 3                                        |
| `deliveredDateTime` | ISO \| null    | Phase 3                                        |
| `expiredDateTime`   | ISO \| null    | Phase 3 (24h auto-expire on Requested)         |
| `rejectionReason`   | string \| null | required when status flips to Rejected         |
| `cancellationReason`| string \| null | optional                                       |

### 2.5 `order_items`
| Field              | Type           | Notes                                        |
|--------------------|----------------|----------------------------------------------|
| `orderItemId`      | string (uuid4) | PK                                           |
| `orderId`          | string         | FK                                           |
| `itemId`           | string         | FK at the time of order                      |
| `itemName`         | string         | snapshot                                     |
| `quantity`         | number         |                                              |
| `unitType`         | string         | snapshot                                     |
| `pricePerUnit`     | number         | snapshot                                     |
| `itemTotal`        | number         | `qty * pricePerUnit`                         |

### 2.6 `counters`
- `{ "_id": "seller_code", "seq": int }` (≥ 1001 baseline)
- `{ "_id": "order_number", "seq": int }` (≥ 100001 baseline)

### 2.7 Recommended indexes (not yet applied — pre-prod task)
```js
db.users.createIndex({ mobileNumber: 1 }, { unique: true })
db.users.createIndex({ sellerCode: 1 }, { unique: true, sparse: true })
db.seller_items.createIndex({ sellerId: 1, isActive: 1 })
db.buyer_seller_connections.createIndex({ buyerId: 1, sellerId: 1 })
db.buyer_seller_connections.createIndex({ status: 1, requestedDateTime: 1 })
db.orders.createIndex({ buyerId: 1, requestedDateTime: -1 })
db.orders.createIndex({ sellerId: 1, requestedDateTime: -1 })
db.orders.createIndex({ orderStatus: 1, requestedDateTime: 1 })   // for 24h expiry sweep
db.order_items.createIndex({ orderId: 1 })
```

---

## 3. API Endpoints

All routes are prefixed with `/api`. Auth = `Authorization: Bearer <JWT>`.

### 3.1 Auth & profile
| Method | Path                              | Auth | Description                                |
|--------|-----------------------------------|------|--------------------------------------------|
| GET    | `/`                               | —    | Service heartbeat                          |
| GET    | `/meta/unit-types`                | —    | List of 10 allowed unit types              |
| POST   | `/auth/otp/send`                  | —    | **MOCK** — always returns `123456`         |
| POST   | `/auth/register/buyer`            | —    | OTP-verify + create buyer                  |
| POST   | `/auth/register/seller`           | —    | OTP-verify + create seller + seller code   |
| POST   | `/auth/login`                     | —    | Mobile + PIN; 5-fail lockout               |
| GET    | `/auth/me`                        | ✓    | Auto-login                                 |
| POST   | `/auth/logout`                    | ✓    | Stateless (client drops token)             |
| PUT    | `/users/me`                       | ✓    | Edit name, address, businessName (seller)  |

### 3.2 Seller inventory & availability
| Method | Path                              | Auth | Description                                |
|--------|-----------------------------------|------|--------------------------------------------|
| GET    | `/seller/items?include_inactive=` | seller | List own items                           |
| POST   | `/seller/items`                   | seller | Create item                              |
| PUT    | `/seller/items/{id}`              | seller | Edit item                                |
| DELETE | `/seller/items/{id}`              | seller | **Soft** delete (`isActive=false`)       |
| PUT    | `/seller/availability`            | seller | **Phase 4** body `{ status: "Open"\|"Closed" }` |
| GET    | `/seller/dashboard`               | seller | **Phase 4** counts + low-inv threshold   |

### 3.3 Connections
| Method | Path                                     | Auth   | Description                          |
|--------|------------------------------------------|--------|--------------------------------------|
| POST   | `/buyer/connections`                     | buyer  | body `{ sellerCode }`                |
| GET    | `/buyer/connections?status=`             | buyer  | with seller summaries                |
| GET    | `/seller/connections?status=`            | seller | with buyer summaries                 |
| POST   | `/seller/connections/{id}/accept`        | seller |                                      |
| POST   | `/seller/connections/{id}/reject`        | seller |                                      |

### 3.4 Buyer browse & orders
| Method | Path                                            | Auth   | Description                              |
|--------|-------------------------------------------------|--------|------------------------------------------|
| GET    | `/buyer/sellers/{sellerId}/items?q=`            | buyer  | only if connection Accepted              |
| POST   | `/buyer/orders`                                 | buyer  | body `{ sellerId, items[{itemId, quantity}] }` — blocks if seller is Closed |
| GET    | `/buyer/orders`                                 | buyer  |                                          |
| GET    | `/seller/orders`                                | seller |                                          |
| GET    | `/orders/{id}`                                  | either party | with items + counterparty            |

### 3.5 Order management (Phase 3 + 4)
| Method | Path                                       | Auth   | Notes                                                |
|--------|--------------------------------------------|--------|------------------------------------------------------|
| POST   | `/seller/orders/{id}/accept`               | seller | atomic claim + inventory reservation; 400 if insufficient stock |
| POST   | `/seller/orders/{id}/reject`               | seller | body `{ reason }` **mandatory**                      |
| POST   | `/seller/orders/{id}/deliver`              | seller | clears `reservedQuantity`                            |
| POST   | `/buyer/orders/{id}/cancel`                | buyer  | body `{ reason? }`; restores inventory if was Accepted |

### 3.6 Standard error shapes
- `400` — validation / state transition / insufficient stock / seller Closed
- `401` — missing/invalid JWT, wrong PIN (with remaining-attempts hint)
- `403` — role/ownership mismatch
- `404` — entity not found
- `409` — duplicate (mobile, duplicate connection)
- `422` — Pydantic validation (e.g. empty reject reason)
- `423` — account locked

---

## 4. Environment Variables

### 4.1 `/app/backend/.env`
| Variable      | Purpose                                                | Required |
|---------------|--------------------------------------------------------|----------|
| `MONGO_URL`   | `mongodb://localhost:27017` (do NOT change in pod)     | ✓ |
| `DB_NAME`     | e.g. `test_database`                                   | ✓ |
| `CORS_ORIGINS`| Comma-separated (placeholder; CORS currently `*`)      | optional |
| `JWT_SECRET`  | HS256 secret for JWT signing — **change for prod**     | ✓ (defaulted, must rotate) |

### 4.2 `/app/frontend/.env`
| Variable                  | Purpose                                                       | Don't modify |
|---------------------------|---------------------------------------------------------------|--------------|
| `EXPO_PUBLIC_BACKEND_URL` | Public preview URL → `/api/*` ingress                         | — (read in code) |
| `EXPO_PACKAGER_PROXY_URL` | Metro proxy URL for QR previews                              | **protected** |
| `EXPO_PACKAGER_HOSTNAME`  | Metro hostname for QR previews                               | **protected** |

### 4.3 Phase 5 (Firebase) — to be added later (see §7)
| Variable                    | Purpose                                              |
|-----------------------------|------------------------------------------------------|
| `FIREBASE_PROJECT_ID`       | Firebase Admin (server-side ID-token verification)   |
| `FIREBASE_SERVICE_ACCOUNT_JSON` | Base64-encoded service-account JSON               |
| `EXPO_PUBLIC_FIREBASE_API_KEY` | Web-API-key (for OTP via `@react-native-firebase/auth` or REST) |
| `EXPO_PUBLIC_FIREBASE_AUTH_DOMAIN` | e.g. `localorders-xxxx.firebaseapp.com`       |
| `EXPO_PUBLIC_FIREBASE_PROJECT_ID` | same as above                                  |
| `EXPO_PUBLIC_FIREBASE_APP_ID` | required by JS SDK                                |

---

## 5. Pending Phase 5 Tasks

Phase 5 is the production-readiness milestone — primarily swapping the mocked OTP for real Firebase and tying up known gaps.

### 5.1 Replace mock OTP with Firebase Phone Auth (P0)
- Client: integrate `@react-native-firebase/auth` (or Expo Firebase JS SDK) for `signInWithPhoneNumber` flow.
- Server: verify Firebase ID token in `register/*` payloads via `firebase-admin` SDK; the JWT we mint stays the same.
- Code touchpoints:
  - Backend `/app/backend/server.py` → `_register()` mock-OTP check
  - Backend `/app/backend/server.py` → `/api/auth/otp/send` (delete or keep as no-op for legacy clients)
  - Frontend `src/lib/api.ts` → `sendOtp` / `register*` payloads
  - Frontend `app/otp.tsx` → swap input for the `confirmationResult.confirm(code)` callback

### 5.2 Mobile-number change with OTP re-verify (P1)
Spec already says: *"Changing mobile number requires OTP verification."* Currently disabled in the UI. Add:
- `POST /api/users/me/mobile/start` → sends OTP to NEW number
- `POST /api/users/me/mobile/confirm` → verifies + atomic-updates `mobileNumber`

### 5.3 Order status notifications (P1, on user request)
Push notifications via Expo / Emergent-managed push when order status changes (Accept/Reject/Deliver/Cancel/Expired). Per project rules this is **only built upon explicit user request** — do not implement proactively.

### 5.4 Operational polish (P2)
- Add the MongoDB indexes in §2.7 to a one-shot migration script.
- Convert per-line `update_one` calls in `_reserve_inventory` / `_restore_inventory` / `_clear_reservation` to `bulk_write` for multi-line orders.
- Split `server.py` into routers (`routers/auth.py`, `routers/inventory.py`, `routers/orders.py`).
- Add periodic background sweep (APScheduler) to **eagerly** expire 7-day connections and 24h orders rather than lazy-on-read (current lazy path is correct but adds slight latency on list reads).
- Rotate `JWT_SECRET` to a strong, env-managed value before production.

### 5.5 Frontend polish (P2)
- Skeleton loaders for inventory / orders lists.
- Pull-to-refresh wired on every list (currently on most).
- Empty-state illustrations.
- Localization scaffold (i18n) — currently English/INR only.

### 5.6 Out-of-scope features previously discussed (P3, opt-in)
- Stock auto-decrement on delivery only (already correct), but a "restock reminder" home banner.
- Buyer-side seller search by **business name** (currently search is by code).
- Order rating / review.

---

## 6. Build Instructions

### 6.1 Local dev (this preview pod)
Services run under Supervisor and reload on file changes:
```bash
sudo supervisorctl status                # expo, backend, mongo
sudo supervisorctl restart expo
sudo supervisorctl restart backend
tail -n 100 /var/log/supervisor/backend.err.log
```

### 6.2 Backend
```bash
cd /app/backend
pip install -r requirements.txt
# .env must define MONGO_URL, DB_NAME, JWT_SECRET
uvicorn server:app --host 0.0.0.0 --port 8001 --reload
```

### 6.3 Frontend
```bash
cd /app/frontend
yarn install                # respects packageManager in package.json
yarn expo start --port 3000 # dev
# Tests / lint
yarn lint
```

### 6.4 Mobile builds (recommended path)
Use Emergent's built-in publish flow:
1. **Publish** button (top-right of the editor) → Emergent generates iOS / Android builds.
2. For Phase 5 Firebase OTP you must upload `google-services.json` (Android) and `GoogleService-Info.plist` (iOS) — see §7.
3. Do not set up EAS CLI / external Expo accounts; use the platform publish flow.

### 6.5 Test suite
```bash
cd /app/backend
pytest /app/backend/tests -v
# Current totals: 99/99 passing
```

### 6.6 Lint
```bash
# Backend
cd /app/backend && python -m ruff check .
# Frontend
cd /app/frontend && yarn lint
```

---

## 7. Firebase Setup Requirements (for Phase 5)

### 7.1 Firebase Console
1. Create a project at https://console.firebase.google.com (e.g. `LocalOrders-prod`).
2. **Authentication → Sign-in method → enable Phone**.
3. Add Android app: package name `com.localorders.app` (or your final package). Download `google-services.json`.
4. Add iOS app: bundle ID `com.localorders.app`. Download `GoogleService-Info.plist`.
5. **Project Settings → Service accounts → Generate new private key** → save the JSON (this is the **server** credential).

### 7.2 Files to place
| File                                | Destination                          | Purpose                            |
|-------------------------------------|--------------------------------------|------------------------------------|
| `google-services.json`              | `/app/frontend/google-services.json` | Android Firebase config            |
| `GoogleService-Info.plist`          | `/app/frontend/GoogleService-Info.plist` | iOS Firebase config            |
| service-account JSON (server)       | Stored as `FIREBASE_SERVICE_ACCOUNT_JSON` (base64) in `/app/backend/.env` | Admin SDK |

### 7.3 Code wiring (Phase 5 work)
Frontend:
```bash
yarn expo install @react-native-firebase/app @react-native-firebase/auth
# app.json plugins:
#   "@react-native-firebase/app",
#   ["expo-build-properties", { "ios": { "useFrameworks": "static" } }]
```

```ts
// app/otp.tsx (excerpt)
import auth from '@react-native-firebase/auth';
const confirmation = await auth().signInWithPhoneNumber('+91' + mobile);
await confirmation.confirm(otp);                // throws on wrong OTP
const idToken = await auth().currentUser!.getIdToken();
// POST /api/auth/register/{role} with { ...form, firebaseIdToken: idToken }
```

Backend (`server.py`):
```python
import firebase_admin
from firebase_admin import auth as fbauth, credentials
cred = credentials.Certificate(json.loads(base64.b64decode(os.environ['FIREBASE_SERVICE_ACCOUNT_JSON'])))
firebase_admin.initialize_app(cred)

# In _register():
decoded = fbauth.verify_id_token(payload['firebaseIdToken'])
if decoded['phone_number'].lstrip('+') != normalize_mobile(payload['mobileNumber']):
    raise HTTPException(400, "OTP phone does not match registration mobile")
```

### 7.4 Firestore (optional swap)
The current MongoDB collections were intentionally named/shaped to mirror Firestore. If you later choose to use Firestore for data (not just auth):
- Replace each `db.<collection>.<op>(...)` call with the matching `firestore.client().collection(...)` calls.
- Use Firestore Transactions (`@firestore.transactional`) for inventory reservation — the same logic in `_reserve_inventory` maps 1:1.
- Indexes will need to be declared in `firestore.indexes.json`.

### 7.5 Known constraints
- Firebase Phone OTP **does not work inside Expo Go**. You must build a development/production binary (Section 6.4) to test it end-to-end.
- The mock OTP `123456` continues to be useful for automated tests — keep the mock path behind an env flag (`MOCK_OTP_ENABLED=true`) if you want to retain it in CI.

---

## Appendix A — Test credentials (mock OTP)

See `/app/memory/test_credentials.md`. Summary:
- OTP code: **`123456`**
- Any unique 10-digit mobile number registers a fresh account.

## Appendix B — File-level "do not touch" list
- `/app/frontend/.env` keys `EXPO_PACKAGER_PROXY_URL`, `EXPO_PACKAGER_HOSTNAME`
- `/app/backend/.env` key `MONGO_URL`
- `/app/frontend/metro.config.js`
- `/app/frontend/app/_layout.tsx` icon-prewarm logic
