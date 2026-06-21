# LocalOrders — Product Requirements (Phase 5 release candidate)

## Status
Phase 1-5 complete EXCEPT Firebase Phone Auth (deliberately deferred per user direction so
the APK can be tested with the existing mock OTP flow first).

## Stack
- Expo SDK 54 (React Native), expo-router, react-native-paper (Material Design 3)
- FastAPI + MongoDB (motor) backend
- expo-notifications + Emergent push relay (FCM/APNs) — wired but inactive until
  `google-services.json` + real `EMERGENT_PUSH_KEY` are supplied at deploy time
- Storage helpers: `@/src/utils/storage` (no direct AsyncStorage / SecureStore imports)
- @react-native-community/netinfo for offline detection

## Phases shipped
- **Phase 1** Auth: mock OTP `123456`, bcrypt PIN, JWT sessions, 5-attempt lockout
- **Phase 2** Buyer ↔ Seller connections by `SELLER-####` code (pending → accepted/rejected with 7-day expiry)
- **Phase 3** Order lifecycle: Requested → Accepted → Delivered + Reject/Cancel + 24h auto-expire
- **Phase 4** Inventory reservation (atomic find_one_and_update); seller availability Open/Closed; dashboard counts
- **Phase 5 (this release)**
  - **Notifications:** `notifications` MongoDB collection; in-app list with unread badge; bell in every screen header; mark-single-read & mark-all-read; events: connection request/accept/reject + order requested/accepted/rejected/cancelled/delivered.
  - **Push framework:** `/api/register-push` (auth-required), `notify_user()` helper persists & best-effort pushes. Tap deep-links to `/buyer-order-detail?orderId=...`. Awaits Firebase / google-services.json at deploy.
  - **Offline support:** Inventory, buyer orders, seller orders and notifications viewable when offline via per-user `lo.cache.*` storage; OfflineBanner across all screens; order placement / inventory mutations blocked with a friendly snackbar when offline.
  - **Settings:** Theme (Light / Dark / Follow System), About LocalOrders, Privacy Policy (all M3-styled, deep-link from Profile screen).
  - **Dark mode:** Custom MD3 light + dark palettes; runtime theme switching via `ThemePrefProvider`; persisted in storage.
  - **Polish:** consistent Appbar/Card/Chip styling, Snackbar for errors, RefreshControl pull-to-refresh on every list, MD3 colors throughout.

## API surface (additions in Phase 5)
- `POST /api/register-push` (auth) — register device push token under the calling user
- `GET  /api/notifications?limit=` (auth) — list + unread count
- `GET  /api/notifications/unread-count` (auth)
- `POST /api/notifications/{id}/read` (auth)
- `POST /api/notifications/read-all` (auth)

## Testing status
- Backend: **120/120 pytest** (99 regression + 21 new Phase 5 tests) — see
  `/app/test_reports/iteration_5.json`.
- Frontend: smoke-tested via Playwright screenshots (Home, Settings, Dark mode, About,
  Dashboard, Notifications). No frontend regressions.

## Release blockers / pre-APK to-do (next session)
1. Replace mock OTP with real Firebase Phone Auth (`expo-firebase-core` + service-account
   JSON or `@react-native-firebase/auth`).
2. Add `google-services.json` (Android) to repo root, plus `GoogleService-Info.plist` (iOS).
3. Build APK via Emergent **Publish** button → Android build with Firebase + push enabled.

## Test credentials
See `/app/memory/test_credentials.md`.
