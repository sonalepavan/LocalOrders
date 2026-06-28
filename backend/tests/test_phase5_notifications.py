"""LocalOrders Phase 5 backend test suite — Notifications & Push.

Covers:
  - GET /api/ heartbeat
  - POST /api/buyer/connections triggers a 'connection_request' notification for the seller
  - GET /api/notifications, /api/notifications/unread-count, POST /api/notifications/{id}/read,
    POST /api/notifications/read-all
  - Connection accept/reject → connection_accepted / connection_rejected
  - Order lifecycle notifications:
      * order_requested  → seller
      * order_accepted   → buyer
      * order_rejected   → buyer
      * order_cancelled  → seller
      * order_delivered  → buyer
  - POST /api/register-push returns 500 with the documented detail when
    EMERGENT_PUSH_KEY='placeholder' (expected per spec — pipeline injects real key).
  - notify_user persists an in-app notification even when the push relay 401s
    (push failures are non-blocking).
  - No Mongo _id leakage in notification responses.
"""

import os
import random
import time
import pytest
import requests

BASE_URL = os.environ.get(
    "EXPO_PUBLIC_BACKEND_URL",
    "https://local-orders-app-1.preview.emergentagent.com",
).rstrip("/")
API = f"{BASE_URL}/api"

OTP = "123456"
PIN = "1234"


def rand_mobile() -> str:
    return "9" + "".join(str(random.randint(0, 9)) for _ in range(9))


def assert_no_mongo_id(obj):
    if isinstance(obj, dict):
        assert "_id" not in obj, f"Mongo _id leaked: {obj}"
        for v in obj.values():
            assert_no_mongo_id(v)
    elif isinstance(obj, list):
        for v in obj:
            assert_no_mongo_id(v)


def auth(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ---------- registration helpers ----------

def register_buyer(s):
    mobile = rand_mobile()
    s.post(f"{API}/auth/otp/send", json={"mobileNumber": mobile, "userType": "buyer"})
    r = s.post(f"{API}/auth/register/buyer", json={
        "firstName": "TEST", "lastName": "Buyer",
        "mobileNumber": mobile, "address": "1 Lane", "pincode": "560001",
        "pin": PIN, "confirmPin": PIN, "otp": OTP,
    })
    assert r.status_code == 200, r.text
    d = r.json()
    return d["token"], d["user"]


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
    d = r.json()
    return d["token"], d["user"]


def create_item(s, seller_token, **overrides):
    payload = {
        "itemName": "Tomato",
        "unitType": "Kg",
        "availableQuantity": 100.0,
        "pricePerUnit": 25.0,
        "minimumOrderQuantity": 1.0,
        "unitIncrement": 1.0,
    }
    payload.update(overrides)
    r = s.post(f"{API}/seller/items", json=payload, headers=auth(seller_token))
    assert r.status_code == 200, r.text
    return r.json()["item"]


def connect_pair(s):
    """Register a buyer + seller, create an Accepted connection, return tokens+ids+item."""
    b_token, b_user = register_buyer(s)
    s_token, s_user = register_seller(s)
    seller_code = s_user["sellerCode"]
    # buyer requests
    r = s.post(f"{API}/buyer/connections", json={"sellerCode": seller_code}, headers=auth(b_token))
    assert r.status_code == 200, r.text
    conn_id = r.json()["connection"]["connectionId"]
    # seller accepts
    r = s.post(f"{API}/seller/connections/{conn_id}/accept", headers=auth(s_token))
    assert r.status_code == 200, r.text
    item = create_item(s, s_token)
    return {
        "b_token": b_token, "b_user": b_user,
        "s_token": s_token, "s_user": s_user,
        "connectionId": conn_id, "item": item,
    }


def place_order(s, cp, qty=2.0):
    payload = {
        "sellerId": cp["s_user"]["userId"],
        "items": [{"itemId": cp["item"]["itemId"], "quantity": qty}],
    }
    r = s.post(f"{API}/buyer/orders", json=payload, headers=auth(cp["b_token"]))
    assert r.status_code == 200, r.text
    return r.json()["order"]


def list_notifs(s, token):
    r = s.get(f"{API}/notifications", headers=auth(token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert_no_mongo_id(body)
    return body


def unread_count(s, token):
    r = s.get(f"{API}/notifications/unread-count", headers=auth(token))
    assert r.status_code == 200, r.text
    return r.json()["unreadCount"]


@pytest.fixture(scope="session")
def sess():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


# =============================================================================
# 1) Heartbeat
# =============================================================================

class TestHeartbeat:
    def test_root_returns_service_header(self, sess):
        r = sess.get(f"{API}/")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("service") == "LocalOrders API"
        assert "phase" in body


# =============================================================================
# 2) Auth gates on notifications endpoints
# =============================================================================

class TestNotificationsAuth:
    def test_list_requires_token(self, sess):
        r = sess.get(f"{API}/notifications")
        assert r.status_code in (401, 403), r.text

    def test_unread_requires_token(self, sess):
        r = sess.get(f"{API}/notifications/unread-count")
        assert r.status_code in (401, 403), r.text

    def test_read_all_requires_token(self, sess):
        r = sess.post(f"{API}/notifications/read-all")
        assert r.status_code in (401, 403), r.text

    def test_fresh_buyer_has_zero_unread(self, sess):
        token, _ = register_buyer(sess)
        body = list_notifs(sess, token)
        assert body["unreadCount"] == 0
        assert body["notifications"] == []


# =============================================================================
# 3) Connection notifications
# =============================================================================

class TestConnectionNotifications:
    def test_connection_request_notifies_seller(self, sess):
        b_token, b_user = register_buyer(sess)
        s_token, s_user = register_seller(sess)
        # buyer requests
        r = sess.post(f"{API}/buyer/connections",
                      json={"sellerCode": s_user["sellerCode"]},
                      headers=auth(b_token))
        assert r.status_code == 200, r.text

        body = list_notifs(sess, s_token)
        # Seller should have at least one 'connection_request' notification
        types = [n["type"] for n in body["notifications"]]
        assert "connection_request" in types, body
        n = next(n for n in body["notifications"] if n["type"] == "connection_request")
        # Notification shape
        for k in ("notificationId", "userId", "type", "title", "body", "data", "createdDate"):
            assert k in n, n
        assert n["userId"] == s_user["userId"]
        assert n["readAt"] is None
        assert n["data"].get("buyerId") == b_user["userId"]
        assert body["unreadCount"] >= 1
        # The buyer should NOT have this notif
        b_body = list_notifs(sess, b_token)
        b_types = [x["type"] for x in b_body["notifications"]]
        assert "connection_request" not in b_types

    def test_connection_accept_notifies_buyer(self, sess):
        b_token, b_user = register_buyer(sess)
        s_token, s_user = register_seller(sess)
        r = sess.post(f"{API}/buyer/connections",
                      json={"sellerCode": s_user["sellerCode"]},
                      headers=auth(b_token))
        conn_id = r.json()["connection"]["connectionId"]
        r = sess.post(f"{API}/seller/connections/{conn_id}/accept", headers=auth(s_token))
        assert r.status_code == 200, r.text

        body = list_notifs(sess, b_token)
        types = [n["type"] for n in body["notifications"]]
        assert "connection_accepted" in types, body
        n = next(n for n in body["notifications"] if n["type"] == "connection_accepted")
        assert n["data"].get("sellerId") == s_user["userId"]
        assert n["data"].get("connectionId") == conn_id

    def test_connection_reject_notifies_buyer(self, sess):
        b_token, _ = register_buyer(sess)
        s_token, s_user = register_seller(sess)
        r = sess.post(f"{API}/buyer/connections",
                      json={"sellerCode": s_user["sellerCode"]},
                      headers=auth(b_token))
        conn_id = r.json()["connection"]["connectionId"]
        r = sess.post(f"{API}/seller/connections/{conn_id}/reject", headers=auth(s_token))
        assert r.status_code == 200, r.text
        types = [n["type"] for n in list_notifs(sess, b_token)["notifications"]]
        assert "connection_rejected" in types


# =============================================================================
# 4) Mark-read flows
# =============================================================================

class TestMarkRead:
    def test_mark_single_read_and_read_all(self, sess):
        # Trigger 2 separate notifications (2 connection requests from 2 buyers)
        s_token, s_user = register_seller(sess)
        b1, _ = register_buyer(sess)
        b2, _ = register_buyer(sess)
        sess.post(f"{API}/buyer/connections",
                  json={"sellerCode": s_user["sellerCode"]},
                  headers=auth(b1))
        sess.post(f"{API}/buyer/connections",
                  json={"sellerCode": s_user["sellerCode"]},
                  headers=auth(b2))

        before = list_notifs(sess, s_token)
        assert before["unreadCount"] >= 2
        first_id = before["notifications"][0]["notificationId"]

        # Mark single
        r = sess.post(f"{API}/notifications/{first_id}/read", headers=auth(s_token))
        assert r.status_code == 200, r.text
        marked = r.json()["notification"]
        assert marked["readAt"] is not None
        assert_no_mongo_id(r.json())

        after_one = unread_count(sess, s_token)
        assert after_one == before["unreadCount"] - 1

        # Mark single again is idempotent on a notification that's already read.
        # It still 200s but readAt timestamp is updated.
        r2 = sess.post(f"{API}/notifications/{first_id}/read", headers=auth(s_token))
        assert r2.status_code == 200, r2.text

        # Mark-all
        r = sess.post(f"{API}/notifications/read-all", headers=auth(s_token))
        assert r.status_code == 200, r.text
        body = r.json()
        assert "markedCount" in body
        assert body["markedCount"] == after_one  # exactly the still-unread ones
        assert unread_count(sess, s_token) == 0

        # Idempotent: second read-all marks zero.
        r = sess.post(f"{API}/notifications/read-all", headers=auth(s_token))
        assert r.status_code == 200, r.text
        assert r.json()["markedCount"] == 0

    def test_mark_unknown_id_404(self, sess):
        token, _ = register_buyer(sess)
        r = sess.post(f"{API}/notifications/does-not-exist/read", headers=auth(token))
        assert r.status_code == 404, r.text

    def test_user_cannot_read_other_users_notification(self, sess):
        # Seller A gets a connection_request, buyer B (unrelated) cannot mark it read.
        s_token, s_user = register_seller(sess)
        b_token, _ = register_buyer(sess)
        sess.post(f"{API}/buyer/connections",
                  json={"sellerCode": s_user["sellerCode"]},
                  headers=auth(b_token))
        body = list_notifs(sess, s_token)
        notif_id = body["notifications"][0]["notificationId"]

        # Unrelated third party
        other_token, _ = register_buyer(sess)
        r = sess.post(f"{API}/notifications/{notif_id}/read", headers=auth(other_token))
        # The notification belongs to seller — for the other user this id is not found.
        assert r.status_code == 404, r.text


# =============================================================================
# 5) Order lifecycle notifications
# =============================================================================

class TestOrderNotifications:
    def test_order_requested_notifies_seller(self, sess):
        cp = connect_pair(sess)
        # Clear seller existing notifications by marking all read
        sess.post(f"{API}/notifications/read-all", headers=auth(cp["s_token"]))
        order = place_order(sess, cp, qty=2.0)

        body = list_notifs(sess, cp["s_token"])
        types = [n["type"] for n in body["notifications"]]
        assert "order_requested" in types, body
        n = next(n for n in body["notifications"] if n["type"] == "order_requested")
        assert n["data"].get("orderId") == order["orderId"]
        assert n["data"].get("buyerId") == cp["b_user"]["userId"]
        # Title format: "New order ORD-#####"
        assert order["orderNumber"] in n["title"]
        # Buyer should NOT have this one
        b_types = [x["type"] for x in list_notifs(sess, cp["b_token"])["notifications"]]
        assert "order_requested" not in b_types

    def test_order_accepted_notifies_buyer(self, sess):
        cp = connect_pair(sess)
        order = place_order(sess, cp, qty=2.0)
        sess.post(f"{API}/notifications/read-all", headers=auth(cp["b_token"]))
        r = sess.post(f"{API}/seller/orders/{order['orderId']}/accept",
                      headers=auth(cp["s_token"]))
        assert r.status_code == 200, r.text

        body = list_notifs(sess, cp["b_token"])
        types = [n["type"] for n in body["notifications"]]
        assert "order_accepted" in types, body
        n = next(n for n in body["notifications"] if n["type"] == "order_accepted")
        assert n["data"].get("orderId") == order["orderId"]
        assert order["orderNumber"] in n["title"]

    def test_order_rejected_notifies_buyer_with_reason(self, sess):
        cp = connect_pair(sess)
        order = place_order(sess, cp, qty=2.0)
        sess.post(f"{API}/notifications/read-all", headers=auth(cp["b_token"]))
        r = sess.post(f"{API}/seller/orders/{order['orderId']}/reject",
                      json={"reason": "Out of stock"},
                      headers=auth(cp["s_token"]))
        assert r.status_code == 200, r.text
        body = list_notifs(sess, cp["b_token"])
        n = next((x for x in body["notifications"] if x["type"] == "order_rejected"), None)
        assert n is not None, body
        assert "Out of stock" in n["body"]

    def test_order_cancelled_notifies_seller(self, sess):
        cp = connect_pair(sess)
        order = place_order(sess, cp, qty=2.0)
        sess.post(f"{API}/notifications/read-all", headers=auth(cp["s_token"]))
        r = sess.post(f"{API}/buyer/orders/{order['orderId']}/cancel",
                      json={"reason": "changed mind"},
                      headers=auth(cp["b_token"]))
        assert r.status_code == 200, r.text
        body = list_notifs(sess, cp["s_token"])
        n = next((x for x in body["notifications"] if x["type"] == "order_cancelled"), None)
        assert n is not None, body
        assert n["data"].get("orderId") == order["orderId"]
        assert "changed mind" in n["body"]

    def test_order_delivered_notifies_buyer(self, sess):
        cp = connect_pair(sess)
        order = place_order(sess, cp, qty=2.0)
        # accept -> deliver
        r = sess.post(f"{API}/seller/orders/{order['orderId']}/accept",
                      headers=auth(cp["s_token"]))
        assert r.status_code == 200, r.text
        sess.post(f"{API}/notifications/read-all", headers=auth(cp["b_token"]))
        r = sess.post(f"{API}/seller/orders/{order['orderId']}/deliver",
                      headers=auth(cp["s_token"]))
        assert r.status_code == 200, r.text
        body = list_notifs(sess, cp["b_token"])
        n = next((x for x in body["notifications"] if x["type"] == "order_delivered"), None)
        assert n is not None, body
        assert n["data"].get("orderId") == order["orderId"]


# =============================================================================
# 6) Push relay 401 must NOT block in-app notifications
# =============================================================================

class TestPushNonBlocking:
    def test_in_app_notif_persisted_even_when_push_relay_fails(self, sess):
        """The local pod has EMERGENT_PUSH_KEY='placeholder' so the relay will 401.
        notify_user is wrapped in try/except — the in-app row must still land.
        We verify this end-to-end: count notifications before vs after each event."""
        cp = connect_pair(sess)
        # Mark all existing read so we can count deltas in unreadCount
        sess.post(f"{API}/notifications/read-all", headers=auth(cp["s_token"]))
        sess.post(f"{API}/notifications/read-all", headers=auth(cp["b_token"]))

        # 1) order_requested -> seller
        s_unread_before = unread_count(sess, cp["s_token"])
        order = place_order(sess, cp, qty=2.0)
        s_unread_after = unread_count(sess, cp["s_token"])
        assert s_unread_after == s_unread_before + 1

        # 2) order_accepted -> buyer
        b_unread_before = unread_count(sess, cp["b_token"])
        sess.post(f"{API}/seller/orders/{order['orderId']}/accept",
                  headers=auth(cp["s_token"]))
        b_unread_after = unread_count(sess, cp["b_token"])
        assert b_unread_after == b_unread_before + 1

        # 3) order_delivered -> buyer (+1 more)
        sess.post(f"{API}/seller/orders/{order['orderId']}/deliver",
                  headers=auth(cp["s_token"]))
        assert unread_count(sess, cp["b_token"]) == b_unread_after + 1

    def test_endpoints_still_return_2xx_under_push_failure(self, sess):
        """If push throws inside the order/connection handler, the handler would
        500 — confirm it does NOT. (Covered implicitly above; explicit assertion here.)"""
        cp = connect_pair(sess)
        order = place_order(sess, cp, qty=1.0)
        assert "orderId" in order
        r = sess.post(f"{API}/seller/orders/{order['orderId']}/reject",
                      json={"reason": "test"},
                      headers=auth(cp["s_token"]))
        assert r.status_code == 200, r.text


# =============================================================================
# 7) register-push placeholder behavior
# =============================================================================

class TestRegisterPush:
    def test_register_push_with_placeholder_key_returns_500_with_documented_detail(self, sess):
        token, user = register_buyer(sess)
        body = {
            "user_id": user["userId"],
            "platform": "android",
            "device_token": "FAKE_FCM_TOKEN_FOR_TEST",
        }
        # No auth required by current implementation; send as anonymous client.
        r = sess.post(f"{API}/register-push", json=body)
        # The 500 status is the EXPECTED behavior per the playbook when
        # EMERGENT_PUSH_KEY=='placeholder'.
        assert r.status_code == 500, r.text
        detail = ""
        try:
            detail = r.json().get("detail", "")
        except Exception:
            pass
        assert "EMERGENT_PUSH_KEY" in detail, (
            f"Expected 'EMERGENT_PUSH_KEY missing or invalid' detail, got: {detail!r}"
        )

    def test_register_push_validates_body(self, sess):
        # Missing required fields -> 422
        r = sess.post(f"{API}/register-push", json={"platform": "android"})
        assert r.status_code == 422, r.text


# =============================================================================
# 8) Cleanliness
# =============================================================================

class TestCleanliness:
    def test_no_mongo_id_in_notification_responses(self, sess):
        cp = connect_pair(sess)
        place_order(sess, cp, qty=1.0)
        for tok in (cp["s_token"], cp["b_token"]):
            body = list_notifs(sess, tok)
            assert_no_mongo_id(body)
            r = sess.get(f"{API}/notifications/unread-count", headers=auth(tok))
            assert_no_mongo_id(r.json())
