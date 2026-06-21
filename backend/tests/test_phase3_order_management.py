"""LocalOrders Phase 3 backend test suite — Order Management.

Covers:
  - POST /api/seller/orders/{id}/accept (Requested→Accepted, only owning seller, idempotency 400, 403 buyer)
  - POST /api/seller/orders/{id}/reject (mandatory reason, 422 empty/whitespace, sets timestamps + reason)
  - POST /api/seller/orders/{id}/deliver (only on Accepted, blocked otherwise)
  - POST /api/buyer/orders/{id}/cancel (Requested OR Accepted; reason optional;
    blocked on Delivered/Rejected/Expired; 403 seller)
  - Role / ownership guards on all transitions
  - 24h lazy auto-expiry (directly mutate requestedDateTime in Mongo)
  - GET /api/orders/{id} exposes the new timestamp & reason fields
  - Seller summary exposes mobileNumber (click-to-call) on /buyer/connections & /orders/{id}
  - No Mongo _id leakage
"""

import os
import random
import asyncio
import pytest
import requests
from datetime import datetime, timezone, timedelta

BASE_URL = os.environ.get(
    "EXPO_PUBLIC_BACKEND_URL",
    "https://local-orders-app.preview.emergentagent.com",
).rstrip("/")
API = f"{BASE_URL}/api"

OTP = "123456"
PIN = "1234"


def rand_mobile() -> str:
    return "9" + "".join(str(random.randint(0, 9)) for _ in range(9))


def assert_no_mongo_id(obj):
    if isinstance(obj, dict):
        assert "_id" not in obj, f"Mongo _id leaked in {obj}"
        for v in obj.values():
            assert_no_mongo_id(v)
    elif isinstance(obj, list):
        for v in obj:
            assert_no_mongo_id(v)


def auth_headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


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


def make_connected_pair(s):
    """Buyer+Seller with Accepted connection and one item."""
    b_token, b_user = register_buyer(s)
    s_token, s_user = register_seller(s)
    item = create_item(s, s_token)
    r = s.post(f"{API}/buyer/connections",
               json={"sellerCode": s_user["sellerCode"]},
               headers=auth_headers(b_token))
    cid = r.json()["connection"]["connectionId"]
    r2 = s.post(f"{API}/seller/connections/{cid}/accept", headers=auth_headers(s_token))
    assert r2.status_code == 200
    return {
        "b_token": b_token, "b_user": b_user,
        "s_token": s_token, "s_user": s_user,
        "item": item,
    }


def place_order(s, cp, qty=2.0):
    r = s.post(f"{API}/buyer/orders", json={
        "sellerId": cp["s_user"]["userId"],
        "items": [{"itemId": cp["item"]["itemId"], "quantity": qty}],
    }, headers=auth_headers(cp["b_token"]))
    assert r.status_code == 200, r.text
    return r.json()["order"]


@pytest.fixture(scope="session")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


# ===================== Accept =====================

class TestAcceptOrder:
    def test_accept_requested_then_idempotent_400(self, s):
        cp = make_connected_pair(s)
        order = place_order(s, cp)
        oid = order["orderId"]
        assert order["orderStatus"] == "Requested"
        assert order["acceptedDateTime"] is None

        r = s.post(f"{API}/seller/orders/{oid}/accept", headers=auth_headers(cp["s_token"]))
        assert r.status_code == 200, r.text
        body = r.json()
        assert_no_mongo_id(body)
        assert body["order"]["orderStatus"] == "Accepted"
        assert body["order"]["acceptedDateTime"]

        # Second accept must fail
        r2 = s.post(f"{API}/seller/orders/{oid}/accept", headers=auth_headers(cp["s_token"]))
        assert r2.status_code == 400

    def test_buyer_cannot_accept_403(self, s):
        cp = make_connected_pair(s)
        order = place_order(s, cp)
        r = s.post(f"{API}/seller/orders/{order['orderId']}/accept",
                   headers=auth_headers(cp["b_token"]))
        assert r.status_code == 403

    def test_other_seller_cannot_accept_403(self, s):
        cp = make_connected_pair(s)
        order = place_order(s, cp)
        rogue_token, _ = register_seller(s)
        r = s.post(f"{API}/seller/orders/{order['orderId']}/accept",
                   headers=auth_headers(rogue_token))
        assert r.status_code == 403


# ===================== Reject =====================

class TestRejectOrder:
    def test_reject_requires_reason_422_empty(self, s):
        cp = make_connected_pair(s)
        order = place_order(s, cp)
        r = s.post(f"{API}/seller/orders/{order['orderId']}/reject",
                   json={"reason": ""},
                   headers=auth_headers(cp["s_token"]))
        assert r.status_code == 422

    def test_reject_requires_reason_422_whitespace(self, s):
        cp = make_connected_pair(s)
        order = place_order(s, cp)
        r = s.post(f"{API}/seller/orders/{order['orderId']}/reject",
                   json={"reason": "   "},
                   headers=auth_headers(cp["s_token"]))
        assert r.status_code == 422

    def test_reject_requires_reason_422_missing(self, s):
        cp = make_connected_pair(s)
        order = place_order(s, cp)
        r = s.post(f"{API}/seller/orders/{order['orderId']}/reject",
                   json={}, headers=auth_headers(cp["s_token"]))
        assert r.status_code == 422

    def test_reject_success_sets_reason_and_timestamp(self, s):
        cp = make_connected_pair(s)
        order = place_order(s, cp)
        r = s.post(f"{API}/seller/orders/{order['orderId']}/reject",
                   json={"reason": "Out of stock"},
                   headers=auth_headers(cp["s_token"]))
        assert r.status_code == 200, r.text
        body = r.json()
        assert_no_mongo_id(body)
        o = body["order"]
        assert o["orderStatus"] == "Rejected"
        assert o["rejectedDateTime"]
        assert o["rejectionReason"] == "Out of stock"

    def test_reject_blocked_when_already_accepted(self, s):
        cp = make_connected_pair(s)
        order = place_order(s, cp)
        s.post(f"{API}/seller/orders/{order['orderId']}/accept",
               headers=auth_headers(cp["s_token"]))
        r = s.post(f"{API}/seller/orders/{order['orderId']}/reject",
                   json={"reason": "nope"},
                   headers=auth_headers(cp["s_token"]))
        assert r.status_code == 400

    def test_buyer_cannot_reject_403(self, s):
        cp = make_connected_pair(s)
        order = place_order(s, cp)
        r = s.post(f"{API}/seller/orders/{order['orderId']}/reject",
                   json={"reason": "x"},
                   headers=auth_headers(cp["b_token"]))
        assert r.status_code == 403


# ===================== Deliver =====================

class TestDeliverOrder:
    def test_deliver_only_after_accept(self, s):
        cp = make_connected_pair(s)
        order = place_order(s, cp)
        oid = order["orderId"]
        # cannot deliver from Requested
        r = s.post(f"{API}/seller/orders/{oid}/deliver",
                   headers=auth_headers(cp["s_token"]))
        assert r.status_code == 400

        # accept then deliver works
        s.post(f"{API}/seller/orders/{oid}/accept",
               headers=auth_headers(cp["s_token"]))
        r2 = s.post(f"{API}/seller/orders/{oid}/deliver",
                    headers=auth_headers(cp["s_token"]))
        assert r2.status_code == 200, r2.text
        body = r2.json()
        assert_no_mongo_id(body)
        assert body["order"]["orderStatus"] == "Delivered"
        assert body["order"]["deliveredDateTime"]

        # idempotent → 400
        r3 = s.post(f"{API}/seller/orders/{oid}/deliver",
                    headers=auth_headers(cp["s_token"]))
        assert r3.status_code == 400

    def test_deliver_blocked_after_reject(self, s):
        cp = make_connected_pair(s)
        order = place_order(s, cp)
        s.post(f"{API}/seller/orders/{order['orderId']}/reject",
               json={"reason": "nope"}, headers=auth_headers(cp["s_token"]))
        r = s.post(f"{API}/seller/orders/{order['orderId']}/deliver",
                   headers=auth_headers(cp["s_token"]))
        assert r.status_code == 400

    def test_buyer_cannot_deliver_403(self, s):
        cp = make_connected_pair(s)
        order = place_order(s, cp)
        s.post(f"{API}/seller/orders/{order['orderId']}/accept",
               headers=auth_headers(cp["s_token"]))
        r = s.post(f"{API}/seller/orders/{order['orderId']}/deliver",
                   headers=auth_headers(cp["b_token"]))
        assert r.status_code == 403

    def test_other_seller_cannot_deliver_403(self, s):
        cp = make_connected_pair(s)
        order = place_order(s, cp)
        s.post(f"{API}/seller/orders/{order['orderId']}/accept",
               headers=auth_headers(cp["s_token"]))
        rogue_token, _ = register_seller(s)
        r = s.post(f"{API}/seller/orders/{order['orderId']}/deliver",
                   headers=auth_headers(rogue_token))
        assert r.status_code == 403


# ===================== Cancel (buyer) =====================

class TestCancelOrder:
    def test_cancel_from_requested_no_reason(self, s):
        cp = make_connected_pair(s)
        order = place_order(s, cp)
        r = s.post(f"{API}/buyer/orders/{order['orderId']}/cancel",
                   json={}, headers=auth_headers(cp["b_token"]))
        assert r.status_code == 200, r.text
        body = r.json()
        assert_no_mongo_id(body)
        o = body["order"]
        assert o["orderStatus"] == "Cancelled"
        assert o["cancelledDateTime"]
        assert o["cancellationReason"] is None

    def test_cancel_from_accepted_with_reason(self, s):
        cp = make_connected_pair(s)
        order = place_order(s, cp)
        s.post(f"{API}/seller/orders/{order['orderId']}/accept",
               headers=auth_headers(cp["s_token"]))
        r = s.post(f"{API}/buyer/orders/{order['orderId']}/cancel",
                   json={"reason": "Changed my mind"},
                   headers=auth_headers(cp["b_token"]))
        assert r.status_code == 200, r.text
        o = r.json()["order"]
        assert o["orderStatus"] == "Cancelled"
        assert o["cancellationReason"] == "Changed my mind"

    def test_cancel_blocked_after_delivered(self, s):
        cp = make_connected_pair(s)
        order = place_order(s, cp)
        s.post(f"{API}/seller/orders/{order['orderId']}/accept",
               headers=auth_headers(cp["s_token"]))
        s.post(f"{API}/seller/orders/{order['orderId']}/deliver",
               headers=auth_headers(cp["s_token"]))
        r = s.post(f"{API}/buyer/orders/{order['orderId']}/cancel",
                   json={"reason": "late"},
                   headers=auth_headers(cp["b_token"]))
        assert r.status_code == 400

    def test_cancel_blocked_after_rejected(self, s):
        cp = make_connected_pair(s)
        order = place_order(s, cp)
        s.post(f"{API}/seller/orders/{order['orderId']}/reject",
               json={"reason": "no"}, headers=auth_headers(cp["s_token"]))
        r = s.post(f"{API}/buyer/orders/{order['orderId']}/cancel",
                   json={}, headers=auth_headers(cp["b_token"]))
        assert r.status_code == 400

    def test_seller_cannot_cancel_403(self, s):
        cp = make_connected_pair(s)
        order = place_order(s, cp)
        r = s.post(f"{API}/buyer/orders/{order['orderId']}/cancel",
                   json={}, headers=auth_headers(cp["s_token"]))
        assert r.status_code == 403

    def test_other_buyer_cannot_cancel_403(self, s):
        cp = make_connected_pair(s)
        order = place_order(s, cp)
        rogue_token, _ = register_buyer(s)
        r = s.post(f"{API}/buyer/orders/{order['orderId']}/cancel",
                   json={}, headers=auth_headers(rogue_token))
        assert r.status_code == 403


# ===================== 24h Auto Expiry =====================

async def _age_order(oid: str, hours_ago: int = 25):
    from motor.motor_asyncio import AsyncIOMotorClient
    cli = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    d = cli[os.environ.get("DB_NAME", "test_database")]
    old = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()
    res = await d.orders.update_one({"orderId": oid}, {"$set": {"requestedDateTime": old}})
    cli.close()
    assert res.modified_count == 1


class TestAutoExpiry:
    def test_expiry_on_seller_list(self, s):
        cp = make_connected_pair(s)
        order = place_order(s, cp)
        asyncio.run(_age_order(order["orderId"]))
        body = s.get(f"{API}/seller/orders", headers=auth_headers(cp["s_token"])).json()
        target = [o for o in body["orders"] if o["orderId"] == order["orderId"]]
        assert target, "order missing from seller list"
        assert target[0]["orderStatus"] == "Expired"
        assert target[0]["expiredDateTime"]

    def test_expiry_on_buyer_list(self, s):
        cp = make_connected_pair(s)
        order = place_order(s, cp)
        asyncio.run(_age_order(order["orderId"]))
        body = s.get(f"{API}/buyer/orders", headers=auth_headers(cp["b_token"])).json()
        target = [o for o in body["orders"] if o["orderId"] == order["orderId"]]
        assert target and target[0]["orderStatus"] == "Expired"

    def test_expiry_on_detail_then_actions_blocked(self, s):
        cp = make_connected_pair(s)
        order = place_order(s, cp)
        oid = order["orderId"]
        asyncio.run(_age_order(oid))

        # Detail flips status lazily
        det = s.get(f"{API}/orders/{oid}", headers=auth_headers(cp["s_token"]))
        assert det.status_code == 200
        body = det.json()
        assert_no_mongo_id(body)
        assert body["order"]["orderStatus"] == "Expired"
        assert body["order"]["expiredDateTime"]

        # All transitions must now return 400
        for path, tok, payload in [
            (f"/seller/orders/{oid}/accept", cp["s_token"], None),
            (f"/seller/orders/{oid}/reject", cp["s_token"], {"reason": "x"}),
            (f"/seller/orders/{oid}/deliver", cp["s_token"], None),
            (f"/buyer/orders/{oid}/cancel", cp["b_token"], {}),
        ]:
            r = s.post(f"{API}{path}", json=payload, headers=auth_headers(tok))
            assert r.status_code == 400, f"{path} got {r.status_code}: {r.text}"


# ===================== Order detail fields & mobileNumber exposure =====================

class TestOrderDetailFields:
    def test_detail_contains_phase3_fields(self, s):
        cp = make_connected_pair(s)
        order = place_order(s, cp)
        r = s.get(f"{API}/orders/{order['orderId']}", headers=auth_headers(cp["b_token"]))
        assert r.status_code == 200
        body = r.json()
        assert_no_mongo_id(body)
        o = body["order"]
        for k in ("acceptedDateTime", "rejectedDateTime", "cancelledDateTime",
                  "deliveredDateTime", "expiredDateTime",
                  "rejectionReason", "cancellationReason"):
            assert k in o, f"missing {k} in order detail"

    def test_seller_summary_has_mobileNumber_in_detail(self, s):
        cp = make_connected_pair(s)
        order = place_order(s, cp)
        r = s.get(f"{API}/orders/{order['orderId']}", headers=auth_headers(cp["b_token"]))
        assert r.status_code == 200
        cp_data = r.json()["counterparty"]
        assert "mobileNumber" in cp_data and cp_data["mobileNumber"], \
            "seller mobileNumber missing/empty in /orders/{id} for buyer"
        assert cp_data["mobileNumber"] == cp["s_user"]["mobileNumber"]

    def test_buyer_summary_has_mobileNumber_for_seller_view(self, s):
        cp = make_connected_pair(s)
        order = place_order(s, cp)
        r = s.get(f"{API}/orders/{order['orderId']}", headers=auth_headers(cp["s_token"]))
        assert r.status_code == 200
        cp_data = r.json()["counterparty"]
        assert "mobileNumber" in cp_data and cp_data["mobileNumber"], \
            "buyer mobileNumber missing/empty in /orders/{id} for seller"

    def test_seller_summary_has_mobileNumber_in_buyer_connections(self, s):
        cp = make_connected_pair(s)
        r = s.get(f"{API}/buyer/connections", headers=auth_headers(cp["b_token"]))
        assert r.status_code == 200
        conns = r.json()["connections"]
        assert conns, "no connections returned"
        for c in conns:
            if c.get("seller"):
                assert "mobileNumber" in c["seller"] and c["seller"]["mobileNumber"], \
                    "seller mobileNumber missing in /buyer/connections"
                break
        else:
            pytest.fail("No seller summary found on any buyer connection")
