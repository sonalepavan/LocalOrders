"""LocalOrders Phase 2 backend test suite.

Covers buyer-seller connections, buyer browse, and order creation.

  - POST /api/buyer/connections (create / 404 invalid code / 409 duplicate / 403 seller-not-buyer)
  - GET /api/buyer/connections and /api/seller/connections (own scope, summaries, no _id)
  - POST /api/seller/connections/{id}/accept|reject (target seller only, idempotency 400)
  - Pending expiry: directly age requestedDateTime >7d then GET sees 'Expired'
  - GET /api/buyer/sellers/{sellerId}/items (Accepted required, ?q= search, only active)
  - POST /api/buyer/orders (no connection 403, qty < min / not aligned / > available all 400)
  - Valid order: status='Requested', orderNumber 'ORD-#####', totals correct, order_items persist
  - GET /api/buyer/orders and /api/seller/orders show counterpart summaries
  - GET /api/orders/{id}: 200 for buyer & seller, 403 for unrelated third user
  - No Mongo _id leakage in any new endpoint
"""

import os
import re
import random
import asyncio
import pytest
import requests
from datetime import datetime, timezone, timedelta

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://local-orders-app.preview.emergentagent.com").rstrip("/")
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


# ---------- helpers ----------

def register_buyer(s):
    mobile = rand_mobile()
    s.post(f"{API}/auth/otp/send", json={"mobileNumber": mobile, "userType": "buyer"})
    r = s.post(f"{API}/auth/register/buyer", json={
        "firstName": "TEST", "lastName": "Buyer",
        "mobileNumber": mobile, "address": "1 Lane", "pincode": "560001",
        "pin": PIN, "confirmPin": PIN, "otp": OTP,
    })
    assert r.status_code == 200, r.text
    data = r.json()
    return data["token"], data["user"]


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
    data = r.json()
    return data["token"], data["user"]


def auth_headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def create_item(s, seller_token, **overrides):
    payload = {
        "itemName": "Tomato",
        "unitType": "Kg",
        "availableQuantity": 100.0,
        "pricePerUnit": 25.0,
        "minimumOrderQuantity": 2.0,
        "unitIncrement": 0.5,
    }
    payload.update(overrides)
    r = s.post(f"{API}/seller/items", json=payload, headers=auth_headers(seller_token))
    assert r.status_code == 200, r.text
    return r.json()["item"]


@pytest.fixture(scope="session")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


@pytest.fixture(scope="session")
def buyer(s):
    return register_buyer(s)  # (token, user)


@pytest.fixture(scope="session")
def seller(s):
    return register_seller(s)


@pytest.fixture(scope="session")
def other_buyer(s):
    return register_buyer(s)


# ---------- connections: create ----------

class TestConnectionsCreate:
    def test_invalid_seller_code_returns_404(self, s, buyer):
        token, _ = buyer
        r = s.post(f"{API}/buyer/connections", json={"sellerCode": "SELLER-9999999"}, headers=auth_headers(token))
        assert r.status_code == 404

    def test_seller_cannot_call_buyer_endpoint(self, s, seller):
        token, _ = seller
        r = s.post(f"{API}/buyer/connections", json={"sellerCode": "SELLER-1001"}, headers=auth_headers(token))
        assert r.status_code == 403

    def test_buyer_cannot_call_seller_connections_list(self, s, buyer):
        token, _ = buyer
        r = s.get(f"{API}/seller/connections", headers=auth_headers(token))
        assert r.status_code == 403

    def test_create_pending_connection(self, s, buyer, seller):
        b_token, _ = buyer
        _, s_user = seller
        r = s.post(f"{API}/buyer/connections", json={"sellerCode": s_user["sellerCode"]}, headers=auth_headers(b_token))
        assert r.status_code == 200, r.text
        body = r.json()
        assert_no_mongo_id(body)
        conn = body["connection"]
        assert conn["status"] == "Pending"
        assert conn["sellerId"] == s_user["userId"]
        assert conn["approvedDateTime"] is None
        assert conn["seller"]["sellerCode"] == s_user["sellerCode"]

    def test_duplicate_pending_returns_409(self, s, buyer, seller):
        b_token, _ = buyer
        _, s_user = seller
        r = s.post(f"{API}/buyer/connections", json={"sellerCode": s_user["sellerCode"]}, headers=auth_headers(b_token))
        assert r.status_code == 409


# ---------- connections: list scope ----------

class TestConnectionsList:
    def test_buyer_list_only_own(self, s, buyer):
        token, user = buyer
        r = s.get(f"{API}/buyer/connections", headers=auth_headers(token))
        assert r.status_code == 200
        body = r.json()
        assert_no_mongo_id(body)
        for c in body["connections"]:
            assert c["buyerId"] == user["userId"]
            assert "seller" in c

    def test_seller_list_only_own(self, s, seller):
        token, user = seller
        r = s.get(f"{API}/seller/connections", headers=auth_headers(token))
        assert r.status_code == 200
        body = r.json()
        assert_no_mongo_id(body)
        for c in body["connections"]:
            assert c["sellerId"] == user["userId"]
            assert "buyer" in c


# ---------- accept / reject ----------

class TestAcceptReject:
    def test_accept_then_idempotency_400(self, s, buyer, seller):
        b_token, _ = buyer
        s_token, _ = seller
        # find the pending connection (or create-accept) -> get connection id
        conns = s.get(f"{API}/seller/connections", headers=auth_headers(s_token)).json()["connections"]
        pending = [c for c in conns if c["status"] == "Pending"]
        assert pending, "No pending connection to accept"
        conn_id = pending[0]["connectionId"]
        r = s.post(f"{API}/seller/connections/{conn_id}/accept", headers=auth_headers(s_token))
        assert r.status_code == 200, r.text
        assert r.json()["connection"]["status"] == "Accepted"
        assert r.json()["connection"]["approvedDateTime"]
        # second attempt should fail
        r2 = s.post(f"{API}/seller/connections/{conn_id}/accept", headers=auth_headers(s_token))
        assert r2.status_code == 400
        r3 = s.post(f"{API}/seller/connections/{conn_id}/reject", headers=auth_headers(s_token))
        assert r3.status_code == 400

    def test_duplicate_accepted_returns_409(self, s, buyer, seller):
        b_token, _ = buyer
        _, s_user = seller
        r = s.post(f"{API}/buyer/connections", json={"sellerCode": s_user["sellerCode"]}, headers=auth_headers(b_token))
        assert r.status_code == 409

    def test_other_seller_cannot_accept(self, s, buyer):
        b_token, _ = buyer
        # create a new seller and a new pending request
        new_b_token, _ = register_buyer(s)
        _, new_s_user = register_seller(s)
        rogue_s_token, _ = register_seller(s)
        r = s.post(f"{API}/buyer/connections",
                   json={"sellerCode": new_s_user["sellerCode"]},
                   headers=auth_headers(new_b_token))
        assert r.status_code == 200
        conn_id = r.json()["connection"]["connectionId"]
        r2 = s.post(f"{API}/seller/connections/{conn_id}/accept",
                    headers=auth_headers(rogue_s_token))
        assert r2.status_code == 404

    def test_reject_flow(self, s):
        b_token, _ = register_buyer(s)
        s_token, s_user = register_seller(s)
        r = s.post(f"{API}/buyer/connections",
                   json={"sellerCode": s_user["sellerCode"]},
                   headers=auth_headers(b_token))
        assert r.status_code == 200
        cid = r.json()["connection"]["connectionId"]
        r2 = s.post(f"{API}/seller/connections/{cid}/reject", headers=auth_headers(s_token))
        assert r2.status_code == 200
        assert r2.json()["connection"]["status"] == "Rejected"


# ---------- pending expiry ----------

class TestPendingExpiry:
    def test_lazy_expiry_on_read(self, s):
        b_token, b_user = register_buyer(s)
        _, s_user = register_seller(s)
        r = s.post(f"{API}/buyer/connections",
                   json={"sellerCode": s_user["sellerCode"]},
                   headers=auth_headers(b_token))
        assert r.status_code == 200
        cid = r.json()["connection"]["connectionId"]

        # age it in mongo
        async def age_it():
            from motor.motor_asyncio import AsyncIOMotorClient
            cli = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
            d = cli[os.environ.get("DB_NAME", "test_database")]
            old = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
            res = await d.buyer_seller_connections.update_one(
                {"connectionId": cid}, {"$set": {"requestedDateTime": old}}
            )
            cli.close()
            assert res.modified_count == 1
        asyncio.get_event_loop().run_until_complete(age_it()) if False else asyncio.run(age_it())

        body = s.get(f"{API}/buyer/connections", headers=auth_headers(b_token)).json()
        target = [c for c in body["connections"] if c["connectionId"] == cid]
        assert target and target[0]["status"] == "Expired"


# ---------- accepted connection fixture for order tests ----------

@pytest.fixture(scope="module")
def connected_pair(s):
    """Buyer + seller with an Accepted connection and one item."""
    b_token, b_user = register_buyer(s)
    s_token, s_user = register_seller(s)
    item = create_item(s, s_token)  # min=2, inc=0.5, avail=100, price=25
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


# ---------- buyer browse ----------

class TestBuyerBrowse:
    def test_browse_requires_accepted(self, s):
        b_token, _ = register_buyer(s)
        _, s_user = register_seller(s)
        r = s.get(f"{API}/buyer/sellers/{s_user['userId']}/items", headers=auth_headers(b_token))
        assert r.status_code == 403

    def test_browse_lists_active_items(self, s, connected_pair):
        cp = connected_pair
        r = s.get(f"{API}/buyer/sellers/{cp['s_user']['userId']}/items",
                  headers=auth_headers(cp["b_token"]))
        assert r.status_code == 200
        body = r.json()
        assert_no_mongo_id(body)
        item_ids = [i["itemId"] for i in body["items"]]
        assert cp["item"]["itemId"] in item_ids
        assert all(i["isActive"] for i in body["items"])
        assert body["seller"]["sellerCode"] == cp["s_user"]["sellerCode"]

    def test_browse_search_q(self, s, connected_pair):
        cp = connected_pair
        # Add a second item with different name
        create_item(s, cp["s_token"], itemName="Banana", availableQuantity=50, pricePerUnit=10,
                    minimumOrderQuantity=1, unitIncrement=1)
        r = s.get(f"{API}/buyer/sellers/{cp['s_user']['userId']}/items?q=bana",
                  headers=auth_headers(cp["b_token"]))
        assert r.status_code == 200
        names = [i["itemName"].lower() for i in r.json()["items"]]
        assert all("bana" in n for n in names)
        assert any("banana" == n for n in names)


# ---------- orders ----------

class TestOrders:
    def test_order_without_connection_403(self, s):
        b_token, _ = register_buyer(s)
        _, s_user = register_seller(s)
        r = s.post(f"{API}/buyer/orders",
                   json={"sellerId": s_user["userId"], "items": [{"itemId": "x", "quantity": 1}]},
                   headers=auth_headers(b_token))
        assert r.status_code == 403

    def test_qty_below_min(self, s, connected_pair):
        cp = connected_pair
        r = s.post(f"{API}/buyer/orders", json={
            "sellerId": cp["s_user"]["userId"],
            "items": [{"itemId": cp["item"]["itemId"], "quantity": 1}],  # min=2
        }, headers=auth_headers(cp["b_token"]))
        assert r.status_code == 400
        assert "minimum" in r.text.lower()

    def test_qty_not_aligned_with_increment(self, s, connected_pair):
        cp = connected_pair
        # min=2, inc=0.5 → 2.3 misaligned
        r = s.post(f"{API}/buyer/orders", json={
            "sellerId": cp["s_user"]["userId"],
            "items": [{"itemId": cp["item"]["itemId"], "quantity": 2.3}],
        }, headers=auth_headers(cp["b_token"]))
        assert r.status_code == 400
        assert "multiples" in r.text.lower() or "increment" in r.text.lower()

    def test_qty_above_available(self, s, connected_pair):
        cp = connected_pair
        r = s.post(f"{API}/buyer/orders", json={
            "sellerId": cp["s_user"]["userId"],
            "items": [{"itemId": cp["item"]["itemId"], "quantity": 9999}],
        }, headers=auth_headers(cp["b_token"]))
        assert r.status_code == 400

    def test_valid_order_created(self, s, connected_pair):
        cp = connected_pair
        # min=2, inc=0.5 → qty=2.5 OK; price=25 → total=62.5
        r = s.post(f"{API}/buyer/orders", json={
            "sellerId": cp["s_user"]["userId"],
            "items": [{"itemId": cp["item"]["itemId"], "quantity": 2.5}],
        }, headers=auth_headers(cp["b_token"]))
        assert r.status_code == 200, r.text
        body = r.json()
        assert_no_mongo_id(body)
        order = body["order"]
        assert order["orderStatus"] == "Requested"
        assert re.match(r"^ORD-\d{6,}$", order["orderNumber"])
        assert int(order["orderNumber"].split("-")[1]) >= 100001
        assert order["totalAmount"] == 62.5
        # items persisted
        assert len(body["items"]) == 1
        oi = body["items"][0]
        assert oi["itemName"] == cp["item"]["itemName"]
        assert oi["quantity"] == 2.5
        assert oi["unitType"] == "Kg"
        assert oi["pricePerUnit"] == 25.0
        assert oi["itemTotal"] == 62.5
        # stash for later
        cp["order_id"] = order["orderId"]
        cp["order_number"] = order["orderNumber"]

    def test_order_number_monotonic(self, s, connected_pair):
        cp = connected_pair
        r1 = s.post(f"{API}/buyer/orders", json={
            "sellerId": cp["s_user"]["userId"],
            "items": [{"itemId": cp["item"]["itemId"], "quantity": 2}],
        }, headers=auth_headers(cp["b_token"]))
        r2 = s.post(f"{API}/buyer/orders", json={
            "sellerId": cp["s_user"]["userId"],
            "items": [{"itemId": cp["item"]["itemId"], "quantity": 2}],
        }, headers=auth_headers(cp["b_token"]))
        assert r1.status_code == 200 and r2.status_code == 200
        n1 = int(r1.json()["order"]["orderNumber"].split("-")[1])
        n2 = int(r2.json()["order"]["orderNumber"].split("-")[1])
        assert n2 == n1 + 1

    def test_buyer_order_list(self, s, connected_pair):
        cp = connected_pair
        r = s.get(f"{API}/buyer/orders", headers=auth_headers(cp["b_token"]))
        assert r.status_code == 200
        body = r.json()
        assert_no_mongo_id(body)
        assert body["orders"], "expected at least 1 order"
        for o in body["orders"]:
            assert o["buyerId"] == cp["b_user"]["userId"]
            assert o["seller"]["sellerCode"] == cp["s_user"]["sellerCode"]

    def test_seller_order_list(self, s, connected_pair):
        cp = connected_pair
        r = s.get(f"{API}/seller/orders", headers=auth_headers(cp["s_token"]))
        assert r.status_code == 200
        body = r.json()
        assert_no_mongo_id(body)
        assert body["orders"]
        for o in body["orders"]:
            assert o["sellerId"] == cp["s_user"]["userId"]
            assert o["buyer"]["firstName"]

    def test_order_detail_buyer_and_seller(self, s, connected_pair):
        cp = connected_pair
        oid = cp.get("order_id")
        if not oid:
            # fetch from buyer list
            oid = s.get(f"{API}/buyer/orders", headers=auth_headers(cp["b_token"])).json()["orders"][0]["orderId"]
        rb = s.get(f"{API}/orders/{oid}", headers=auth_headers(cp["b_token"]))
        assert rb.status_code == 200
        body = rb.json()
        assert_no_mongo_id(body)
        assert body["counterparty"]["sellerCode"] == cp["s_user"]["sellerCode"]
        assert body["items"]

        rs = s.get(f"{API}/orders/{oid}", headers=auth_headers(cp["s_token"]))
        assert rs.status_code == 200
        body2 = rs.json()
        assert body2["counterparty"]["firstName"] == cp["b_user"]["firstName"]

        # third party
        rogue_token, _ = register_buyer(s)
        r3 = s.get(f"{API}/orders/{oid}", headers=auth_headers(rogue_token))
        assert r3.status_code == 403
