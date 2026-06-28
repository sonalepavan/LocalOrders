"""
Backend regression for the new buyer 'Place Order Now' UI flow.

The change is UI-only: buyer-seller-items.tsx now lets the buyer pick a quantity
on the item card and either (a) add-to-cart → /buyer-cart → manual Place Order,
or (b) Place Order Now → /buyer-cart?autoPlace=1 which auto-fires the same
api.createOrder() call. Both flows MUST produce identical orders for the same
selected qty. This file verifies the backend contract that supports both
flows is intact and that an order created with a non-MOQ selected quantity
matches the qty the client posted.

OTP is mocked = 123456. No seeded users.
"""
import os
import random
import string
import time

import pytest
import requests

_PUBLIC = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://local-orders-app-1.preview.emergentagent.com").rstrip("/")
# Fall back to localhost if the public ingress is currently not routing /api (returns 404 on /api/).
try:
    _probe = requests.get(f"{_PUBLIC}/api/", timeout=5)
    BASE_URL = _PUBLIC if _probe.status_code == 200 else "http://localhost:8001"
except Exception:
    BASE_URL = "http://localhost:8001"
API = f"{BASE_URL}/api"
OTP = "123456"


def _mob() -> str:
    return "9" + "".join(random.choices(string.digits, k=9))


def _rand(n=5) -> str:
    return "".join(random.choices(string.ascii_uppercase, k=n))


@pytest.fixture(scope="module")
def session():
    return requests.Session()


@pytest.fixture(scope="module")
def seller_ctx(session):
    """Register a seller, set Open, create two items:
    - itemA: MOQ=1, step=1, avail=10
    - itemB: MOQ=2, step=2, avail=10
    """
    payload = {
        "firstName": "TEST", "lastName": _rand(),
        "mobileNumber": _mob(), "address": "TEST addr",
        "pincode": "560001", "pin": "1234", "confirmPin": "1234",
        "otp": OTP, "businessName": f"TEST_{_rand()}",
    }
    r = session.post(f"{API}/auth/register/seller", json=payload, timeout=30)
    assert r.status_code in (200, 201), r.text
    data = r.json()
    token = data["token"]
    user = data["user"]
    headers = {"Authorization": f"Bearer {token}"}

    # Ensure Open
    r = session.put(f"{API}/seller/availability", json={"status": "Open"}, headers=headers, timeout=30)
    assert r.status_code == 200

    # Items
    item_a = {"itemName": f"TEST_A_{_rand()}", "unitType": "Kg",
              "availableQuantity": 10, "reservedQuantity": 0,
              "pricePerUnit": 100, "minimumOrderQuantity": 1, "unitIncrement": 1,
              "lowInventory": False}
    item_b = {"itemName": f"TEST_B_{_rand()}", "unitType": "Kg",
              "availableQuantity": 10, "reservedQuantity": 0,
              "pricePerUnit": 50, "minimumOrderQuantity": 2, "unitIncrement": 2,
              "lowInventory": False}
    ra = session.post(f"{API}/seller/items", json=item_a, headers=headers, timeout=30)
    rb = session.post(f"{API}/seller/items", json=item_b, headers=headers, timeout=30)
    assert ra.status_code in (200, 201), ra.text
    assert rb.status_code in (200, 201), rb.text
    return {
        "token": token, "headers": headers, "user": user,
        "sellerId": user["userId"], "sellerCode": user["sellerCode"],
        "itemA": ra.json()["item"], "itemB": rb.json()["item"],
    }


@pytest.fixture(scope="module")
def buyer_ctx(session, seller_ctx):
    """Register a buyer, request connection, accept, return buyer headers."""
    payload = {
        "firstName": "TEST", "lastName": _rand(),
        "mobileNumber": _mob(), "address": "TEST addr",
        "pincode": "560001", "pin": "1234", "confirmPin": "1234",
        "otp": OTP,
    }
    r = session.post(f"{API}/auth/register/buyer", json=payload, timeout=30)
    assert r.status_code in (200, 201), r.text
    data = r.json()
    token = data["token"]
    user = data["user"]
    headers = {"Authorization": f"Bearer {token}"}

    # Request connection
    r = session.post(f"{API}/buyer/connections", json={"sellerCode": seller_ctx["sellerCode"]},
                     headers=headers, timeout=30)
    assert r.status_code in (200, 201), r.text
    conn = r.json()["connection"]
    # Seller accepts
    ra = session.post(f"{API}/seller/connections/{conn['connectionId']}/accept",
                      headers=seller_ctx["headers"], timeout=30)
    assert ra.status_code == 200, ra.text
    return {"token": token, "headers": headers, "user": user, "buyerId": user["userId"]}


class TestBrowseAndOrder:
    """Item browse + order placement contract used by both Add-to-Cart and Place-Order-Now flows."""

    def test_browse_seller_items_returns_moq_step_avail(self, session, seller_ctx, buyer_ctx):
        r = session.get(f"{API}/buyer/sellers/{seller_ctx['sellerId']}/items",
                        headers=buyer_ctx["headers"], timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "seller" in body and "items" in body
        names = {i["itemName"] for i in body["items"]}
        assert seller_ctx["itemA"]["itemName"] in names
        assert seller_ctx["itemB"]["itemName"] in names
        # MOQ/step/avail surfaced for the stepper
        for it in body["items"]:
            assert "minimumOrderQuantity" in it and "unitIncrement" in it and "availableQuantity" in it

    def test_order_with_selected_qty_not_moq(self, session, seller_ctx, buyer_ctx):
        """Flow 1: cart line qty (selected) was 3 for itemA. Order MUST reflect qty=3."""
        sel_qty = 3
        r = session.post(f"{API}/buyer/orders", headers=buyer_ctx["headers"], timeout=30,
                         json={"sellerId": seller_ctx["sellerId"],
                               "items": [{"itemId": seller_ctx["itemA"]["itemId"], "quantity": sel_qty}]})
        assert r.status_code in (200, 201), r.text
        body = r.json()
        order = body["order"]
        items = body["items"]
        assert order["sellerId"] == seller_ctx["sellerId"]
        assert order["buyerId"] == buyer_ctx["buyerId"]
        assert order["orderStatus"] == "Requested"
        assert len(items) == 1
        assert items[0]["quantity"] == sel_qty
        assert items[0]["itemId"] == seller_ctx["itemA"]["itemId"]
        # totalAmount = 3 * 100
        assert abs(order["totalAmount"] - 300) < 1e-6

    def test_flow1_equals_flow2_same_shape(self, session, seller_ctx, buyer_ctx):
        """Two orders posted with the same selected qty must be structurally identical.
        This is what the UI does for Add→Cart→PlaceOrder vs PlaceOrderNow."""
        sel_qty = 4  # MOQ=2, step=2 ⇒ valid
        payload = {"sellerId": seller_ctx["sellerId"],
                   "items": [{"itemId": seller_ctx["itemB"]["itemId"], "quantity": sel_qty}]}
        r1 = session.post(f"{API}/buyer/orders", headers=buyer_ctx["headers"], json=payload, timeout=30)
        time.sleep(0.2)
        r2 = session.post(f"{API}/buyer/orders", headers=buyer_ctx["headers"], json=payload, timeout=30)
        assert r1.status_code in (200, 201) and r2.status_code in (200, 201), (r1.text, r2.text)
        o1, o2 = r1.json()["order"], r2.json()["order"]
        it1, it2 = r1.json()["items"], r2.json()["items"]
        # Different orderId/orderNumber/timestamps but same shape/qty/seller/buyer/total
        assert o1["sellerId"] == o2["sellerId"]
        assert o1["buyerId"] == o2["buyerId"]
        assert o1["orderStatus"] == o2["orderStatus"] == "Requested"
        assert abs(o1["totalAmount"] - o2["totalAmount"]) < 1e-6
        assert it1[0]["itemId"] == it2[0]["itemId"]
        assert it1[0]["quantity"] == it2[0]["quantity"] == sel_qty
        assert it1[0]["pricePerUnit"] == it2[0]["pricePerUnit"]
        assert it1[0]["itemTotal"] == it2[0]["itemTotal"]

    def test_order_below_moq_rejected(self, session, seller_ctx, buyer_ctx):
        """Backend should reject qty < MOQ — protects buyer flows from any UI bug."""
        r = session.post(f"{API}/buyer/orders", headers=buyer_ctx["headers"], timeout=30,
                         json={"sellerId": seller_ctx["sellerId"],
                               "items": [{"itemId": seller_ctx["itemB"]["itemId"], "quantity": 1}]})
        assert r.status_code >= 400, r.text

    def test_order_above_available_rejected(self, session, seller_ctx, buyer_ctx):
        r = session.post(f"{API}/buyer/orders", headers=buyer_ctx["headers"], timeout=30,
                         json={"sellerId": seller_ctx["sellerId"],
                               "items": [{"itemId": seller_ctx["itemA"]["itemId"], "quantity": 999}]})
        assert r.status_code >= 400, r.text

    def test_no_mongo_id_in_order_response(self, session, seller_ctx, buyer_ctx):
        r = session.post(f"{API}/buyer/orders", headers=buyer_ctx["headers"], timeout=30,
                         json={"sellerId": seller_ctx["sellerId"],
                               "items": [{"itemId": seller_ctx["itemA"]["itemId"], "quantity": 1}]})
        assert r.status_code in (200, 201), r.text
        body = r.json()
        assert "_id" not in body
        assert "_id" not in body["order"]
        for it in body["items"]:
            assert "_id" not in it
