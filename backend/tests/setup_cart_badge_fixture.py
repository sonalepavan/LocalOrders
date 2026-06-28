"""Seed a buyer + seller pair with an accepted connection and 2 active items.

Prints a JSON blob with credentials and seller info that the Playwright UI test
consumes. Used by /app/tests/test_cart_badge_ui.py to verify the cart badge
synchronization fix on /buyer-seller-items.
"""
import json
import os
import random
import sys

import requests

BASE = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://local-orders-deploy.preview.emergentagent.com").rstrip("/")


def rand_mobile() -> str:
    return "9" + "".join(str(random.randint(0, 9)) for _ in range(9))


def reg(role: str, mobile: str, payload_extra: dict) -> str:
    r0 = requests.post(f"{BASE}/api/auth/otp/send",
                       json={"mobileNumber": mobile, "userType": role}, timeout=20)
    r0.raise_for_status()
    body = {
        "firstName": "TEST",
        "lastName": role.capitalize(),
        "mobileNumber": mobile,
        "pin": "1234",
        "confirmPin": "1234",
        "otp": "123456",
        "address": "TEST Addr",
        "pincode": "431702",
        **payload_extra,
    }
    r = requests.post(f"{BASE}/api/auth/register/{role}", json=body, timeout=20)
    r.raise_for_status()
    return r.json()["token"]


def main():
    buyer_mobile = rand_mobile()
    seller_mobile = rand_mobile()
    buyer_tok = reg("buyer", buyer_mobile, {})
    seller_tok = reg("seller", seller_mobile, {"businessName": "TEST Cart Badge Shop"})

    seller_hdr = {"Authorization": f"Bearer {seller_tok}"}
    buyer_hdr = {"Authorization": f"Bearer {buyer_tok}"}

    # Get seller profile to find sellerCode
    me = requests.get(f"{BASE}/api/auth/me", headers=seller_hdr, timeout=20).json()
    seller_code = me["user"].get("sellerCode") or me.get("sellerCode")
    seller_id = me["user"].get("userId") or me["user"].get("id")
    assert seller_code, f"Missing seller code in {me}"

    # Buyer sends connection request, seller accepts
    cr = requests.post(f"{BASE}/api/buyer/connections", headers=buyer_hdr,
                      json={"sellerCode": seller_code}, timeout=20)
    cr.raise_for_status()
    conn_id = cr.json()["connection"]["connectionId"]

    ac = requests.post(f"{BASE}/api/seller/connections/{conn_id}/accept", headers=seller_hdr, timeout=20)
    ac.raise_for_status()

    # Create 2 items
    items = []
    for i in range(2):
        body = {
            "itemName": f"TEST Item {i+1}",
            "unitType": "Kg",
            "pricePerUnit": 50 + i * 10,
            "minimumOrderQuantity": 1,
            "unitIncrement": 1,
            "availableQuantity": 100,
        }
        r = requests.post(f"{BASE}/api/seller/items", headers=seller_hdr, json=body, timeout=20)
        r.raise_for_status()
        items.append(r.json()["item"])

    print(json.dumps({
        "buyer_mobile": buyer_mobile,
        "seller_mobile": seller_mobile,
        "seller_id": seller_id,
        "seller_code": seller_code,
        "items": [{"itemId": it["itemId"], "itemName": it["itemName"]} for it in items],
    }))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
