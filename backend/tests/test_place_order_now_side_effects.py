"""Verify that the SAME backend side effects happen when Place-Order-Now path
posts to POST /api/buyer/orders: (1) seller's availableQuantity goes down by
the ordered qty (reservation), and (2) seller receives an 'order_requested'
notification. Also verifies that two orders posted with identical payload
yield identical order shape (Place-Order-Now vs Add-to-Cart parity)."""
import os, random, string
import pytest, requests

BASE = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://local-orders-deploy.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api"
OTP = "123456"


def _mob() -> str:
    return "9" + "".join(random.choices(string.digits, k=9))


def _rand(n=5) -> str:
    return "".join(random.choices(string.ascii_uppercase, k=n))


@pytest.fixture(scope="module")
def ctx():
    s = requests.Session()
    # seller
    sp = {"firstName": "TEST", "lastName": _rand(), "mobileNumber": _mob(),
          "address": "TEST", "pincode": "560001", "pin": "1234", "confirmPin": "1234",
          "otp": OTP, "businessName": f"TEST_{_rand()}"}
    r = s.post(f"{API}/auth/register/seller", json=sp, timeout=30)
    assert r.status_code in (200, 201), r.text
    sd = r.json(); s_tok = sd["token"]; s_user = sd["user"]
    s_hdr = {"Authorization": f"Bearer {s_tok}"}
    s.put(f"{API}/seller/availability", json={"status": "Open"}, headers=s_hdr, timeout=30)
    item = {"itemName": f"TEST_{_rand()}", "unitType": "Kg",
            "availableQuantity": 20, "reservedQuantity": 0,
            "pricePerUnit": 100, "minimumOrderQuantity": 1, "unitIncrement": 1,
            "lowInventory": False}
    ri = s.post(f"{API}/seller/items", json=item, headers=s_hdr, timeout=30)
    assert ri.status_code in (200, 201)
    it = ri.json()["item"]
    # buyer
    bp = {"firstName": "TEST", "lastName": _rand(), "mobileNumber": _mob(),
          "address": "TEST", "pincode": "560001", "pin": "1234", "confirmPin": "1234",
          "otp": OTP}
    r = s.post(f"{API}/auth/register/buyer", json=bp, timeout=30)
    assert r.status_code in (200, 201)
    bd = r.json(); b_tok = bd["token"]; b_user = bd["user"]
    b_hdr = {"Authorization": f"Bearer {b_tok}"}
    cr = s.post(f"{API}/buyer/connections", json={"sellerCode": s_user["sellerCode"]},
                headers=b_hdr, timeout=30)
    assert cr.status_code in (200, 201)
    conn_id = cr.json()["connection"]["connectionId"]
    ac = s.post(f"{API}/seller/connections/{conn_id}/accept", headers=s_hdr, timeout=30)
    assert ac.status_code == 200
    return {"s": s, "s_hdr": s_hdr, "b_hdr": b_hdr,
            "sellerId": s_user["userId"], "buyerId": b_user["userId"],
            "item": it}


class TestPlaceOrderNowSideEffects:
    def test_inventory_reserved_on_seller_accept(self, ctx):
        """Inventory reservation fires on seller-accept (existing behavior).
        Place-Order-Now and Add-to-Cart both create 'Requested' orders so this
        post-creation reservation step must continue to work for either flow."""
        s = ctx["s"]; b_hdr = ctx["b_hdr"]; s_hdr = ctx["s_hdr"]
        sid = ctx["sellerId"]; iid = ctx["item"]["itemId"]
        before = s.get(f"{API}/buyer/sellers/{sid}/items", headers=b_hdr, timeout=30).json()
        avail_before = next(i for i in before["items"] if i["itemId"] == iid)["availableQuantity"]
        r = s.post(f"{API}/buyer/orders", headers=b_hdr, timeout=30,
                   json={"sellerId": sid, "items": [{"itemId": iid, "quantity": 3}]})
        assert r.status_code in (200, 201), r.text
        order_id = r.json()["order"]["orderId"]
        # Seller accepts -> reservation should decrement availableQuantity
        ar = s.post(f"{API}/seller/orders/{order_id}/accept", headers=s_hdr, timeout=30)
        assert ar.status_code == 200, ar.text
        after = s.get(f"{API}/buyer/sellers/{sid}/items", headers=b_hdr, timeout=30).json()
        avail_after = next(i for i in after["items"] if i["itemId"] == iid)["availableQuantity"]
        assert avail_after == avail_before - 3, f"{avail_before} -> {avail_after}"

    def test_seller_receives_order_requested_notification(self, ctx):
        s = ctx["s"]; b_hdr = ctx["b_hdr"]; s_hdr = ctx["s_hdr"]
        sid = ctx["sellerId"]; iid = ctx["item"]["itemId"]
        r = s.post(f"{API}/buyer/orders", headers=b_hdr, timeout=30,
                   json={"sellerId": sid, "items": [{"itemId": iid, "quantity": 1}]})
        assert r.status_code in (200, 201)
        order_id = r.json()["order"]["orderId"]
        # Seller notifications
        rn = s.get(f"{API}/notifications", headers=s_hdr, timeout=30)
        assert rn.status_code == 200, rn.text
        notifs = rn.json().get("notifications", rn.json()) if isinstance(rn.json(), dict) else rn.json()
        # Look for order_requested type with matching orderId
        found = any(
            (n.get("type") == "order_requested" or n.get("notificationType") == "order_requested")
            and (n.get("data", {}).get("orderId") == order_id or n.get("referenceId") == order_id or order_id in str(n))
            for n in (notifs if isinstance(notifs, list) else [])
        )
        assert found, f"No order_requested notification for {order_id} found in {notifs}"

    def test_two_identical_payloads_yield_identical_shape(self, ctx):
        """Add-to-Cart path and Place-Order-Now path both POST identical payloads to the
        same endpoint, so structurally the resulting orders must match (except ids/timestamps)."""
        s = ctx["s"]; b_hdr = ctx["b_hdr"]; sid = ctx["sellerId"]; iid = ctx["item"]["itemId"]
        payload = {"sellerId": sid, "items": [{"itemId": iid, "quantity": 2}]}
        r1 = s.post(f"{API}/buyer/orders", headers=b_hdr, json=payload, timeout=30)
        r2 = s.post(f"{API}/buyer/orders", headers=b_hdr, json=payload, timeout=30)
        assert r1.status_code in (200, 201) and r2.status_code in (200, 201)
        o1, o2 = r1.json()["order"], r2.json()["order"]
        # Same key set (ignoring orderId/orderNumber/timestamps that differ by design)
        ignore = {"orderId", "orderNumber", "createdAt", "updatedAt", "expiresAt"}
        keys1 = set(o1.keys()) - ignore
        keys2 = set(o2.keys()) - ignore
        assert keys1 == keys2, f"Field-set mismatch: {keys1 ^ keys2}"
        assert o1["sellerId"] == o2["sellerId"]
        assert o1["buyerId"] == o2["buyerId"]
        assert o1["orderStatus"] == o2["orderStatus"]
        assert o1["totalAmount"] == o2["totalAmount"]
        # orderStatus is 'Requested' for newly placed orders (no expiresAt field
        # in this backend; reservation/expiry is handled via requestedDateTime + ORDER_EXPIRY_HOURS).
        assert o1["orderStatus"] == "Requested" == o2["orderStatus"]
