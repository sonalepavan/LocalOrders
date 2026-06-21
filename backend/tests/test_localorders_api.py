"""LocalOrders Phase 1 backend test suite.

Covers:
  - OTP send (valid / duplicate / invalid mobile)
  - Buyer & seller registration (OTP/PIN validation, duplicate, seller code sequence)
  - PIN format validation (Pydantic)
  - Login success / wrong PIN remaining counter / 5-strike lockout
  - GET /api/auth/me with and without token
  - PUT /api/users/me (buyer cannot set businessName, seller can)
  - Seller inventory CRUD (buyer 403, soft delete, include_inactive)
  - unitType whitelist validation
  - Response cleanliness: no Mongo "_id" anywhere
"""

import os
import random
import time
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://local-orders-app.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

UNIT_TYPES = ["Piece", "Bottle", "Packet", "Kg", "Gram", "Litre", "ml", "Dozen", "Can", "Box"]


def rand_mobile() -> str:
    # 10-digit mobile not starting with 0
    return "9" + "".join(str(random.randint(0, 9)) for _ in range(9))


def assert_no_mongo_id(obj):
    if isinstance(obj, dict):
        assert "_id" not in obj, f"Mongo _id leaked in {obj}"
        for v in obj.values():
            assert_no_mongo_id(v)
    elif isinstance(obj, list):
        for v in obj:
            assert_no_mongo_id(v)


@pytest.fixture(scope="session")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


# ---------- OTP send ----------

class TestOtp:
    def test_otp_send_success(self, s):
        m = rand_mobile()
        r = s.post(f"{API}/auth/otp/send", json={"mobileNumber": m, "userType": "buyer"})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("sent") is True
        assert data.get("mockOtp") == "123456"
        assert_no_mongo_id(data)

    def test_otp_send_invalid_mobile(self, s):
        r = s.post(f"{API}/auth/otp/send", json={"mobileNumber": "123", "userType": "buyer"})
        assert r.status_code == 400, r.text

    def test_otp_send_duplicate_mobile(self, s):
        # register a buyer first, then try otp send for same mobile
        m = rand_mobile()
        reg = s.post(f"{API}/auth/register/buyer", json={
            "firstName": "Dup", "lastName": "User", "mobileNumber": m,
            "address": "addr", "pincode": "560001",
            "pin": "1234", "confirmPin": "1234", "otp": "123456",
        })
        assert reg.status_code == 200, reg.text
        r = s.post(f"{API}/auth/otp/send", json={"mobileNumber": m, "userType": "buyer"})
        assert r.status_code == 409, r.text


# ---------- Registration ----------

class TestRegister:
    def test_buyer_register_success(self, s):
        m = rand_mobile()
        r = s.post(f"{API}/auth/register/buyer", json={
            "firstName": "Alice", "lastName": "B", "mobileNumber": m,
            "address": "addr", "pincode": "560001",
            "pin": "1234", "confirmPin": "1234", "otp": "123456",
        })
        assert r.status_code == 200, r.text
        data = r.json()
        assert "token" in data and "user" in data
        u = data["user"]
        assert u["userType"] == "buyer"
        assert u["mobileNumber"] == m
        assert u["isMobileVerified"] is True
        assert u["sellerCode"] is None
        assert_no_mongo_id(data)

    def test_buyer_register_pin_mismatch(self, s):
        m = rand_mobile()
        r = s.post(f"{API}/auth/register/buyer", json={
            "firstName": "A", "lastName": "B", "mobileNumber": m,
            "address": "addr", "pincode": "560001",
            "pin": "1234", "confirmPin": "5678", "otp": "123456",
        })
        assert r.status_code == 400, r.text

    def test_buyer_register_wrong_otp(self, s):
        m = rand_mobile()
        r = s.post(f"{API}/auth/register/buyer", json={
            "firstName": "A", "lastName": "B", "mobileNumber": m,
            "address": "addr", "pincode": "560001",
            "pin": "1234", "confirmPin": "1234", "otp": "000000",
        })
        assert r.status_code == 400, r.text

    def test_buyer_register_duplicate(self, s):
        m = rand_mobile()
        payload = {
            "firstName": "Dup", "lastName": "B", "mobileNumber": m,
            "address": "addr", "pincode": "560001",
            "pin": "1234", "confirmPin": "1234", "otp": "123456",
        }
        r1 = s.post(f"{API}/auth/register/buyer", json=payload)
        assert r1.status_code == 200
        r2 = s.post(f"{API}/auth/register/buyer", json=payload)
        assert r2.status_code == 409

    @pytest.mark.parametrize("pin", ["12", "12345", "abcd", "12a4"])
    def test_pin_format_validation(self, s, pin):
        m = rand_mobile()
        r = s.post(f"{API}/auth/register/buyer", json={
            "firstName": "A", "lastName": "B", "mobileNumber": m,
            "address": "addr", "pincode": "560001",
            "pin": pin, "confirmPin": pin, "otp": "123456",
        })
        assert r.status_code == 422, f"pin={pin} -> {r.status_code} {r.text}"

    def test_seller_register_and_code_sequence(self, s):
        codes = []
        for _ in range(2):
            m = rand_mobile()
            r = s.post(f"{API}/auth/register/seller", json={
                "firstName": "Sam", "lastName": "S", "mobileNumber": m,
                "address": "addr", "pincode": "560001",
                "pin": "1234", "confirmPin": "1234", "otp": "123456",
                "businessName": "Sam Biz",
            })
            assert r.status_code == 200, r.text
            u = r.json()["user"]
            assert u["userType"] == "seller"
            assert u["businessName"] == "Sam Biz"
            assert u["sellerCode"] and u["sellerCode"].startswith("SELLER-")
            num = int(u["sellerCode"].split("-")[1])
            assert num >= 1001
            codes.append(num)
        assert codes[1] == codes[0] + 1, f"Seller codes not incrementing: {codes}"


# ---------- Login + lockout ----------

class TestLogin:
    @pytest.fixture(scope="class")
    def buyer(self, s):
        m = rand_mobile()
        r = s.post(f"{API}/auth/register/buyer", json={
            "firstName": "Login", "lastName": "User", "mobileNumber": m,
            "address": "addr", "pincode": "560001",
            "pin": "1234", "confirmPin": "1234", "otp": "123456",
        })
        assert r.status_code == 200
        return {"mobile": m, "pin": "1234", "token": r.json()["token"], "user": r.json()["user"]}

    def test_login_success(self, s, buyer):
        r = s.post(f"{API}/auth/login", json={"mobileNumber": buyer["mobile"], "pin": buyer["pin"]})
        assert r.status_code == 200, r.text
        assert "token" in r.json()

    def test_login_wrong_pin_counter(self, s):
        m = rand_mobile()
        s.post(f"{API}/auth/register/buyer", json={
            "firstName": "WP", "lastName": "U", "mobileNumber": m, "address": "a", "pincode": "1",
            "pin": "1234", "confirmPin": "1234", "otp": "123456",
        }).raise_for_status()
        r = s.post(f"{API}/auth/login", json={"mobileNumber": m, "pin": "9999"})
        assert r.status_code == 401
        assert "4 attempts remaining" in r.json().get("detail", ""), r.text
        # success after wrong PIN resets counter
        ok = s.post(f"{API}/auth/login", json={"mobileNumber": m, "pin": "1234"})
        assert ok.status_code == 200
        # next wrong attempt should be "4 remaining" again (counter reset)
        r2 = s.post(f"{API}/auth/login", json={"mobileNumber": m, "pin": "9999"})
        assert r2.status_code == 401
        assert "4 attempts remaining" in r2.json().get("detail", "")

    def test_login_lockout_after_5_failures(self, s):
        m = rand_mobile()
        s.post(f"{API}/auth/register/buyer", json={
            "firstName": "LK", "lastName": "U", "mobileNumber": m, "address": "a", "pincode": "1",
            "pin": "1234", "confirmPin": "1234", "otp": "123456",
        }).raise_for_status()
        last = None
        for i in range(5):
            last = s.post(f"{API}/auth/login", json={"mobileNumber": m, "pin": "0000"})
        # 5th failure should return 423
        assert last.status_code == 423, f"expected 423 on 5th failure, got {last.status_code}: {last.text}"
        # subsequent login attempts (even correct PIN) should remain 423 while locked
        r = s.post(f"{API}/auth/login", json={"mobileNumber": m, "pin": "1234"})
        assert r.status_code == 423


# ---------- /auth/me ----------

class TestMe:
    def test_me_no_token(self, s):
        r = requests.get(f"{API}/auth/me")
        assert r.status_code == 401

    def test_me_bad_token(self, s):
        r = requests.get(f"{API}/auth/me", headers={"Authorization": "Bearer not-a-jwt"})
        assert r.status_code == 401

    def test_me_with_token(self, s):
        m = rand_mobile()
        reg = s.post(f"{API}/auth/register/buyer", json={
            "firstName": "Me", "lastName": "U", "mobileNumber": m, "address": "a", "pincode": "1",
            "pin": "1234", "confirmPin": "1234", "otp": "123456",
        })
        token = reg.json()["token"]
        r = requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        body = r.json()
        assert body["user"]["mobileNumber"] == m
        assert_no_mongo_id(body)


# ---------- Profile update ----------

class TestProfileUpdate:
    def _register(self, s, kind="buyer"):
        m = rand_mobile()
        payload = {
            "firstName": "F", "lastName": "L", "mobileNumber": m, "address": "a", "pincode": "1",
            "pin": "1234", "confirmPin": "1234", "otp": "123456",
        }
        if kind == "seller":
            payload["businessName"] = "B"
        r = s.post(f"{API}/auth/register/{kind}", json=payload)
        assert r.status_code == 200, r.text
        return r.json()["token"], r.json()["user"]

    def test_buyer_can_update_name_address(self, s):
        token, _ = self._register(s, "buyer")
        h = {"Authorization": f"Bearer {token}"}
        r = requests.put(f"{API}/users/me", json={"firstName": "New", "lastName": "Name", "address": "NewAddr"}, headers=h)
        assert r.status_code == 200, r.text
        u = r.json()["user"]
        assert u["firstName"] == "New" and u["lastName"] == "Name" and u["address"] == "NewAddr"

    def test_buyer_cannot_set_business_name(self, s):
        token, _ = self._register(s, "buyer")
        h = {"Authorization": f"Bearer {token}"}
        r = requests.put(f"{API}/users/me", json={"businessName": "Nope"}, headers=h)
        assert r.status_code == 400

    def test_seller_can_set_business_name(self, s):
        token, _ = self._register(s, "seller")
        h = {"Authorization": f"Bearer {token}"}
        r = requests.put(f"{API}/users/me", json={"businessName": "New Biz"}, headers=h)
        assert r.status_code == 200, r.text
        assert r.json()["user"]["businessName"] == "New Biz"


# ---------- Inventory CRUD ----------

class TestInventory:
    @pytest.fixture(scope="class")
    def seller_token(self, s):
        m = rand_mobile()
        r = s.post(f"{API}/auth/register/seller", json={
            "firstName": "Inv", "lastName": "S", "mobileNumber": m, "address": "a", "pincode": "1",
            "pin": "1234", "confirmPin": "1234", "otp": "123456", "businessName": "InvBiz",
        })
        assert r.status_code == 200
        return r.json()["token"]

    @pytest.fixture(scope="class")
    def buyer_token(self, s):
        m = rand_mobile()
        r = s.post(f"{API}/auth/register/buyer", json={
            "firstName": "Inv", "lastName": "B", "mobileNumber": m, "address": "a", "pincode": "1",
            "pin": "1234", "confirmPin": "1234", "otp": "123456",
        })
        assert r.status_code == 200
        return r.json()["token"]

    def test_buyer_cannot_access_inventory(self, s, buyer_token):
        h = {"Authorization": f"Bearer {buyer_token}"}
        assert requests.get(f"{API}/seller/items", headers=h).status_code == 403
        r = requests.post(f"{API}/seller/items", json={
            "itemName": "x", "unitType": "Piece", "availableQuantity": 1,
            "pricePerUnit": 1, "minimumOrderQuantity": 1, "unitIncrement": 1,
        }, headers=h)
        assert r.status_code == 403

    def test_full_crud_and_soft_delete(self, s, seller_token):
        h = {"Authorization": f"Bearer {seller_token}"}
        # create
        c = requests.post(f"{API}/seller/items", json={
            "itemName": "Rice", "unitType": "Kg", "availableQuantity": 50,
            "pricePerUnit": 60, "minimumOrderQuantity": 1, "unitIncrement": 0.5,
        }, headers=h)
        assert c.status_code == 200, c.text
        item = c.json()["item"]
        assert item["isActive"] is True
        assert_no_mongo_id(c.json())
        iid = item["itemId"]

        # list active
        L = requests.get(f"{API}/seller/items", headers=h)
        assert L.status_code == 200
        ids = [i["itemId"] for i in L.json()["items"]]
        assert iid in ids

        # update
        u = requests.put(f"{API}/seller/items/{iid}", json={
            "itemName": "Basmati Rice", "unitType": "Kg", "availableQuantity": 40,
            "pricePerUnit": 80, "minimumOrderQuantity": 2, "unitIncrement": 1,
        }, headers=h)
        assert u.status_code == 200, u.text
        assert u.json()["item"]["itemName"] == "Basmati Rice"
        assert u.json()["item"]["pricePerUnit"] == 80

        # soft delete
        d = requests.delete(f"{API}/seller/items/{iid}", headers=h)
        assert d.status_code == 200

        # active list should NOT contain it
        L2 = requests.get(f"{API}/seller/items", headers=h)
        assert iid not in [i["itemId"] for i in L2.json()["items"]]

        # include_inactive should contain it with isActive=false
        L3 = requests.get(f"{API}/seller/items?include_inactive=true", headers=h)
        found = [i for i in L3.json()["items"] if i["itemId"] == iid]
        assert found and found[0]["isActive"] is False

    def test_invalid_unit_type(self, s, seller_token):
        h = {"Authorization": f"Bearer {seller_token}"}
        r = requests.post(f"{API}/seller/items", json={
            "itemName": "x", "unitType": "Bucket", "availableQuantity": 1,
            "pricePerUnit": 1, "minimumOrderQuantity": 1, "unitIncrement": 1,
        }, headers=h)
        assert r.status_code == 422

    def test_all_allowed_unit_types(self, s, seller_token):
        h = {"Authorization": f"Bearer {seller_token}"}
        for ut in UNIT_TYPES:
            r = requests.post(f"{API}/seller/items", json={
                "itemName": f"Item-{ut}", "unitType": ut, "availableQuantity": 1,
                "pricePerUnit": 1, "minimumOrderQuantity": 1, "unitIncrement": 1,
            }, headers=h)
            assert r.status_code == 200, f"{ut}: {r.text}"


# ---------- Meta ----------

class TestMeta:
    def test_unit_types_endpoint(self, s):
        r = requests.get(f"{API}/meta/unit-types")
        assert r.status_code == 200
        assert r.json()["unitTypes"] == UNIT_TYPES
