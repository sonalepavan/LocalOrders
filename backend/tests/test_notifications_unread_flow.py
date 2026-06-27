"""
Backend integration tests for the unread-count / mark-read / mark-all-read flow
used by NotificationBell. Reuses existing notification APIs only.
"""
import os
import random
import time

import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://local-orders-deploy.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
OTP = "123456"
PIN = "1234"


def _mob() -> str:
    # Random 10-digit starting with 9
    return "9" + "".join(str(random.randint(0, 9)) for _ in range(9))


@pytest.fixture(scope="module")
def accounts():
    """Register a fresh buyer + seller, accept connection, return tokens & user info."""
    s = requests.Session()
    buyer_mob, seller_mob = _mob(), _mob()

    # Send OTPs (best effort; mock always returns 123456)
    for m, ut in [(buyer_mob, "buyer"), (seller_mob, "seller")]:
        s.post(f"{API}/auth/otp/send", json={"mobileNumber": m, "userType": ut}, timeout=15)

    buyer_payload = {
        "firstName": "TEST", "lastName": "Buyer",
        "mobileNumber": buyer_mob, "pin": PIN, "confirmPin": PIN, "otp": OTP,
        "address": "TEST Addr", "pincode": "431702",
    }
    seller_payload = {
        "firstName": "TEST", "lastName": "Seller",
        "mobileNumber": seller_mob, "pin": PIN, "confirmPin": PIN, "otp": OTP,
        "address": "TEST Addr", "pincode": "431702",
        "businessName": "TEST Shop",
    }
    rb = s.post(f"{API}/auth/register/buyer", json=buyer_payload, timeout=15)
    assert rb.status_code in (200, 201), rb.text
    buyer = rb.json()

    rs = s.post(f"{API}/auth/register/seller", json=seller_payload, timeout=15)
    assert rs.status_code in (200, 201), rs.text
    seller = rs.json()

    return {
        "buyer_token": buyer["token"],
        "buyer_user": buyer["user"],
        "seller_token": seller["token"],
        "seller_user": seller["user"],
        "buyer_mob": buyer_mob,
        "seller_mob": seller_mob,
    }


def _auth(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ---- Tests ----

def test_unread_count_endpoint_authenticated(accounts):
    r = requests.get(f"{API}/notifications/unread-count", headers=_auth(accounts["buyer_token"]), timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "unreadCount" in data
    assert isinstance(data["unreadCount"], int)


def test_unread_count_requires_auth():
    r = requests.get(f"{API}/notifications/unread-count", timeout=15)
    assert r.status_code in (401, 403)


def test_full_flow_create_read_decrement(accounts):
    buyer_tok = accounts["buyer_token"]
    seller_tok = accounts["seller_token"]
    seller_code = accounts["seller_user"].get("sellerCode")
    assert seller_code, "seller must have sellerCode"

    # Buyer requests connection → notification for seller
    r = requests.post(f"{API}/buyer/connections", headers=_auth(buyer_tok),
                      json={"sellerCode": seller_code}, timeout=15)
    assert r.status_code in (200, 201), r.text
    conn = r.json()["connection"]
    conn_id = conn["connectionId"]

    # Seller accepts → notification for buyer (connection_accepted)
    r = requests.post(f"{API}/seller/connections/{conn_id}/accept", headers=_auth(seller_tok), timeout=15)
    assert r.status_code in (200, 201), r.text

    # Allow notification persistence
    time.sleep(1.0)

    # Buyer unread count should be >= 1
    r = requests.get(f"{API}/notifications/unread-count", headers=_auth(buyer_tok), timeout=15)
    assert r.status_code == 200
    count_before = r.json()["unreadCount"]
    assert count_before >= 1, f"expected >=1 unread, got {count_before}"

    # Fetch notifications list
    r = requests.get(f"{API}/notifications?limit=100", headers=_auth(buyer_tok), timeout=15)
    assert r.status_code == 200
    notifs = r.json()["notifications"]
    unread = [n for n in notifs if not n.get("readAt")]
    assert len(unread) >= 1
    first_id = unread[0]["notificationId"]

    # Mark single notification read
    r = requests.post(f"{API}/notifications/{first_id}/read", headers=_auth(buyer_tok), timeout=15)
    assert r.status_code in (200, 201), r.text
    body = r.json()
    assert body["notification"]["readAt"] is not None

    # Unread count should have decremented by exactly 1
    r = requests.get(f"{API}/notifications/unread-count", headers=_auth(buyer_tok), timeout=15)
    assert r.status_code == 200
    count_after = r.json()["unreadCount"]
    assert count_after == count_before - 1, f"expected {count_before - 1}, got {count_after}"


def test_mark_all_read_zeros_unread(accounts):
    buyer_tok = accounts["buyer_token"]

    # Create another unread notification: buyer places an order that gets rejected? Simpler:
    # Use seller→buyer flow by creating an order then seller rejects.
    # But to keep test focused, just call mark-all-read and confirm count == 0.

    r = requests.post(f"{API}/notifications/read-all", headers=_auth(buyer_tok), timeout=15)
    assert r.status_code in (200, 201), r.text
    body = r.json()
    assert "markedCount" in body

    # Verify GET unread-count is now 0
    r = requests.get(f"{API}/notifications/unread-count", headers=_auth(buyer_tok), timeout=15)
    assert r.status_code == 200
    assert r.json()["unreadCount"] == 0


def test_list_notifications_shape(accounts):
    r = requests.get(f"{API}/notifications?limit=100", headers=_auth(accounts["buyer_token"]), timeout=15)
    assert r.status_code == 200
    data = r.json()
    assert "notifications" in data and isinstance(data["notifications"], list)
    assert "unreadCount" in data
