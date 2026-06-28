"""Backend tests for the per-item Custom Message feature.

Covers:
  (A) POST /api/buyer/orders accepts and persists customMessage per item, trims
      leading/trailing whitespace.
  (B) Whitespace-only customMessage is normalised to None.
  (C) customMessage omitted entirely → stored/returned as None (backward compat).
  (D) customMessage > 500 chars rejected with a validation error (422).
  (E/F) GET /api/orders/{id} returns customMessage to BOTH buyer and seller.
  (G) Legacy order_items doc without the field surfaces customMessage: None
      and does not crash.
"""
import os
import random
import time

import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient

BASE = os.environ.get(
    "EXPO_PUBLIC_BACKEND_URL", "https://local-orders-deploy.preview.emergentagent.com"
).rstrip("/")

# Backend-side direct DB access for the legacy-order test
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")


def _rand_mobile() -> str:
    return "9" + "".join(str(random.randint(0, 9)) for _ in range(9))


def _register(role: str, extra: dict | None = None) -> tuple[str, dict]:
    mobile = _rand_mobile()
    extra = extra or {}
    r = requests.post(
        f"{BASE}/api/auth/otp/send",
        json={"mobileNumber": mobile, "userType": role},
        timeout=20,
    )
    r.raise_for_status()
    body = {
        "firstName": "TEST",
        "lastName": role.capitalize(),
        "mobileNumber": mobile,
        "pin": "1234",
        "confirmPin": "1234",
        "otp": "123456",
        "address": "TEST Addr",
        "pincode": "431702",
        **extra,
    }
    r = requests.post(f"{BASE}/api/auth/register/{role}", json=body, timeout=20)
    r.raise_for_status()
    data = r.json()
    return data["token"], data["user"]


@pytest.fixture(scope="module")
def env():
    """Seed buyer+seller with accepted connection and 2 active items."""
    buyer_tok, buyer = _register("buyer")
    seller_tok, seller = _register("seller", {"businessName": "TEST CM Shop"})

    buyer_hdr = {"Authorization": f"Bearer {buyer_tok}"}
    seller_hdr = {"Authorization": f"Bearer {seller_tok}"}

    me = requests.get(f"{BASE}/api/auth/me", headers=seller_hdr, timeout=20).json()
    seller_code = me["user"]["sellerCode"]
    seller_id = me["user"]["userId"] if "userId" in me["user"] else me["user"].get("id")

    cr = requests.post(
        f"{BASE}/api/buyer/connections",
        headers=buyer_hdr,
        json={"sellerCode": seller_code},
        timeout=20,
    )
    cr.raise_for_status()
    conn_id = cr.json()["connection"]["connectionId"]

    r = requests.post(
        f"{BASE}/api/seller/connections/{conn_id}/accept",
        headers=seller_hdr,
        timeout=20,
    )
    r.raise_for_status()

    items = []
    for i in range(2):
        r = requests.post(
            f"{BASE}/api/seller/items",
            headers=seller_hdr,
            json={
                "itemName": f"TEST CM Item {i+1}",
                "unitType": "Kg",
                "pricePerUnit": 50,
                "minimumOrderQuantity": 1,
                "unitIncrement": 1,
                "availableQuantity": 100,
            },
            timeout=20,
        )
        r.raise_for_status()
        items.append(r.json()["item"])

    return {
        "buyer_tok": buyer_tok,
        "seller_tok": seller_tok,
        "buyer_hdr": buyer_hdr,
        "seller_hdr": seller_hdr,
        "seller_id": seller_id,
        "items": items,
    }


# ---------- A. trim leading/trailing whitespace ----------

def test_create_order_trims_whitespace(env):
    msg = "   Please pack fresh items   "
    r = requests.post(
        f"{BASE}/api/buyer/orders",
        headers=env["buyer_hdr"],
        json={
            "sellerId": env["seller_id"],
            "items": [{"itemId": env["items"][0]["itemId"], "quantity": 2, "customMessage": msg}],
        },
        timeout=20,
    )
    assert r.status_code == 200, r.text
    order_id = r.json()["order"]["orderId"]

    g = requests.get(f"{BASE}/api/orders/{order_id}", headers=env["buyer_hdr"], timeout=20)
    assert g.status_code == 200
    items = g.json()["items"]
    assert items[0]["customMessage"] == "Please pack fresh items"


# ---------- B. whitespace-only → None ----------

def test_whitespace_only_normalised_to_null(env):
    r = requests.post(
        f"{BASE}/api/buyer/orders",
        headers=env["buyer_hdr"],
        json={
            "sellerId": env["seller_id"],
            "items": [{"itemId": env["items"][0]["itemId"], "quantity": 1, "customMessage": "     "}],
        },
        timeout=20,
    )
    assert r.status_code == 200, r.text
    order_id = r.json()["order"]["orderId"]
    g = requests.get(f"{BASE}/api/orders/{order_id}", headers=env["buyer_hdr"], timeout=20).json()
    assert g["items"][0]["customMessage"] is None


# ---------- C. omitted message → None (backward compat) ----------

def test_omitted_message_returns_null(env):
    r = requests.post(
        f"{BASE}/api/buyer/orders",
        headers=env["buyer_hdr"],
        json={
            "sellerId": env["seller_id"],
            "items": [{"itemId": env["items"][0]["itemId"], "quantity": 1}],
        },
        timeout=20,
    )
    assert r.status_code == 200, r.text
    order_id = r.json()["order"]["orderId"]
    g = requests.get(f"{BASE}/api/orders/{order_id}", headers=env["buyer_hdr"], timeout=20).json()
    items = g["items"]
    assert "customMessage" in items[0]
    assert items[0]["customMessage"] is None


# ---------- D. 501 chars rejected ----------

def test_501_chars_rejected(env):
    long_msg = "a" * 501
    r = requests.post(
        f"{BASE}/api/buyer/orders",
        headers=env["buyer_hdr"],
        json={
            "sellerId": env["seller_id"],
            "items": [{"itemId": env["items"][0]["itemId"], "quantity": 1, "customMessage": long_msg}],
        },
        timeout=20,
    )
    assert r.status_code in (400, 422), f"Expected 400/422, got {r.status_code}: {r.text}"


def test_exactly_500_chars_accepted(env):
    msg = "b" * 500
    r = requests.post(
        f"{BASE}/api/buyer/orders",
        headers=env["buyer_hdr"],
        json={
            "sellerId": env["seller_id"],
            "items": [{"itemId": env["items"][0]["itemId"], "quantity": 1, "customMessage": msg}],
        },
        timeout=20,
    )
    assert r.status_code == 200, r.text
    order_id = r.json()["order"]["orderId"]
    g = requests.get(f"{BASE}/api/orders/{order_id}", headers=env["buyer_hdr"], timeout=20).json()
    assert g["items"][0]["customMessage"] == msg
    assert len(g["items"][0]["customMessage"]) == 500


# ---------- E/F. buyer + seller both see the message ----------

def test_buyer_and_seller_both_see_message(env):
    msg = "Both buyer and seller should see this."
    r = requests.post(
        f"{BASE}/api/buyer/orders",
        headers=env["buyer_hdr"],
        json={
            "sellerId": env["seller_id"],
            "items": [
                {"itemId": env["items"][0]["itemId"], "quantity": 2, "customMessage": msg},
                {"itemId": env["items"][1]["itemId"], "quantity": 1},
            ],
        },
        timeout=20,
    )
    assert r.status_code == 200, r.text
    order_id = r.json()["order"]["orderId"]

    b = requests.get(f"{BASE}/api/orders/{order_id}", headers=env["buyer_hdr"], timeout=20).json()
    s = requests.get(f"{BASE}/api/orders/{order_id}", headers=env["seller_hdr"], timeout=20).json()

    b_items = b["items"]
    s_items = s["items"]
    # find by itemId since order can differ
    def find(items, item_id):
        return next(it for it in items if it["itemId"] == item_id)

    assert find(b_items, env["items"][0]["itemId"])["customMessage"] == msg
    assert find(s_items, env["items"][0]["itemId"])["customMessage"] == msg
    assert find(b_items, env["items"][1]["itemId"])["customMessage"] is None
    assert find(s_items, env["items"][1]["itemId"])["customMessage"] is None


# ---------- G. legacy order_item without customMessage key ----------

@pytest.mark.asyncio
async def test_legacy_order_item_without_field_returns_null(env):
    # Place an order, then directly $unset the customMessage field in Mongo to
    # simulate a legacy doc that pre-dates this feature.
    r = requests.post(
        f"{BASE}/api/buyer/orders",
        headers=env["buyer_hdr"],
        json={
            "sellerId": env["seller_id"],
            "items": [{"itemId": env["items"][0]["itemId"], "quantity": 1, "customMessage": "to-be-removed"}],
        },
        timeout=20,
    )
    assert r.status_code == 200, r.text
    order_id = r.json()["order"]["orderId"]

    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    res = await db.order_items.update_many(
        {"orderId": order_id}, {"$unset": {"customMessage": ""}}
    )
    assert res.modified_count >= 1

    # Confirm field is actually missing
    doc = await db.order_items.find_one({"orderId": order_id})
    assert "customMessage" not in doc
    client.close()

    # Now GET — should not crash and should return customMessage: None
    g = requests.get(f"{BASE}/api/orders/{order_id}", headers=env["buyer_hdr"], timeout=20)
    assert g.status_code == 200
    items = g.json()["items"]
    assert "customMessage" in items[0]
    assert items[0]["customMessage"] is None

    # Seller view too
    g2 = requests.get(f"{BASE}/api/orders/{order_id}", headers=env["seller_hdr"], timeout=20)
    assert g2.status_code == 200
    assert g2.json()["items"][0]["customMessage"] is None
