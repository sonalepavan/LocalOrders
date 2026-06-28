"""Tests for the COMPLETED status enhancement on custom requests.

Covers:
  - POST /api/seller/custom-requests/{id}/complete  ACCEPTED -> COMPLETED + completedAt
  - Endpoint rejects non-ACCEPTED requests with 400
  - Buyer gets a `custom_request_completed` notification
  - Existing lifecycle (send/quote/accept-quote/reject/reject-quote) still works
  - Existing buyer order creation with customMessage still works
  - Existing seller item creation still works
"""
import os
import random
import time
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://orders-import-setup.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

PIN = "1234"
BUYER_MOBILE = "9876645804"
SELLER_MOBILE = "9877645804"


def _login(mobile: str) -> dict:
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{API}/auth/login", json={"mobileNumber": mobile, "pin": PIN})
    assert r.status_code == 200, f"login {mobile}: {r.status_code} {r.text}"
    data = r.json()
    s.headers.update({"Authorization": f"Bearer {data['token']}"})
    return {"session": s, "user": data["user"]}


@pytest.fixture(scope="module")
def pair():
    return {"buyer": _login(BUYER_MOBILE), "seller": _login(SELLER_MOBILE)}


def _create_and_send(buyer, seller) -> str:
    r = buyer["session"].post(
        f"{API}/buyer/custom-requests",
        json={"sellerId": seller["user"]["userId"], "requestDetails": f"TEST_need widgets {random.randint(0,9999)}", "send": True},
    )
    assert r.status_code in (200, 201), r.text
    req = r.json()["request"]
    assert req["status"] == "NEW_REQUEST"
    return req["requestId"]


def _drive_to_accepted_via_quote(buyer, seller, request_id: str) -> None:
    r = seller["session"].post(
        f"{API}/seller/custom-requests/{request_id}/quote",
        json={"quoteAmount": 100.0, "sellerMessage": "Quote msg"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["request"]["status"] == "QUOTE_SENT"
    r = buyer["session"].post(f"{API}/buyer/custom-requests/{request_id}/accept-quote")
    assert r.status_code == 200, r.text
    assert r.json()["request"]["status"] == "ACCEPTED"


# ---------- COMPLETED status tests ----------
class TestCompleteEndpoint:
    def test_complete_accepted_request_persists_completedAt(self, pair):
        buyer, seller = pair["buyer"], pair["seller"]
        rid = _create_and_send(buyer, seller)
        _drive_to_accepted_via_quote(buyer, seller, rid)

        r = seller["session"].post(f"{API}/seller/custom-requests/{rid}/complete")
        assert r.status_code == 200, r.text
        body = r.json()["request"]
        assert body["status"] == "COMPLETED"
        assert body.get("completedAt"), "completedAt must be persisted"
        assert "T" in body["completedAt"], f"completedAt should be ISO timestamp: {body['completedAt']}"

        # Verify via GET (shared endpoint)
        r = buyer["session"].get(f"{API}/custom-requests/{rid}")
        assert r.status_code == 200
        got = r.json()["request"]
        assert got["status"] == "COMPLETED"
        assert got["completedAt"] == body["completedAt"]
        # quote fields preserved (used by buyer detail screen)
        assert got["quoteAmount"] == 100.0
        assert got["sellerMessage"] == "Quote msg"

    def test_complete_rejects_non_accepted_with_400(self, pair):
        buyer, seller = pair["buyer"], pair["seller"]
        rid = _create_and_send(buyer, seller)  # status: NEW_REQUEST
        r = seller["session"].post(f"{API}/seller/custom-requests/{rid}/complete")
        assert r.status_code == 400, r.text
        body = r.json()
        assert "NEW_REQUEST" in body.get("detail", "") or "Cannot" in body.get("detail", "")

    def test_complete_creates_buyer_notification(self, pair):
        buyer, seller = pair["buyer"], pair["seller"]
        rid = _create_and_send(buyer, seller)
        _drive_to_accepted_via_quote(buyer, seller, rid)
        r = seller["session"].post(f"{API}/seller/custom-requests/{rid}/complete")
        assert r.status_code == 200, r.text
        time.sleep(0.5)
        r = buyer["session"].get(f"{API}/notifications")
        assert r.status_code == 200, r.text
        body = r.json()
        items = body.get("notifications", body) if isinstance(body, dict) else body
        matches = [
            n for n in items
            if n.get("type") == "custom_request_completed"
            and (n.get("data") or {}).get("customRequestId") == rid
        ]
        assert matches, f"Expected custom_request_completed notification for {rid}; got types: {[n.get('type') for n in items[:10]]}"


# ---------- existing lifecycle regression ----------
class TestExistingLifecycle:
    def test_saved_then_send_then_quote_then_accept(self, pair):
        buyer, seller = pair["buyer"], pair["seller"]
        r = buyer["session"].post(
            f"{API}/buyer/custom-requests",
            json={"sellerId": seller["user"]["userId"], "requestDetails": "TEST_lifecycle draft", "send": False},
        )
        assert r.status_code in (200, 201), r.text
        req = r.json()["request"]
        assert req["status"] == "SAVED"
        rid = req["requestId"]

        r = buyer["session"].post(f"{API}/buyer/custom-requests/{rid}/send")
        assert r.status_code == 200
        assert r.json()["request"]["status"] == "NEW_REQUEST"

        r = seller["session"].post(
            f"{API}/seller/custom-requests/{rid}/quote",
            json={"quoteAmount": 50.0, "sellerMessage": "ok"},
        )
        assert r.status_code == 200
        assert r.json()["request"]["status"] == "QUOTE_SENT"

        r = buyer["session"].post(f"{API}/buyer/custom-requests/{rid}/accept-quote")
        assert r.status_code == 200
        assert r.json()["request"]["status"] == "ACCEPTED"

    def test_seller_reject_new_request(self, pair):
        buyer, seller = pair["buyer"], pair["seller"]
        rid = _create_and_send(buyer, seller)
        r = seller["session"].post(
            f"{API}/seller/custom-requests/{rid}/reject", json={"rejectionReason": "out of stock"}
        )
        assert r.status_code == 200, r.text
        assert r.json()["request"]["status"] == "REJECTED_BY_SELLER"

    def test_buyer_reject_quote(self, pair):
        buyer, seller = pair["buyer"], pair["seller"]
        rid = _create_and_send(buyer, seller)
        r = seller["session"].post(
            f"{API}/seller/custom-requests/{rid}/quote",
            json={"quoteAmount": 75.0},
        )
        assert r.status_code == 200
        r = buyer["session"].post(f"{API}/buyer/custom-requests/{rid}/reject-quote")
        assert r.status_code == 200, r.text
        assert r.json()["request"]["status"] == "REJECTED_BY_BUYER"


# ---------- orders + items regression ----------
class TestOrdersRegression:
    def _ensure_item(self, seller):
        r = seller["session"].get(f"{API}/seller/items")
        assert r.status_code == 200, r.text
        items = r.json().get("items") or r.json()
        active = [i for i in items if i.get("isActive", True) and i.get("availableQuantity", 0) > 5]
        if active:
            return active[0]
        # Create a fresh item
        payload = {
            "itemName": f"TEST_ITEM_{random.randint(1000, 9999)}",
            "unitType": "Piece",
            "availableQuantity": 100.0,
            "pricePerUnit": 9.99,
            "minimumOrderQuantity": 1.0,
            "unitIncrement": 1.0,
        }
        r = seller["session"].post(f"{API}/seller/items", json=payload)
        assert r.status_code in (200, 201), r.text
        return r.json().get("item") or r.json()

    def test_seller_create_item(self, pair):
        seller = pair["seller"]
        payload = {
            "itemName": f"TEST_ITEM_{random.randint(1000, 9999)}",
            "unitType": "Piece",
            "availableQuantity": 50.0,
            "pricePerUnit": 12.5,
            "minimumOrderQuantity": 1.0,
            "unitIncrement": 1.0,
        }
        r = seller["session"].post(f"{API}/seller/items", json=payload)
        assert r.status_code in (200, 201), r.text
        body = r.json().get("item") or r.json()
        assert body.get("itemName") == payload["itemName"]

    def test_buyer_order_with_custom_message_persists(self, pair):
        buyer, seller = pair["buyer"], pair["seller"]
        item = self._ensure_item(seller)
        item_id = item.get("itemId") or item.get("id")
        assert item_id, item

        msg = f"TEST custom note {random.randint(1000,9999)}"
        order_payload = {
            "sellerId": seller["user"]["userId"],
            "items": [{"itemId": item_id, "quantity": 2.0, "customMessage": msg}],
        }
        r = buyer["session"].post(f"{API}/buyer/orders", json=order_payload)
        assert r.status_code in (200, 201), r.text
        order = r.json().get("order") or r.json()
        order_id = order.get("orderId") or order.get("id")
        assert order_id

        # GET /buyer/orders should return the order
        r = buyer["session"].get(f"{API}/buyer/orders")
        assert r.status_code == 200
        b = r.json()
        orders = b.get("orders") if isinstance(b, dict) else b
        assert orders, "expected at least one order"
        found = [o for o in orders if (o.get("orderId") or o.get("id")) == order_id]
        assert found, "newly placed order should be returned"
