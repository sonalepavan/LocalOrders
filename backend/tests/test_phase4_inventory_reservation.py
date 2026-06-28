"""LocalOrders Phase 4 — Inventory Reservation + Seller Availability.

Covers:
  - Seller availability default Open; PUT /seller/availability validation; /auth/me reflects status
  - Buyer order blocked when seller Closed (400 'Seller currently unavailable.')
    Browse still works and reflects availabilityStatus
  - item_public exposes reservedQuantity and lowInventory (avail < 10)
  - Accept reserves inventory atomically; double-accept 400
  - Accept fails on insufficient stock (no partial state, inventory unchanged on failure)
  - Concurrent double-accept: exactly one wins
  - Cancel from Accepted restores; Cancel from Requested unchanged
  - Reject from Requested unchanged
  - Deliver clears reservedQuantity, keeps availableQuantity reduced
  - Atomic claim: accepting Cancelled returns 400 with status-from-error (not stock)
  - No negative inventory across flows
  - GET /seller/dashboard fields
  - No Mongo _id leakage in Phase 4 responses
"""

import asyncio
import os
import random
from typing import Optional

import httpx
import pytest
import requests

BASE_URL = os.environ.get(
    "EXPO_PUBLIC_BACKEND_URL",
    "https://local-orders-app.preview.emergentagent.com",
).rstrip("/")
API = f"{BASE_URL}/api"

OTP = "123456"
PIN = "1234"


# ---------- helpers ----------

def rand_mobile() -> str:
    return "9" + "".join(str(random.randint(0, 9)) for _ in range(9))


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def assert_no_mongo_id(obj):
    if isinstance(obj, dict):
        assert "_id" not in obj, f"Mongo _id leaked in {obj}"
        for v in obj.values():
            assert_no_mongo_id(v)
    elif isinstance(obj, list):
        for v in obj:
            assert_no_mongo_id(v)


def register_buyer(s):
    mobile = rand_mobile()
    s.post(f"{API}/auth/otp/send", json={"mobileNumber": mobile, "userType": "buyer"})
    r = s.post(f"{API}/auth/register/buyer", json={
        "firstName": "TEST", "lastName": "Buyer",
        "mobileNumber": mobile, "address": "1 Lane", "pincode": "560001",
        "pin": PIN, "confirmPin": PIN, "otp": OTP,
    })
    assert r.status_code == 200, r.text
    return r.json()["token"], r.json()["user"]


def register_seller(s):
    mobile = rand_mobile()
    s.post(f"{API}/auth/otp/send", json={"mobileNumber": mobile, "userType": "seller"})
    r = s.post(f"{API}/auth/register/seller", json={
        "firstName": "TEST", "lastName": "Seller",
        "mobileNumber": mobile, "address": "2 Lane", "pincode": "560002",
        "pin": PIN, "confirmPin": PIN, "otp": OTP,
        "businessName": "TEST Biz",
    })
    assert r.status_code == 200, r.text
    return r.json()["token"], r.json()["user"]


def create_item(s, seller_token, **overrides):
    payload = {
        "itemName": "Tomato", "unitType": "Kg",
        "availableQuantity": 100.0, "pricePerUnit": 25.0,
        "minimumOrderQuantity": 2.0, "unitIncrement": 0.5,
    }
    payload.update(overrides)
    r = s.post(f"{API}/seller/items", json=payload, headers=auth_headers(seller_token))
    assert r.status_code == 200, r.text
    return r.json()["item"]


def make_connected_pair(s, item_kwargs: Optional[dict] = None):
    b_token, b_user = register_buyer(s)
    s_token, s_user = register_seller(s)
    item = create_item(s, s_token, **(item_kwargs or {}))
    r = s.post(f"{API}/buyer/connections",
               json={"sellerCode": s_user["sellerCode"]},
               headers=auth_headers(b_token))
    cid = r.json()["connection"]["connectionId"]
    r2 = s.post(f"{API}/seller/connections/{cid}/accept", headers=auth_headers(s_token))
    assert r2.status_code == 200
    return {"b_token": b_token, "b_user": b_user,
            "s_token": s_token, "s_user": s_user, "item": item}


def place_order(s, cp, qty=2.0, item_id=None):
    iid = item_id or cp["item"]["itemId"]
    r = s.post(f"{API}/buyer/orders", json={
        "sellerId": cp["s_user"]["userId"],
        "items": [{"itemId": iid, "quantity": qty}],
    }, headers=auth_headers(cp["b_token"]))
    assert r.status_code == 200, r.text
    return r.json()["order"]


def fetch_item(s, seller_token, item_id):
    r = s.get(f"{API}/seller/items", headers=auth_headers(seller_token))
    assert r.status_code == 200
    for it in r.json()["items"]:
        if it["itemId"] == item_id:
            return it
    raise AssertionError(f"Item {item_id} not found")


@pytest.fixture(scope="session")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


# ===================== Availability =====================

class TestSellerAvailability:
    def test_default_open_on_register(self, s):
        _, u = register_seller(s)
        assert u.get("availabilityStatus") == "Open"

    def test_set_closed_then_me_reflects(self, s):
        tok, _ = register_seller(s)
        r = s.put(f"{API}/seller/availability", json={"status": "Closed"},
                  headers=auth_headers(tok))
        assert r.status_code == 200, r.text
        body = r.json()
        assert_no_mongo_id(body)
        assert body["user"]["availabilityStatus"] == "Closed"

        me = s.get(f"{API}/auth/me", headers=auth_headers(tok)).json()
        assert me["user"]["availabilityStatus"] == "Closed"

    def test_set_open_again(self, s):
        tok, _ = register_seller(s)
        s.put(f"{API}/seller/availability", json={"status": "Closed"},
              headers=auth_headers(tok))
        r = s.put(f"{API}/seller/availability", json={"status": "Open"},
                  headers=auth_headers(tok))
        assert r.status_code == 200
        assert r.json()["user"]["availabilityStatus"] == "Open"

    def test_invalid_status_422(self, s):
        tok, _ = register_seller(s)
        r = s.put(f"{API}/seller/availability", json={"status": "Maybe"},
                  headers=auth_headers(tok))
        assert r.status_code == 422

    def test_buyer_cannot_set_availability_403(self, s):
        tok, _ = register_buyer(s)
        r = s.put(f"{API}/seller/availability", json={"status": "Closed"},
                  headers=auth_headers(tok))
        assert r.status_code == 403


class TestOrderBlockedWhenClosed:
    def test_order_blocked_when_closed(self, s):
        cp = make_connected_pair(s)
        # Close shop
        s.put(f"{API}/seller/availability", json={"status": "Closed"},
              headers=auth_headers(cp["s_token"]))
        r = s.post(f"{API}/buyer/orders", json={
            "sellerId": cp["s_user"]["userId"],
            "items": [{"itemId": cp["item"]["itemId"], "quantity": 2.0}],
        }, headers=auth_headers(cp["b_token"]))
        assert r.status_code == 400, r.text
        assert "Seller currently unavailable." in r.json().get("detail", "")

    def test_browse_succeeds_when_closed(self, s):
        cp = make_connected_pair(s)
        s.put(f"{API}/seller/availability", json={"status": "Closed"},
              headers=auth_headers(cp["s_token"]))
        r = s.get(f"{API}/buyer/sellers/{cp['s_user']['userId']}/items",
                  headers=auth_headers(cp["b_token"]))
        assert r.status_code == 200, r.text
        body = r.json()
        assert_no_mongo_id(body)
        assert body["seller"]["availabilityStatus"] == "Closed"
        assert isinstance(body["items"], list) and len(body["items"]) >= 1


# ===================== item_public exposes reservedQuantity + lowInventory =====================

class TestItemPublicFields:
    def test_item_initial_reserved_zero_low_false(self, s):
        tok, _ = register_seller(s)
        item = create_item(s, tok, availableQuantity=100.0)
        assert item["reservedQuantity"] == 0
        assert item["lowInventory"] is False

    def test_item_low_inventory_true_when_below_10(self, s):
        tok, _ = register_seller(s)
        item = create_item(s, tok, availableQuantity=5.0, minimumOrderQuantity=1.0,
                           unitIncrement=1.0)
        assert item["lowInventory"] is True
        assert item["reservedQuantity"] == 0

    def test_item_low_inventory_boundary_10_false(self, s):
        tok, _ = register_seller(s)
        item = create_item(s, tok, availableQuantity=10.0, minimumOrderQuantity=1.0,
                           unitIncrement=1.0)
        # strictly less than 10 → 10 is NOT low
        assert item["lowInventory"] is False


# ===================== Accept flow reserves inventory =====================

class TestAcceptReservesInventory:
    def test_accept_decreases_avail_increases_reserved(self, s):
        cp = make_connected_pair(s)
        order = place_order(s, cp, qty=10.0)
        r = s.post(f"{API}/seller/orders/{order['orderId']}/accept",
                   headers=auth_headers(cp["s_token"]))
        assert r.status_code == 200, r.text
        it = fetch_item(s, cp["s_token"], cp["item"]["itemId"])
        assert it["availableQuantity"] == 90.0
        assert it["reservedQuantity"] == 10.0

    def test_double_accept_returns_400(self, s):
        cp = make_connected_pair(s)
        order = place_order(s, cp, qty=5.0)
        r1 = s.post(f"{API}/seller/orders/{order['orderId']}/accept",
                    headers=auth_headers(cp["s_token"]))
        assert r1.status_code == 200
        r2 = s.post(f"{API}/seller/orders/{order['orderId']}/accept",
                    headers=auth_headers(cp["s_token"]))
        assert r2.status_code == 400
        # Inventory should reflect a single accept
        it = fetch_item(s, cp["s_token"], cp["item"]["itemId"])
        assert it["availableQuantity"] == 95.0
        assert it["reservedQuantity"] == 5.0

    def test_accept_insufficient_stock_no_partial_state(self, s):
        # stock 10, place two orders of 8 → accept first OK, second 400, state unchanged after fail.
        cp = make_connected_pair(s, item_kwargs={
            "availableQuantity": 10.0,
            "minimumOrderQuantity": 1.0,
            "unitIncrement": 1.0,
        })
        o1 = place_order(s, cp, qty=8.0)
        o2 = place_order(s, cp, qty=8.0)

        r1 = s.post(f"{API}/seller/orders/{o1['orderId']}/accept",
                    headers=auth_headers(cp["s_token"]))
        assert r1.status_code == 200, r1.text

        # snapshot inventory before failing accept
        before = fetch_item(s, cp["s_token"], cp["item"]["itemId"])
        assert before["availableQuantity"] == 2.0
        assert before["reservedQuantity"] == 8.0

        r2 = s.post(f"{API}/seller/orders/{o2['orderId']}/accept",
                    headers=auth_headers(cp["s_token"]))
        assert r2.status_code == 400
        assert "Insufficient stock" in r2.json().get("detail", ""), r2.text

        # Order 2 must remain Requested (no partial state)
        det = s.get(f"{API}/orders/{o2['orderId']}",
                    headers=auth_headers(cp["s_token"])).json()
        assert det["order"]["orderStatus"] == "Requested"
        assert det["order"]["acceptedDateTime"] is None

        # Inventory completely unchanged by failed accept
        after = fetch_item(s, cp["s_token"], cp["item"]["itemId"])
        assert after["availableQuantity"] == before["availableQuantity"]
        assert after["reservedQuantity"] == before["reservedQuantity"]


# ===================== Concurrent double-accept =====================

class TestConcurrentAccept:
    def test_concurrent_double_accept_only_one_wins(self, s):
        cp = make_connected_pair(s)
        order = place_order(s, cp, qty=4.0)
        url = f"{API}/seller/orders/{order['orderId']}/accept"
        headers = auth_headers(cp["s_token"])

        async def fire():
            async with httpx.AsyncClient(timeout=30.0) as client:
                return await asyncio.gather(
                    client.post(url, headers=headers),
                    client.post(url, headers=headers),
                )

        r1, r2 = asyncio.run(fire())
        codes = sorted([r1.status_code, r2.status_code])
        assert codes == [200, 400], f"Expected one 200 + one 400, got {codes}"

        it = fetch_item(s, cp["s_token"], cp["item"]["itemId"])
        # Single accept reflected
        assert it["availableQuantity"] == 96.0
        assert it["reservedQuantity"] == 4.0


# ===================== Cancel & Reject inventory semantics =====================

class TestCancelRejectInventory:
    def test_cancel_from_accepted_restores(self, s):
        cp = make_connected_pair(s)
        order = place_order(s, cp, qty=6.0)
        s.post(f"{API}/seller/orders/{order['orderId']}/accept",
               headers=auth_headers(cp["s_token"]))
        mid = fetch_item(s, cp["s_token"], cp["item"]["itemId"])
        assert mid["availableQuantity"] == 94.0 and mid["reservedQuantity"] == 6.0

        r = s.post(f"{API}/buyer/orders/{order['orderId']}/cancel",
                   json={}, headers=auth_headers(cp["b_token"]))
        assert r.status_code == 200, r.text
        after = fetch_item(s, cp["s_token"], cp["item"]["itemId"])
        assert after["availableQuantity"] == 100.0
        assert after["reservedQuantity"] == 0.0

    def test_cancel_from_requested_no_inventory_change(self, s):
        cp = make_connected_pair(s)
        order = place_order(s, cp, qty=6.0)
        before = fetch_item(s, cp["s_token"], cp["item"]["itemId"])
        r = s.post(f"{API}/buyer/orders/{order['orderId']}/cancel",
                   json={}, headers=auth_headers(cp["b_token"]))
        assert r.status_code == 200
        after = fetch_item(s, cp["s_token"], cp["item"]["itemId"])
        assert after["availableQuantity"] == before["availableQuantity"]
        assert after["reservedQuantity"] == before["reservedQuantity"]

    def test_reject_from_requested_no_inventory_change(self, s):
        cp = make_connected_pair(s)
        order = place_order(s, cp, qty=6.0)
        before = fetch_item(s, cp["s_token"], cp["item"]["itemId"])
        r = s.post(f"{API}/seller/orders/{order['orderId']}/reject",
                   json={"reason": "no"}, headers=auth_headers(cp["s_token"]))
        assert r.status_code == 200
        after = fetch_item(s, cp["s_token"], cp["item"]["itemId"])
        assert after["availableQuantity"] == before["availableQuantity"]
        assert after["reservedQuantity"] == before["reservedQuantity"]


# ===================== Deliver =====================

class TestDeliverInventory:
    def test_deliver_clears_reserved_keeps_avail_reduced(self, s):
        cp = make_connected_pair(s)
        order = place_order(s, cp, qty=7.0)
        s.post(f"{API}/seller/orders/{order['orderId']}/accept",
               headers=auth_headers(cp["s_token"]))
        mid = fetch_item(s, cp["s_token"], cp["item"]["itemId"])
        assert mid["availableQuantity"] == 93.0 and mid["reservedQuantity"] == 7.0

        r = s.post(f"{API}/seller/orders/{order['orderId']}/deliver",
                   headers=auth_headers(cp["s_token"]))
        assert r.status_code == 200, r.text
        after = fetch_item(s, cp["s_token"], cp["item"]["itemId"])
        assert after["availableQuantity"] == 93.0
        assert after["reservedQuantity"] == 0.0


# ===================== Atomic claim on stale status =====================

class TestAtomicStatusClaim:
    def test_accept_cancelled_returns_status_error_not_stock(self, s):
        cp = make_connected_pair(s)
        order = place_order(s, cp, qty=3.0)
        # buyer cancels while Requested
        s.post(f"{API}/buyer/orders/{order['orderId']}/cancel",
               json={}, headers=auth_headers(cp["b_token"]))
        r = s.post(f"{API}/seller/orders/{order['orderId']}/accept",
                   headers=auth_headers(cp["s_token"]))
        assert r.status_code == 400
        detail = r.json().get("detail", "")
        assert "Cancelled" in detail and "Accepted" in detail, detail
        assert "Insufficient stock" not in detail


# ===================== Negative inventory invariant =====================

class TestNoNegativeInventory:
    def test_invariant_after_mixed_flows(self, s):
        cp = make_connected_pair(s, item_kwargs={
            "availableQuantity": 10.0,
            "minimumOrderQuantity": 1.0,
            "unitIncrement": 1.0,
        })
        # Accept then cancel
        o1 = place_order(s, cp, qty=4.0)
        s.post(f"{API}/seller/orders/{o1['orderId']}/accept",
               headers=auth_headers(cp["s_token"]))
        s.post(f"{API}/buyer/orders/{o1['orderId']}/cancel",
               json={}, headers=auth_headers(cp["b_token"]))
        # Accept then deliver
        o2 = place_order(s, cp, qty=3.0)
        s.post(f"{API}/seller/orders/{o2['orderId']}/accept",
               headers=auth_headers(cp["s_token"]))
        s.post(f"{API}/seller/orders/{o2['orderId']}/deliver",
               headers=auth_headers(cp["s_token"]))
        # Race-failing accept: two requested orders both within current avail, but
        # together exceed it → second accept must 400 without producing negative inventory.
        o3 = place_order(s, cp, qty=5.0)  # avail=7, ok
        o4 = place_order(s, cp, qty=5.0)  # avail=7, ok
        r3 = s.post(f"{API}/seller/orders/{o3['orderId']}/accept",
                    headers=auth_headers(cp["s_token"]))
        assert r3.status_code == 200, r3.text
        r4 = s.post(f"{API}/seller/orders/{o4['orderId']}/accept",
                    headers=auth_headers(cp["s_token"]))
        assert r4.status_code == 400, r4.text

        it = fetch_item(s, cp["s_token"], cp["item"]["itemId"])
        assert it["availableQuantity"] >= 0, it
        assert it["reservedQuantity"] >= 0, it
        # Net: started 10, delivered 3, reserved 5 → avail 2, reserved 5
        assert it["availableQuantity"] == 2.0
        assert it["reservedQuantity"] == 5.0


# ===================== Seller dashboard =====================

class TestSellerDashboard:
    def test_dashboard_fields_and_no_id_leak(self, s):
        s_token, s_user = register_seller(s)
        # 2 items, one low (<10)
        create_item(s, s_token, availableQuantity=50.0)
        create_item(s, s_token, itemName="Onion", availableQuantity=5.0,
                    minimumOrderQuantity=1.0, unitIncrement=1.0)

        r = s.get(f"{API}/seller/dashboard", headers=auth_headers(s_token))
        assert r.status_code == 200, r.text
        body = r.json()
        assert_no_mongo_id(body)
        for k in ("activeItems", "lowInventoryCount", "pendingRequests",
                  "openOrders", "lowInventoryThreshold", "availabilityStatus"):
            assert k in body, f"missing {k} in dashboard"
        assert body["lowInventoryThreshold"] == 10
        assert body["activeItems"] >= 2
        assert body["lowInventoryCount"] >= 1
        assert body["availabilityStatus"] in ("Open", "Closed")

    def test_dashboard_open_orders_counts_requested_and_accepted(self, s):
        cp = make_connected_pair(s)
        place_order(s, cp, qty=2.0)
        o2 = place_order(s, cp, qty=2.0)
        s.post(f"{API}/seller/orders/{o2['orderId']}/accept",
               headers=auth_headers(cp["s_token"]))
        body = s.get(f"{API}/seller/dashboard",
                     headers=auth_headers(cp["s_token"])).json()
        assert body["openOrders"] >= 2

    def test_buyer_cannot_view_dashboard_403(self, s):
        tok, _ = register_buyer(s)
        r = s.get(f"{API}/seller/dashboard", headers=auth_headers(tok))
        assert r.status_code == 403
