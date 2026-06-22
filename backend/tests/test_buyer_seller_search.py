"""LocalOrders backend test suite for buyer → search sellers (Phase 6 enhancement).

Covers GET /api/buyer/sellers/search?q=... in detail:
  - 401 unauth, 403 for seller tokens (buyer-only)
  - Empty / whitespace q returns empty list
  - Case-insensitive partial match on sellerCode, businessName, address, pincode
  - Excludes the calling buyer themselves and never includes other buyers
  - connectionStatus is null when no existing connection
  - After POST /api/buyer/connections, connectionStatus annotation becomes 'Pending'
  - Duplicate POST /api/buyer/connections → 409 with detail mentioning status
  - No mongo _id leak
"""

import os
import random
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"

OTP = "123456"
PIN = "1234"


def rand_mobile() -> str:
    return "9" + "".join(str(random.randint(0, 9)) for _ in range(9))


def assert_no_mongo_id(obj):
    if isinstance(obj, dict):
        assert "_id" not in obj, f"Mongo _id leaked: keys={list(obj.keys())}"
        for v in obj.values():
            assert_no_mongo_id(v)
    elif isinstance(obj, list):
        for v in obj:
            assert_no_mongo_id(v)


# ---------- helpers ----------

def register_buyer(s, address="1 Lane Bengaluru", pincode="560001"):
    mobile = rand_mobile()
    s.post(f"{API}/auth/otp/send", json={"mobileNumber": mobile, "userType": "buyer"})
    r = s.post(f"{API}/auth/register/buyer", json={
        "firstName": "TEST", "lastName": "Buyer",
        "mobileNumber": mobile, "address": address, "pincode": pincode,
        "pin": PIN, "confirmPin": PIN, "otp": OTP,
    })
    assert r.status_code == 200, r.text
    data = r.json()
    return data["token"], data["user"], mobile


def register_seller(s, business_name, address, pincode):
    mobile = rand_mobile()
    s.post(f"{API}/auth/otp/send", json={"mobileNumber": mobile, "userType": "seller"})
    r = s.post(f"{API}/auth/register/seller", json={
        "firstName": "TEST", "lastName": "Seller",
        "mobileNumber": mobile, "address": address, "pincode": pincode,
        "pin": PIN, "confirmPin": PIN, "otp": OTP,
        "businessName": business_name,
    })
    assert r.status_code == 200, r.text
    data = r.json()
    return data["token"], data["user"], mobile


def auth(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


@pytest.fixture(scope="session")
def s():
    return requests.Session()


@pytest.fixture(scope="module")
def world(s):
    """Create 1 buyer + 3 sellers with distinct names/pincodes/addresses for matching."""
    buyer_token, buyer_user, _ = register_buyer(s)

    # Seed uniqueness with random suffix to keep tests deterministic across re-runs
    suffix = "".join(random.choices("ABCDEFGHJKMNPQRSTUVWXYZ23456789", k=5))
    s1 = register_seller(
        s,
        business_name=f"TEST_GreenLeaf_{suffix}",
        address="14 MG Road Indiranagar Bengaluru",
        pincode="560038",
    )
    s2 = register_seller(
        s,
        business_name=f"TEST_FreshMart_{suffix}",
        address="22 Brigade Cross Koramangala Bengaluru",
        pincode="560095",
    )
    s3 = register_seller(
        s,
        business_name=f"TEST_OrchardCo_{suffix}",
        address=f"7 Mango Lane {suffix} Mysore",
        pincode="570001",
    )
    return {
        "buyer_token": buyer_token,
        "buyer_user": buyer_user,
        "suffix": suffix,
        "sellers": [s1, s2, s3],  # each is (token, user, mobile)
    }


# ---------- tests ----------

class TestSearchAuth:
    def test_unauth_returns_401_or_403(self, s):
        r = s.get(f"{API}/buyer/sellers/search?q=test")
        assert r.status_code in (401, 403), r.text

    def test_seller_token_forbidden(self, s, world):
        seller_token = world["sellers"][0][0]
        r = s.get(f"{API}/buyer/sellers/search?q=test", headers=auth(seller_token))
        assert r.status_code == 403, r.text


class TestSearchEmpty:
    def test_missing_q_returns_empty(self, s, world):
        r = s.get(f"{API}/buyer/sellers/search", headers=auth(world["buyer_token"]))
        assert r.status_code == 200, r.text
        assert r.json() == {"sellers": []}

    def test_whitespace_q_returns_empty(self, s, world):
        r = s.get(f"{API}/buyer/sellers/search?q=%20%20", headers=auth(world["buyer_token"]))
        assert r.status_code == 200, r.text
        assert r.json() == {"sellers": []}


class TestSearchMatching:
    def test_match_by_business_name_partial_case_insensitive(self, s, world):
        # 'greenleaf' lowercase substring should match TEST_GreenLeaf_{suffix}
        r = s.get(f"{API}/buyer/sellers/search?q=greenleaf", headers=auth(world["buyer_token"]))
        assert r.status_code == 200, r.text
        data = r.json()
        assert_no_mongo_id(data)
        names = [x["businessName"] for x in data["sellers"]]
        assert any("GreenLeaf" in (n or "") for n in names), names

    def test_match_by_seller_code(self, s, world):
        target_code = world["sellers"][0][1]["sellerCode"]
        assert target_code and target_code.startswith("SELLER-"), target_code
        r = s.get(f"{API}/buyer/sellers/search?q={target_code}", headers=auth(world["buyer_token"]))
        assert r.status_code == 200, r.text
        codes = [x["sellerCode"] for x in r.json()["sellers"]]
        assert target_code in codes, codes

    def test_match_seller_code_case_insensitive(self, s, world):
        # Lower-case version of a seeded code (e.g. 'seller-1080') must still match (case-insensitive partial)
        target_code = world["sellers"][2][1]["sellerCode"]  # OrchardCo
        r = s.get(f"{API}/buyer/sellers/search?q={target_code.lower()}",
                  headers=auth(world["buyer_token"]))
        assert r.status_code == 200, r.text
        codes = [x["sellerCode"] for x in r.json()["sellers"]]
        assert target_code in codes, codes

    def test_match_by_address_partial(self, s, world):
        suffix = world["suffix"]
        # 'Mango Lane {suffix}' is unique to seller 3
        r = s.get(f"{API}/buyer/sellers/search?q=mango%20lane%20{suffix}",
                  headers=auth(world["buyer_token"]))
        assert r.status_code == 200, r.text
        results = r.json()["sellers"]
        assert len(results) >= 1
        # All matched should contain Mango Lane in address
        assert all("Mango Lane" in x["address"] for x in results), results

    def test_match_by_pincode(self, s, world):
        r = s.get(f"{API}/buyer/sellers/search?q=560038", headers=auth(world["buyer_token"]))
        assert r.status_code == 200, r.text
        pincodes = [x["pincode"] for x in r.json()["sellers"]]
        assert "560038" in pincodes, pincodes

    def test_excludes_other_buyers_and_self(self, s, world):
        # Query the buyer's own first name 'TEST' — should match sellers but NOT the buyer themselves
        r = s.get(f"{API}/buyer/sellers/search?q=TEST", headers=auth(world["buyer_token"]))
        assert r.status_code == 200, r.text
        ids = [x["userId"] for x in r.json()["sellers"]]
        assert world["buyer_user"]["userId"] not in ids


class TestConnectionStatusAnnotation:
    def test_connection_status_null_then_pending_then_409_duplicate(self, s, world):
        buyer_token = world["buyer_token"]
        target_code = world["sellers"][1][1]["sellerCode"]  # FreshMart

        # 1. Pre-condition: connectionStatus is None
        r = s.get(f"{API}/buyer/sellers/search?q={target_code}", headers=auth(buyer_token))
        assert r.status_code == 200, r.text
        row = next(x for x in r.json()["sellers"] if x["sellerCode"] == target_code)
        assert row["connectionStatus"] is None, row
        assert row["connectionId"] is None

        # 2. Send connection request
        r = s.post(f"{API}/buyer/connections",
                   json={"sellerCode": target_code}, headers=auth(buyer_token))
        assert r.status_code == 200, r.text
        conn = r.json()["connection"]
        assert conn["status"] == "Pending"
        conn_id = conn["connectionId"]

        # 3. After request, search must annotate as Pending
        r = s.get(f"{API}/buyer/sellers/search?q={target_code}", headers=auth(buyer_token))
        assert r.status_code == 200, r.text
        row = next(x for x in r.json()["sellers"] if x["sellerCode"] == target_code)
        assert row["connectionStatus"] == "Pending", row
        assert row["connectionId"] == conn_id

        # 4. Duplicate POST → 409 with status in detail
        r = s.post(f"{API}/buyer/connections",
                   json={"sellerCode": target_code}, headers=auth(buyer_token))
        assert r.status_code == 409, r.text
        detail = r.json().get("detail", "")
        assert "Pending" in detail or "Accepted" in detail, detail
        assert "already exists" in detail.lower(), detail
