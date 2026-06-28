"""LocalOrders backend (Phase 1).

Mirrors Firebase Firestore data shape using MongoDB collections:
  - users (Users)
  - seller_items (SellerItems)

OTP is mocked: any registration accepts `123456` as the verification code.
"""

from fastapi import FastAPI, APIRouter, HTTPException, Depends, Header, Query
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ReturnDocument
import os
import logging
import re
from pathlib import Path
from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Literal, Any, Dict
import uuid
from datetime import datetime, timezone, timedelta
import bcrypt
import jwt
import httpx


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

JWT_SECRET = os.environ.get("JWT_SECRET", "localorders-dev-secret-change-me")
JWT_ALGO = "HS256"
JWT_EXP_DAYS = 30
MOCK_OTP = "123456"
MAX_FAILED_ATTEMPTS = 5
LOCK_DURATION_MINUTES = 15

UNIT_TYPES = ["Piece", "Bottle", "Packet", "Kg", "Gram", "Litre", "ml", "Dozen", "Can", "Box"]

# ---------- Emergent Push relay ----------
PUSH_BASE_URL = "https://integrations.emergentagent.com"
PUSH_KEY = os.environ.get("EMERGENT_PUSH_KEY", "placeholder")
_push_client = httpx.AsyncClient(
    base_url=PUSH_BASE_URL,
    headers={"X-Push-Key": PUSH_KEY},
    timeout=10.0,
)


async def send_push(
    recipients: List[str],
    data: Dict[str, Any],
    idempotency_key: Optional[str] = None,
) -> None:
    """Relay a push notification to Emergent push provider (FCM/APNs).
    Wrap callers in try/except so push failure never blocks the primary operation.
    """
    if not recipients:
        return
    if len(recipients) > 100:
        raise ValueError("max 100 recipients per /trigger call")
    if "title" not in data or "message" not in data:
        raise ValueError("data must include title and message")
    payload: Dict[str, Any] = {"recipients": recipients, "data": data}
    if idempotency_key:
        payload["$idempotency_key"] = idempotency_key
    resp = await _push_client.post("/api/v1/push/trigger", json=payload)
    if resp.status_code == 401:
        raise HTTPException(500, "EMERGENT_PUSH_KEY missing or invalid")
    if resp.status_code >= 500:
        raise HTTPException(502, "Push provider unavailable")
    resp.raise_for_status()


async def notify_user(
    user_id: str,
    notif_type: str,
    title: str,
    body: str,
    data: Optional[Dict[str, Any]] = None,
) -> None:
    """Persist an in-app notification AND attempt push delivery (non-blocking)."""
    doc = {
        "notificationId": str(uuid.uuid4()),
        "userId": user_id,
        "type": notif_type,
        "title": title,
        "body": body,
        "data": data or {},
        "readAt": None,
        "createdDate": utc_now_iso(),
    }
    try:
        await db.notifications.insert_one(doc)
    except Exception as e:
        logger.warning(f"Notification persist failed (non-blocking): {e}")

    # Build deeplink for tap-to-navigate
    push_data: Dict[str, Any] = {"title": title, "message": body}
    if data and data.get("orderId"):
        push_data["action_url"] = f"/buyer-order-detail?orderId={data['orderId']}"
    elif data and data.get("connectionId"):
        push_data["action_url"] = "/(buyer)/home"
    try:
        await send_push(
            recipients=[user_id],
            data=push_data,
            idempotency_key=doc["notificationId"],
        )
    except Exception as e:
        logger.warning(f"Push notification failed (non-blocking): {e}")

app = FastAPI(title="LocalOrders API")
api_router = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


# ---------- helpers ----------

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def hash_pin(pin: str) -> str:
    return bcrypt.hashpw(pin.encode(), bcrypt.gensalt()).decode()


def verify_pin(pin: str, pin_hash: str) -> bool:
    try:
        return bcrypt.checkpw(pin.encode(), pin_hash.encode())
    except Exception:
        return False


def make_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "exp": datetime.now(timezone.utc) + timedelta(days=JWT_EXP_DAYS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)


def normalize_mobile(mobile: str) -> str:
    digits = re.sub(r"\D", "", mobile or "")
    return digits


async def next_seller_code() -> str:
    # Atomic counter
    counter = await db.counters.find_one_and_update(
        {"_id": "seller_code"},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=True,
    )
    seq = counter.get("seq", 1) if counter else 1
    if seq < 1001:
        # bump baseline so first ever code is SELLER-1001
        counter = await db.counters.find_one_and_update(
            {"_id": "seller_code"},
            {"$set": {"seq": 1001}},
            return_document=True,
        )
        seq = counter["seq"]
    return f"SELLER-{seq}"


LOW_INVENTORY_THRESHOLD = 10
AVAILABILITY_STATUSES = ["Open", "Closed"]


def user_public(doc: dict) -> dict:
    out = {
        "userId": doc["userId"],
        "userType": doc["userType"],
        "firstName": doc["firstName"],
        "lastName": doc["lastName"],
        "mobileNumber": doc["mobileNumber"],
        "address": doc.get("address", ""),
        "pincode": doc.get("pincode", ""),
        "businessName": doc.get("businessName"),
        "sellerCode": doc.get("sellerCode"),
        "isMobileVerified": doc.get("isMobileVerified", False),
        "createdDate": doc.get("createdDate"),
    }
    if doc.get("userType") == "seller":
        out["availabilityStatus"] = doc.get("availabilityStatus", "Open")
    return out


def item_public(doc: dict) -> dict:
    avail = doc["availableQuantity"]
    reserved = doc.get("reservedQuantity", 0)
    return {
        "itemId": doc["itemId"],
        "sellerId": doc["sellerId"],
        "itemName": doc["itemName"],
        "unitType": doc["unitType"],
        "availableQuantity": avail,
        "reservedQuantity": reserved,
        "pricePerUnit": doc["pricePerUnit"],
        "minimumOrderQuantity": doc["minimumOrderQuantity"],
        "unitIncrement": doc["unitIncrement"],
        "isActive": doc["isActive"],
        "lowInventory": avail < LOW_INVENTORY_THRESHOLD,
        "createdDate": doc["createdDate"],
        "updatedDate": doc["updatedDate"],
    }


async def current_user(authorization: Optional[str] = Header(None)) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user_id = payload.get("sub")
    user = await db.users.find_one({"userId": user_id}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


# ---------- models ----------

class OtpSendRequest(BaseModel):
    mobileNumber: str
    userType: Literal["buyer", "seller"]


class RegisterBuyerRequest(BaseModel):
    firstName: str
    lastName: str
    mobileNumber: str
    address: str
    pincode: str
    pin: str
    confirmPin: str
    otp: str

    @field_validator("pin", "confirmPin")
    @classmethod
    def pin_format(cls, v):
        if not (v.isdigit() and len(v) == 4):
            raise ValueError("PIN must be 4 digits")
        return v


class RegisterSellerRequest(RegisterBuyerRequest):
    businessName: str


class LoginRequest(BaseModel):
    mobileNumber: str
    pin: str


class UpdateProfileRequest(BaseModel):
    firstName: Optional[str] = None
    lastName: Optional[str] = None
    address: Optional[str] = None
    businessName: Optional[str] = None


class ItemRequest(BaseModel):
    itemName: str
    unitType: str
    availableQuantity: float
    pricePerUnit: float
    minimumOrderQuantity: float
    unitIncrement: float

    @field_validator("unitType")
    @classmethod
    def valid_unit(cls, v):
        if v not in UNIT_TYPES:
            raise ValueError(f"unitType must be one of {UNIT_TYPES}")
        return v


# ---------- routes ----------

@api_router.get("/")
async def root():
    return {"service": "LocalOrders API", "phase": 1}


@api_router.get("/meta/unit-types")
async def unit_types():
    return {"unitTypes": UNIT_TYPES}


@api_router.post("/auth/otp/send")
async def send_otp(req: OtpSendRequest):
    mobile = normalize_mobile(req.mobileNumber)
    if len(mobile) < 10:
        raise HTTPException(status_code=400, detail="Invalid mobile number")
    existing = await db.users.find_one({"mobileNumber": mobile}, {"_id": 0, "userId": 1})
    if existing:
        raise HTTPException(status_code=409, detail="Mobile number already registered")
    # In real Firebase: triggers SMS. Here mock returns success.
    logger.info(f"[MOCK OTP] Sent to {mobile}: {MOCK_OTP}")
    return {"sent": True, "mockOtp": MOCK_OTP, "message": "OTP sent (mock: use 123456)"}


async def _register(payload: dict, user_type: str) -> dict:
    if payload["pin"] != payload["confirmPin"]:
        raise HTTPException(status_code=400, detail="PIN and confirm PIN do not match")
    if payload["otp"] != MOCK_OTP:
        raise HTTPException(status_code=400, detail="Invalid OTP")
    mobile = normalize_mobile(payload["mobileNumber"])
    if len(mobile) < 10:
        raise HTTPException(status_code=400, detail="Invalid mobile number")
    if await db.users.find_one({"mobileNumber": mobile}):
        raise HTTPException(status_code=409, detail="Mobile number already registered")

    user_id = str(uuid.uuid4())
    doc = {
        "userId": user_id,
        "userType": user_type,
        "firstName": payload["firstName"].strip(),
        "lastName": payload["lastName"].strip(),
        "mobileNumber": mobile,
        "address": payload["address"].strip(),
        "pincode": payload["pincode"].strip(),
        "businessName": None,
        "sellerCode": None,
        "isMobileVerified": True,
        "pinHash": hash_pin(payload["pin"]),
        "failedAttempts": 0,
        "lockedUntil": None,
        "createdDate": utc_now_iso(),
    }
    if user_type == "seller":
        doc["businessName"] = payload["businessName"].strip()
        doc["sellerCode"] = await next_seller_code()
        doc["availabilityStatus"] = "Open"

    await db.users.insert_one(doc)
    token = make_token(user_id)
    return {"token": token, "user": user_public(doc)}


@api_router.post("/auth/register/buyer")
async def register_buyer(req: RegisterBuyerRequest):
    return await _register(req.model_dump(), "buyer")


@api_router.post("/auth/register/seller")
async def register_seller(req: RegisterSellerRequest):
    return await _register(req.model_dump(), "seller")


@api_router.post("/auth/login")
async def login(req: LoginRequest):
    mobile = normalize_mobile(req.mobileNumber)
    user = await db.users.find_one({"mobileNumber": mobile})
    if not user:
        raise HTTPException(status_code=404, detail="Account not found")

    if not user.get("isMobileVerified"):
        raise HTTPException(status_code=403, detail="Mobile number not verified")

    locked_until = user.get("lockedUntil")
    if locked_until:
        lu = datetime.fromisoformat(locked_until)
        if lu > datetime.now(timezone.utc):
            mins = max(1, int((lu - datetime.now(timezone.utc)).total_seconds() // 60) + 1)
            raise HTTPException(status_code=423, detail=f"Account locked. Try again in {mins} minutes.")

    if not verify_pin(req.pin, user["pinHash"]):
        new_count = user.get("failedAttempts", 0) + 1
        update = {"failedAttempts": new_count}
        if new_count >= MAX_FAILED_ATTEMPTS:
            update["lockedUntil"] = (datetime.now(timezone.utc) + timedelta(minutes=LOCK_DURATION_MINUTES)).isoformat()
            update["failedAttempts"] = 0
            await db.users.update_one({"userId": user["userId"]}, {"$set": update})
            raise HTTPException(status_code=423, detail=f"Too many failed attempts. Account locked for {LOCK_DURATION_MINUTES} minutes.")
        await db.users.update_one({"userId": user["userId"]}, {"$set": update})
        remaining = MAX_FAILED_ATTEMPTS - new_count
        raise HTTPException(status_code=401, detail=f"Incorrect PIN. {remaining} attempts remaining.")

    await db.users.update_one(
        {"userId": user["userId"]},
        {"$set": {"failedAttempts": 0, "lockedUntil": None}},
    )
    token = make_token(user["userId"])
    return {"token": token, "user": user_public(user)}


@api_router.get("/auth/me")
async def me(user: dict = Depends(current_user)):
    return {"user": user_public(user)}


@api_router.post("/auth/logout")
async def logout(user: dict = Depends(current_user)):
    # Stateless JWT — client just drops the token.
    return {"ok": True}


@api_router.put("/users/me")
async def update_profile(req: UpdateProfileRequest, user: dict = Depends(current_user)):
    update = {}
    if req.firstName is not None:
        update["firstName"] = req.firstName.strip()
    if req.lastName is not None:
        update["lastName"] = req.lastName.strip()
    if req.address is not None:
        update["address"] = req.address.strip()
    if req.businessName is not None:
        if user["userType"] != "seller":
            raise HTTPException(status_code=400, detail="Only sellers can set business name")
        update["businessName"] = req.businessName.strip()
    if not update:
        raise HTTPException(status_code=400, detail="Nothing to update")
    await db.users.update_one({"userId": user["userId"]}, {"$set": update})
    fresh = await db.users.find_one({"userId": user["userId"]})
    return {"user": user_public(fresh)}


# ---------- inventory ----------

def ensure_seller(user: dict):
    if user["userType"] != "seller":
        raise HTTPException(status_code=403, detail="Sellers only")


@api_router.get("/seller/items")
async def list_items(include_inactive: bool = False, user: dict = Depends(current_user)):
    ensure_seller(user)
    q = {"sellerId": user["userId"]}
    if not include_inactive:
        q["isActive"] = True
    items = await db.seller_items.find(q, {"_id": 0}).sort("createdDate", -1).to_list(1000)
    return {"items": [item_public(i) for i in items]}


@api_router.post("/seller/items")
async def create_item(req: ItemRequest, user: dict = Depends(current_user)):
    ensure_seller(user)
    now = utc_now_iso()
    doc = {
        "itemId": str(uuid.uuid4()),
        "sellerId": user["userId"],
        "itemName": req.itemName.strip(),
        "unitType": req.unitType,
        "availableQuantity": req.availableQuantity,
        "reservedQuantity": 0,
        "pricePerUnit": req.pricePerUnit,
        "minimumOrderQuantity": req.minimumOrderQuantity,
        "unitIncrement": req.unitIncrement,
        "isActive": True,
        "createdDate": now,
        "updatedDate": now,
    }
    await db.seller_items.insert_one(doc)
    return {"item": item_public(doc)}


@api_router.put("/seller/items/{item_id}")
async def update_item(item_id: str, req: ItemRequest, user: dict = Depends(current_user)):
    ensure_seller(user)
    existing = await db.seller_items.find_one({"itemId": item_id, "sellerId": user["userId"]})
    if not existing:
        raise HTTPException(status_code=404, detail="Item not found")
    update = {
        "itemName": req.itemName.strip(),
        "unitType": req.unitType,
        "availableQuantity": req.availableQuantity,
        "pricePerUnit": req.pricePerUnit,
        "minimumOrderQuantity": req.minimumOrderQuantity,
        "unitIncrement": req.unitIncrement,
        "updatedDate": utc_now_iso(),
    }
    await db.seller_items.update_one({"itemId": item_id}, {"$set": update})
    fresh = await db.seller_items.find_one({"itemId": item_id}, {"_id": 0})
    return {"item": item_public(fresh)}


@api_router.delete("/seller/items/{item_id}")
async def soft_delete_item(item_id: str, user: dict = Depends(current_user)):
    ensure_seller(user)
    existing = await db.seller_items.find_one({"itemId": item_id, "sellerId": user["userId"]})
    if not existing:
        raise HTTPException(status_code=404, detail="Item not found")
    await db.seller_items.update_one(
        {"itemId": item_id},
        {"$set": {"isActive": False, "updatedDate": utc_now_iso()}},
    )
    return {"ok": True}


# ---------- seller availability & dashboard (Phase 4) ----------

class AvailabilityRequest(BaseModel):
    status: Literal["Open", "Closed"]


@api_router.put("/seller/availability")
async def set_availability(req: AvailabilityRequest, user: dict = Depends(current_user)):
    ensure_seller(user)
    await db.users.update_one(
        {"userId": user["userId"]},
        {"$set": {"availabilityStatus": req.status}},
    )
    fresh = await db.users.find_one({"userId": user["userId"]}, {"_id": 0})
    return {"user": user_public(fresh)}


@api_router.get("/seller/dashboard")
async def seller_dashboard(user: dict = Depends(current_user)):
    ensure_seller(user)
    active_items = await db.seller_items.count_documents({"sellerId": user["userId"], "isActive": True})
    low_inventory = await db.seller_items.count_documents({
        "sellerId": user["userId"],
        "isActive": True,
        "availableQuantity": {"$lt": LOW_INVENTORY_THRESHOLD},
    })
    pending_requests = await db.buyer_seller_connections.count_documents({
        "sellerId": user["userId"],
        "status": "Pending",
    })
    open_orders = await db.orders.count_documents({
        "sellerId": user["userId"],
        "orderStatus": {"$in": ["Requested", "Accepted"]},
    })
    return {
        "activeItems": active_items,
        "lowInventoryCount": low_inventory,
        "pendingRequests": pending_requests,
        "openOrders": open_orders,
        "lowInventoryThreshold": LOW_INVENTORY_THRESHOLD,
        "availabilityStatus": user.get("availabilityStatus", "Open"),
    }


# ===================== Notifications & Push =====================

class RegisterPushBody(BaseModel):
    platform: str  # "android" | "ios"
    device_token: str


@api_router.post("/register-push", status_code=201)
async def register_push(body: RegisterPushBody, user: dict = Depends(current_user)):
    """Register a device push token with the upstream relay (SuprSend).
    Authenticated — the token is always registered under the calling user.
    """
    payload = {
        "user_id": user["userId"],
        "platform": body.platform,
        "device_token": body.device_token,
    }
    try:
        resp = await _push_client.post("/api/v1/push/users/register", json=payload)
        if resp.status_code == 401:
            raise HTTPException(500, "EMERGENT_PUSH_KEY missing or invalid")
        if resp.status_code >= 500:
            raise HTTPException(502, "Push provider unavailable")
        resp.raise_for_status()
    except HTTPException:
        raise
    except Exception as e:
        # Never block app login on push registration failure
        logger.warning(f"register-push failed (non-blocking): {e}")
        return {"status": "deferred"}
    return {"status": "registered"}


def notification_public(doc: dict) -> dict:
    return {
        "notificationId": doc["notificationId"],
        "userId": doc["userId"],
        "type": doc["type"],
        "title": doc["title"],
        "body": doc["body"],
        "data": doc.get("data") or {},
        "readAt": doc.get("readAt"),
        "createdDate": doc["createdDate"],
    }


@api_router.get("/notifications")
async def list_notifications(
    limit: int = Query(default=50, ge=1, le=200),
    user: dict = Depends(current_user),
):
    docs = await db.notifications.find(
        {"userId": user["userId"]}, {"_id": 0}
    ).sort("createdDate", -1).to_list(limit)
    unread = await db.notifications.count_documents({"userId": user["userId"], "readAt": None})
    return {
        "notifications": [notification_public(d) for d in docs],
        "unreadCount": unread,
    }


@api_router.get("/notifications/unread-count")
async def unread_count(user: dict = Depends(current_user)):
    unread = await db.notifications.count_documents({"userId": user["userId"], "readAt": None})
    return {"unreadCount": unread}


@api_router.post("/notifications/{notification_id}/read")
async def mark_notification_read(notification_id: str, user: dict = Depends(current_user)):
    res = await db.notifications.find_one_and_update(
        {"notificationId": notification_id, "userId": user["userId"]},
        {"$set": {"readAt": utc_now_iso()}},
        return_document=ReturnDocument.AFTER,
    )
    if not res:
        raise HTTPException(status_code=404, detail="Notification not found")
    res.pop("_id", None)
    return {"notification": notification_public(res)}


@api_router.post("/notifications/read-all")
async def mark_all_read(user: dict = Depends(current_user)):
    now = utc_now_iso()
    result = await db.notifications.update_many(
        {"userId": user["userId"], "readAt": None},
        {"$set": {"readAt": now}},
    )
    return {"markedCount": result.modified_count}


# ===================== Phase 2: Connections & Orders =====================

ORDER_EXPIRY_HOURS = 24
CONNECTION_EXPIRY_DAYS = 7
ORDER_STATUSES = ["Requested", "Accepted", "Rejected", "Cancelled", "Delivered", "Expired"]


def ensure_buyer(user: dict):
    if user["userType"] != "buyer":
        raise HTTPException(status_code=403, detail="Buyers only")


def connection_public(doc: dict, buyer_summary: Optional[dict] = None, seller_summary: Optional[dict] = None) -> dict:
    out = {
        "connectionId": doc["connectionId"],
        "buyerId": doc["buyerId"],
        "sellerId": doc["sellerId"],
        "status": doc["status"],
        "requestedDateTime": doc["requestedDateTime"],
        "approvedDateTime": doc.get("approvedDateTime"),
    }
    if buyer_summary:
        out["buyer"] = buyer_summary
    if seller_summary:
        out["seller"] = seller_summary
    return out


def buyer_summary(user: dict) -> dict:
    return {
        "userId": user["userId"],
        "firstName": user["firstName"],
        "lastName": user["lastName"],
        "mobileNumber": user["mobileNumber"],
        "pincode": user.get("pincode", ""),
    }


def seller_summary(user: dict) -> dict:
    return {
        "userId": user["userId"],
        "businessName": user.get("businessName"),
        "sellerCode": user.get("sellerCode"),
        "firstName": user["firstName"],
        "lastName": user["lastName"],
        "mobileNumber": user["mobileNumber"],
        "address": user.get("address", ""),
        "pincode": user.get("pincode", ""),
        "availabilityStatus": user.get("availabilityStatus", "Open"),
    }


async def expire_stale_connections():
    cutoff = (datetime.now(timezone.utc) - timedelta(days=CONNECTION_EXPIRY_DAYS)).isoformat()
    await db.buyer_seller_connections.update_many(
        {"status": "Pending", "requestedDateTime": {"$lt": cutoff}},
        {"$set": {"status": "Expired"}},
    )


async def next_order_number() -> str:
    counter = await db.counters.find_one_and_update(
        {"_id": "order_number"},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=True,
    )
    seq = counter.get("seq", 1) if counter else 1
    if seq < 100001:
        counter = await db.counters.find_one_and_update(
            {"_id": "order_number"},
            {"$set": {"seq": 100001}},
            return_document=True,
        )
        seq = counter["seq"]
    return f"ORD-{seq}"


def order_public(doc: dict) -> dict:
    return {
        "orderId": doc["orderId"],
        "orderNumber": doc["orderNumber"],
        "buyerId": doc["buyerId"],
        "sellerId": doc["sellerId"],
        "orderStatus": doc["orderStatus"],
        "totalAmount": doc["totalAmount"],
        "requestedDateTime": doc["requestedDateTime"],
        "acceptedDateTime": doc.get("acceptedDateTime"),
        "rejectedDateTime": doc.get("rejectedDateTime"),
        "cancelledDateTime": doc.get("cancelledDateTime"),
        "deliveredDateTime": doc.get("deliveredDateTime"),
        "expiredDateTime": doc.get("expiredDateTime"),
        "rejectionReason": doc.get("rejectionReason"),
        "cancellationReason": doc.get("cancellationReason"),
    }


def order_item_public(doc: dict) -> dict:
    return {
        "orderItemId": doc["orderItemId"],
        "orderId": doc["orderId"],
        "itemId": doc["itemId"],
        "itemName": doc["itemName"],
        "quantity": doc["quantity"],
        "unitType": doc["unitType"],
        "pricePerUnit": doc["pricePerUnit"],
        "itemTotal": doc["itemTotal"],
        # Backward compatible: legacy order_items docs (pre-feature) have no
        # `customMessage` key — surface as None so the field is always present
        # in the API contract.
        "customMessage": doc.get("customMessage"),
    }


class ConnectionRequest(BaseModel):
    sellerCode: str


CUSTOM_MESSAGE_MAX_LENGTH = 500


class OrderItemInput(BaseModel):
    itemId: str
    quantity: float
    # Optional buyer-to-seller note for this line. Trimmed and capped at 500
    # characters server-side; empty/whitespace-only is normalised to None so
    # legacy orders (without the field) and intentionally-blank submissions
    # are stored identically.
    customMessage: Optional[str] = None

    @field_validator("customMessage")
    @classmethod
    def trim_and_limit_message(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        trimmed = v.strip()
        if not trimmed:
            return None
        if len(trimmed) > CUSTOM_MESSAGE_MAX_LENGTH:
            raise ValueError(
                f"Custom message must be {CUSTOM_MESSAGE_MAX_LENGTH} characters or fewer"
            )
        return trimmed


class CreateOrderRequest(BaseModel):
    sellerId: str
    items: List[OrderItemInput]


# ---------- buyer: search sellers ----------

@api_router.get("/buyer/sellers/search")
async def search_sellers(q: Optional[str] = None, user: dict = Depends(current_user)):
    """Unified search for sellers by sellerCode (contains), businessName (contains),
    address (contains), or pincode (contains). Case-insensitive."""
    ensure_buyer(user)
    q_raw = (q or "").strip()
    if len(q_raw) < 1:
        return {"sellers": []}
    # Escape regex special chars to prevent injection / invalid patterns
    pattern = re.escape(q_raw)
    regex = {"$regex": pattern, "$options": "i"}
    mongo_q = {
        "userType": "seller",
        "userId": {"$ne": user["userId"]},
        "$or": [
            {"sellerCode": regex},
            {"businessName": regex},
            {"address": regex},
            {"pincode": regex},
        ],
    }
    sellers = await db.users.find(mongo_q, {"_id": 0}).limit(50).to_list(50)
    # Bulk-fetch current buyer's existing connections for status annotation
    seller_ids = [s["userId"] for s in sellers]
    existing_conns = await db.buyer_seller_connections.find(
        {
            "buyerId": user["userId"],
            "sellerId": {"$in": seller_ids},
            "status": {"$in": ["Pending", "Accepted"]},
        },
        {"_id": 0, "sellerId": 1, "status": 1, "connectionId": 1},
    ).to_list(1000)
    conn_by_seller = {c["sellerId"]: c for c in existing_conns}
    out = []
    for s in sellers:
        c = conn_by_seller.get(s["userId"])
        out.append({
            "userId": s["userId"],
            "businessName": s.get("businessName"),
            "sellerCode": s.get("sellerCode"),
            "firstName": s.get("firstName", ""),
            "lastName": s.get("lastName", ""),
            "mobileNumber": s.get("mobileNumber", ""),
            "address": s.get("address", ""),
            "pincode": s.get("pincode", ""),
            "availabilityStatus": s.get("availabilityStatus", "Open"),
            "connectionStatus": c["status"] if c else None,
            "connectionId": c["connectionId"] if c else None,
        })
    return {"sellers": out}


# ---------- buyer: connections ----------

@api_router.post("/buyer/connections")
async def request_connection(req: ConnectionRequest, user: dict = Depends(current_user)):
    ensure_buyer(user)
    code = req.sellerCode.strip().upper()
    seller = await db.users.find_one({"sellerCode": code, "userType": "seller"})
    if not seller:
        raise HTTPException(status_code=404, detail="Seller not found")
    if seller["userId"] == user["userId"]:
        raise HTTPException(status_code=400, detail="Cannot connect to yourself")

    await expire_stale_connections()

    existing = await db.buyer_seller_connections.find_one({
        "buyerId": user["userId"],
        "sellerId": seller["userId"],
        "status": {"$in": ["Pending", "Accepted"]},
    })
    if existing:
        raise HTTPException(status_code=409, detail=f"Connection already exists (status: {existing['status']})")

    doc = {
        "connectionId": str(uuid.uuid4()),
        "buyerId": user["userId"],
        "sellerId": seller["userId"],
        "status": "Pending",
        "requestedDateTime": utc_now_iso(),
        "approvedDateTime": None,
    }
    await db.buyer_seller_connections.insert_one(doc)
    # Notify the seller of the new connection request
    await notify_user(
        seller["userId"],
        "connection_request",
        "New connection request",
        f"{user['firstName']} {user['lastName']} wants to connect with you.",
        {"connectionId": doc["connectionId"], "buyerId": user["userId"]},
    )
    return {"connection": connection_public(doc, seller_summary=seller_summary(seller))}


@api_router.get("/buyer/connections")
async def list_buyer_connections(status: Optional[str] = None, user: dict = Depends(current_user)):
    ensure_buyer(user)
    await expire_stale_connections()
    q = {"buyerId": user["userId"]}
    if status:
        q["status"] = status
    conns = await db.buyer_seller_connections.find(q, {"_id": 0}).sort("requestedDateTime", -1).to_list(1000)
    seller_ids = list({c["sellerId"] for c in conns})
    sellers = {s["userId"]: s for s in await db.users.find({"userId": {"$in": seller_ids}}, {"_id": 0}).to_list(1000)}
    return {
        "connections": [
            connection_public(c, seller_summary=seller_summary(sellers[c["sellerId"]]) if c["sellerId"] in sellers else None)
            for c in conns
        ]
    }


# ---------- seller: connections ----------

@api_router.get("/seller/connections")
async def list_seller_connections(status: Optional[str] = None, user: dict = Depends(current_user)):
    ensure_seller(user)
    await expire_stale_connections()
    q = {"sellerId": user["userId"]}
    if status:
        q["status"] = status
    conns = await db.buyer_seller_connections.find(q, {"_id": 0}).sort("requestedDateTime", -1).to_list(1000)
    buyer_ids = list({c["buyerId"] for c in conns})
    buyers = {b["userId"]: b for b in await db.users.find({"userId": {"$in": buyer_ids}}, {"_id": 0}).to_list(1000)}
    return {
        "connections": [
            connection_public(c, buyer_summary=buyer_summary(buyers[c["buyerId"]]) if c["buyerId"] in buyers else None)
            for c in conns
        ]
    }


async def _set_connection_status(connection_id: str, seller_id: str, new_status: str) -> dict:
    await expire_stale_connections()
    conn = await db.buyer_seller_connections.find_one({"connectionId": connection_id, "sellerId": seller_id})
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    if conn["status"] != "Pending":
        raise HTTPException(status_code=400, detail=f"Connection is {conn['status']}, cannot change")
    update = {"status": new_status}
    if new_status == "Accepted":
        update["approvedDateTime"] = utc_now_iso()
    await db.buyer_seller_connections.update_one({"connectionId": connection_id}, {"$set": update})
    fresh = await db.buyer_seller_connections.find_one({"connectionId": connection_id}, {"_id": 0})
    return fresh


@api_router.post("/seller/connections/{connection_id}/accept")
async def accept_connection(connection_id: str, user: dict = Depends(current_user)):
    ensure_seller(user)
    fresh = await _set_connection_status(connection_id, user["userId"], "Accepted")
    biz = user.get("businessName") or f"{user['firstName']} {user['lastName']}"
    await notify_user(
        fresh["buyerId"],
        "connection_accepted",
        "Connection accepted",
        f"{biz} accepted your connection request.",
        {"connectionId": connection_id, "sellerId": user["userId"]},
    )
    return {"connection": connection_public(fresh)}


@api_router.post("/seller/connections/{connection_id}/reject")
async def reject_connection(connection_id: str, user: dict = Depends(current_user)):
    ensure_seller(user)
    fresh = await _set_connection_status(connection_id, user["userId"], "Rejected")
    biz = user.get("businessName") or f"{user['firstName']} {user['lastName']}"
    await notify_user(
        fresh["buyerId"],
        "connection_rejected",
        "Connection rejected",
        f"{biz} rejected your connection request.",
        {"connectionId": connection_id, "sellerId": user["userId"]},
    )
    return {"connection": connection_public(fresh)}


async def _ensure_accepted_connection(buyer_id: str, seller_id: str) -> dict:
    await expire_stale_connections()
    conn = await db.buyer_seller_connections.find_one({
        "buyerId": buyer_id,
        "sellerId": seller_id,
        "status": "Accepted",
    })
    if not conn:
        raise HTTPException(status_code=403, detail="No accepted connection with this seller")
    return conn


# ---------- buyer: browse seller inventory ----------

@api_router.get("/buyer/sellers/{seller_id}/items")
async def buyer_browse_items(seller_id: str, q: Optional[str] = None, user: dict = Depends(current_user)):
    ensure_buyer(user)
    await _ensure_accepted_connection(user["userId"], seller_id)
    seller = await db.users.find_one({"userId": seller_id, "userType": "seller"}, {"_id": 0})
    if not seller:
        raise HTTPException(status_code=404, detail="Seller not found")
    query = {"sellerId": seller_id, "isActive": True}
    if q:
        query["itemName"] = {"$regex": re.escape(q), "$options": "i"}
    items = await db.seller_items.find(query, {"_id": 0}).sort("itemName", 1).to_list(1000)
    return {"seller": seller_summary(seller), "items": [item_public(i) for i in items]}


# ---------- buyer: orders ----------

def _validate_qty(qty: float, item: dict):
    min_q = item["minimumOrderQuantity"]
    inc = item["unitIncrement"]
    if qty <= 0:
        raise HTTPException(status_code=400, detail=f"{item['itemName']}: quantity must be positive")
    if qty < min_q:
        raise HTTPException(status_code=400, detail=f"{item['itemName']}: minimum order quantity is {min_q}")
    if qty > item["availableQuantity"]:
        raise HTTPException(status_code=400, detail=f"{item['itemName']}: only {item['availableQuantity']} available")
    # qty must align with increment from min: (qty - min) must be a non-negative multiple of inc (with float tolerance)
    diff = qty - min_q
    if inc > 0:
        steps = diff / inc
        if abs(steps - round(steps)) > 1e-6:
            raise HTTPException(status_code=400, detail=f"{item['itemName']}: quantity must be {min_q} + multiples of {inc}")


@api_router.post("/buyer/orders")
async def create_order(req: CreateOrderRequest, user: dict = Depends(current_user)):
    ensure_buyer(user)
    if not req.items:
        raise HTTPException(status_code=400, detail="Cart is empty")
    await _ensure_accepted_connection(user["userId"], req.sellerId)

    seller = await db.users.find_one({"userId": req.sellerId, "userType": "seller"}, {"_id": 0})
    if not seller:
        raise HTTPException(status_code=404, detail="Seller not found")
    if seller.get("availabilityStatus", "Open") != "Open":
        raise HTTPException(status_code=400, detail="Seller currently unavailable.")

    item_ids = [i.itemId for i in req.items]
    db_items = {i["itemId"]: i for i in await db.seller_items.find(
        {"itemId": {"$in": item_ids}, "sellerId": req.sellerId, "isActive": True}, {"_id": 0}
    ).to_list(1000)}

    total = 0.0
    order_items_docs = []
    order_id = str(uuid.uuid4())
    for line in req.items:
        item = db_items.get(line.itemId)
        if not item:
            raise HTTPException(status_code=404, detail=f"Item {line.itemId} not available")
        _validate_qty(line.quantity, item)
        item_total = round(line.quantity * item["pricePerUnit"], 2)
        total += item_total
        order_items_docs.append({
            "orderItemId": str(uuid.uuid4()),
            "orderId": order_id,
            "itemId": item["itemId"],
            "itemName": item["itemName"],
            "quantity": line.quantity,
            "unitType": item["unitType"],
            "pricePerUnit": item["pricePerUnit"],
            "itemTotal": item_total,
            # Pydantic validator has already trimmed + length-checked this
            # field. Stored as None when blank for consistent backward
            # compatibility with pre-feature documents.
            "customMessage": line.customMessage,
        })

    order_doc = {
        "orderId": order_id,
        "orderNumber": await next_order_number(),
        "buyerId": user["userId"],
        "sellerId": req.sellerId,
        "orderStatus": "Requested",
        "totalAmount": round(total, 2),
        "requestedDateTime": utc_now_iso(),
    }
    await db.orders.insert_one(order_doc)
    if order_items_docs:
        await db.order_items.insert_many(order_items_docs)
    # Notify the seller of the new order
    await notify_user(
        req.sellerId,
        "order_requested",
        f"New order {order_doc['orderNumber']}",
        f"{user['firstName']} {user['lastName']} placed an order for ₹{order_doc['totalAmount']:.2f}.",
        {"orderId": order_id, "buyerId": user["userId"]},
    )
    return {
        "order": order_public(order_doc),
        "items": [order_item_public(i) for i in order_items_docs],
    }


@api_router.get("/buyer/orders")
async def list_buyer_orders(user: dict = Depends(current_user)):
    ensure_buyer(user)
    await expire_stale_orders()
    orders = await db.orders.find({"buyerId": user["userId"]}, {"_id": 0}).sort("requestedDateTime", -1).to_list(1000)
    seller_ids = list({o["sellerId"] for o in orders})
    sellers = {s["userId"]: s for s in await db.users.find({"userId": {"$in": seller_ids}}, {"_id": 0}).to_list(1000)}
    return {
        "orders": [
            {**order_public(o), "seller": seller_summary(sellers[o["sellerId"]]) if o["sellerId"] in sellers else None}
            for o in orders
        ]
    }


@api_router.get("/seller/orders")
async def list_seller_orders(user: dict = Depends(current_user)):
    ensure_seller(user)
    await expire_stale_orders()
    orders = await db.orders.find({"sellerId": user["userId"]}, {"_id": 0}).sort("requestedDateTime", -1).to_list(1000)
    buyer_ids = list({o["buyerId"] for o in orders})
    buyers = {b["userId"]: b for b in await db.users.find({"userId": {"$in": buyer_ids}}, {"_id": 0}).to_list(1000)}
    return {
        "orders": [
            {**order_public(o), "buyer": buyer_summary(buyers[o["buyerId"]]) if o["buyerId"] in buyers else None}
            for o in orders
        ]
    }


@api_router.get("/orders/{order_id}")
async def get_order_detail(order_id: str, user: dict = Depends(current_user)):
    await expire_stale_orders(order_id=order_id)
    order = await db.orders.find_one({"orderId": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if user["userId"] not in (order["buyerId"], order["sellerId"]):
        raise HTTPException(status_code=403, detail="Not your order")
    items = await db.order_items.find({"orderId": order_id}, {"_id": 0}).to_list(1000)
    counterparty = None
    if user["userType"] == "buyer":
        seller = await db.users.find_one({"userId": order["sellerId"]}, {"_id": 0})
        if seller:
            counterparty = seller_summary(seller)
    else:
        buyer = await db.users.find_one({"userId": order["buyerId"]}, {"_id": 0})
        if buyer:
            counterparty = buyer_summary(buyer)
    return {
        "order": order_public(order),
        "items": [order_item_public(i) for i in items],
        "counterparty": counterparty,
    }


# ===================== Phase 3: Order Management =====================

ORDER_EXPIRY_HOURS = 24


class RejectOrderRequest(BaseModel):
    reason: str

    @field_validator("reason")
    @classmethod
    def reason_non_empty(cls, v):
        if not v or not v.strip():
            raise ValueError("Rejection reason is required")
        return v.strip()


class CancelOrderRequest(BaseModel):
    reason: Optional[str] = None


async def expire_stale_orders(order_id: Optional[str] = None):
    """Lazy-expire Requested orders older than 24h. Optionally target a single order."""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=ORDER_EXPIRY_HOURS)).isoformat()
    now = utc_now_iso()
    q = {"orderStatus": "Requested", "requestedDateTime": {"$lt": cutoff}}
    if order_id:
        q["orderId"] = order_id
    await db.orders.update_many(q, {"$set": {"orderStatus": "Expired", "expiredDateTime": now}})


async def _transition_order(order_id: str, user: dict, expected_statuses: List[str], new_status: str, extra: dict) -> dict:
    """Atomically claim an order's status transition.

    Uses MongoDB's atomic `find_one_and_update` filtered on the expected status, so concurrent
    callers (e.g. double-accept) cannot both succeed. Also enforces role+ownership via the filter.
    """
    await expire_stale_orders(order_id=order_id)

    filter_doc = {"orderId": order_id, "orderStatus": {"$in": expected_statuses}}
    if user["userType"] == "seller":
        filter_doc["sellerId"] = user["userId"]
    else:
        filter_doc["buyerId"] = user["userId"]

    fresh = await db.orders.find_one_and_update(
        filter_doc,
        {"$set": {"orderStatus": new_status, **extra}},
        return_document=ReturnDocument.AFTER,
    )
    if fresh:
        # Strip Mongo _id before returning
        fresh.pop("_id", None)
        return fresh

    # Diagnose failure
    actual = await db.orders.find_one({"orderId": order_id})
    if not actual:
        raise HTTPException(status_code=404, detail="Order not found")
    if user["userType"] == "seller" and actual["sellerId"] != user["userId"]:
        raise HTTPException(status_code=403, detail="Not your order")
    if user["userType"] == "buyer" and actual["buyerId"] != user["userId"]:
        raise HTTPException(status_code=403, detail="Not your order")
    raise HTTPException(
        status_code=400,
        detail=f"Cannot change status from '{actual['orderStatus']}' to '{new_status}'",
    )


async def _reserve_inventory(order_id: str, seller_id: str) -> Optional[str]:
    """Atomically reserve inventory for every line of an order.

    For each item, performs a conditional `$inc` requiring `availableQuantity >= qty`.
    If any line fails, prior lines are rolled back. Returns an error message or None.
    """
    items = await db.order_items.find({"orderId": order_id}, {"_id": 0}).to_list(1000)
    reserved: List[dict] = []
    now = utc_now_iso()
    for line in items:
        result = await db.seller_items.find_one_and_update(
            {
                "itemId": line["itemId"],
                "sellerId": seller_id,
                "isActive": True,
                "availableQuantity": {"$gte": line["quantity"]},
            },
            {
                "$inc": {
                    "availableQuantity": -line["quantity"],
                    "reservedQuantity": line["quantity"],
                },
                "$set": {"updatedDate": now},
            },
            return_document=ReturnDocument.AFTER,
        )
        if not result:
            # Roll back previously reserved lines
            for prev in reserved:
                await db.seller_items.update_one(
                    {"itemId": prev["itemId"]},
                    {
                        "$inc": {
                            "availableQuantity": prev["quantity"],
                            "reservedQuantity": -prev["quantity"],
                        },
                        "$set": {"updatedDate": utc_now_iso()},
                    },
                )
            return f"Insufficient stock for '{line['itemName']}'"
        reserved.append(line)
    return None


async def _restore_inventory(order_id: str):
    """Restore availableQuantity and decrease reservedQuantity for all lines (used on cancel-after-accept)."""
    items = await db.order_items.find({"orderId": order_id}, {"_id": 0}).to_list(1000)
    now = utc_now_iso()
    for line in items:
        await db.seller_items.update_one(
            {"itemId": line["itemId"]},
            {
                "$inc": {
                    "availableQuantity": line["quantity"],
                    "reservedQuantity": -line["quantity"],
                },
                "$set": {"updatedDate": now},
            },
        )


async def _clear_reservation(order_id: str):
    """Clear reservedQuantity without touching availableQuantity (used on deliver)."""
    items = await db.order_items.find({"orderId": order_id}, {"_id": 0}).to_list(1000)
    now = utc_now_iso()
    for line in items:
        await db.seller_items.update_one(
            {"itemId": line["itemId"]},
            {"$inc": {"reservedQuantity": -line["quantity"]}, "$set": {"updatedDate": now}},
        )


@api_router.post("/seller/orders/{order_id}/accept")
async def accept_order(order_id: str, user: dict = Depends(current_user)):
    ensure_seller(user)

    # 1) Atomically claim the status transition. This rejects double-accept and non-Requested orders.
    fresh = await _transition_order(
        order_id, user,
        expected_statuses=["Requested"],
        new_status="Accepted",
        extra={"acceptedDateTime": utc_now_iso()},
    )

    # 2) Reserve inventory atomically. If any line fails (insufficient stock or item removed),
    #    revert the order status back to Requested so the seller can act again.
    err = await _reserve_inventory(order_id, user["userId"])
    if err:
        await db.orders.update_one(
            {"orderId": order_id, "orderStatus": "Accepted"},
            {"$set": {"orderStatus": "Requested"}, "$unset": {"acceptedDateTime": ""}},
        )
        raise HTTPException(status_code=400, detail=err)

    # Notify the buyer
    await notify_user(
        fresh["buyerId"],
        "order_accepted",
        f"Order {fresh['orderNumber']} accepted",
        "Your order has been accepted and will be delivered soon.",
        {"orderId": order_id},
    )
    return {"order": order_public(fresh)}


@api_router.post("/seller/orders/{order_id}/reject")
async def reject_order(order_id: str, req: RejectOrderRequest, user: dict = Depends(current_user)):
    ensure_seller(user)
    fresh = await _transition_order(
        order_id, user,
        expected_statuses=["Requested"],
        new_status="Rejected",
        extra={"rejectedDateTime": utc_now_iso(), "rejectionReason": req.reason},
    )
    # Reject is only from Requested → nothing was reserved, no inventory change.
    await notify_user(
        fresh["buyerId"],
        "order_rejected",
        f"Order {fresh['orderNumber']} rejected",
        f"Reason: {req.reason}",
        {"orderId": order_id},
    )
    return {"order": order_public(fresh)}


@api_router.post("/seller/orders/{order_id}/deliver")
async def deliver_order(order_id: str, user: dict = Depends(current_user)):
    ensure_seller(user)
    fresh = await _transition_order(
        order_id, user,
        expected_statuses=["Accepted"],
        new_status="Delivered",
        extra={"deliveredDateTime": utc_now_iso()},
    )
    # Delivered: keep availableQuantity deducted, clear reservedQuantity.
    await _clear_reservation(order_id)
    await notify_user(
        fresh["buyerId"],
        "order_delivered",
        f"Order {fresh['orderNumber']} delivered",
        "Your order has been marked as delivered. Thank you!",
        {"orderId": order_id},
    )
    return {"order": order_public(fresh)}


@api_router.post("/buyer/orders/{order_id}/cancel")
async def cancel_order(order_id: str, req: CancelOrderRequest, user: dict = Depends(current_user)):
    ensure_buyer(user)
    # Capture previous status so we know whether to restore inventory.
    pre = await db.orders.find_one({"orderId": order_id, "buyerId": user["userId"]}, {"_id": 0, "orderStatus": 1})
    fresh = await _transition_order(
        order_id, user,
        expected_statuses=["Requested", "Accepted"],
        new_status="Cancelled",
        extra={
            "cancelledDateTime": utc_now_iso(),
            "cancellationReason": (req.reason or "").strip() or None,
        },
    )
    if pre and pre["orderStatus"] == "Accepted":
        await _restore_inventory(order_id)
    # Notify the seller
    reason_txt = (req.reason or "").strip()
    body = "Order cancelled by buyer." + (f" Reason: {reason_txt}" if reason_txt else "")
    await notify_user(
        fresh["sellerId"],
        "order_cancelled",
        f"Order {fresh['orderNumber']} cancelled",
        body,
        {"orderId": order_id},
    )
    return {"order": order_public(fresh)}


# ===================== Custom Requests ("Need Something Not Listed?") =====================
#
# Lightweight 1-buyer ↔ 1-seller request channel for items not in the seller's
# catalog. Reuses the atomic find_one_and_update state-transition pattern from
# orders, the notify_user notification helper, and the existing buyer↔seller
# connection gating. No cart, no inventory, no order side-effects.

CUSTOM_REQUEST_MIN_LEN = 5
CUSTOM_REQUEST_MAX_LEN = 500
CUSTOM_REQUEST_STATUSES = [
    "SAVED",
    "NEW_REQUEST",
    "QUOTE_SENT",
    "ACCEPTED",
    "REJECTED_BY_BUYER",
    "REJECTED_BY_SELLER",
]
SELLER_MESSAGE_MAX_LEN = 500
REJECTION_REASON_MAX_LEN = 500


class CreateCustomRequestBody(BaseModel):
    sellerId: str
    requestDetails: str
    send: bool = False  # True = NEW_REQUEST (send immediately), False = SAVED (draft)

    @field_validator("requestDetails")
    @classmethod
    def validate_details(cls, v: str) -> str:
        trimmed = (v or "").strip()
        if len(trimmed) < CUSTOM_REQUEST_MIN_LEN or len(trimmed) > CUSTOM_REQUEST_MAX_LEN:
            raise ValueError(
                f"Request details must be {CUSTOM_REQUEST_MIN_LEN}-{CUSTOM_REQUEST_MAX_LEN} characters"
            )
        return trimmed


class UpdateCustomRequestBody(BaseModel):
    requestDetails: str

    @field_validator("requestDetails")
    @classmethod
    def validate_details(cls, v: str) -> str:
        trimmed = (v or "").strip()
        if len(trimmed) < CUSTOM_REQUEST_MIN_LEN or len(trimmed) > CUSTOM_REQUEST_MAX_LEN:
            raise ValueError(
                f"Request details must be {CUSTOM_REQUEST_MIN_LEN}-{CUSTOM_REQUEST_MAX_LEN} characters"
            )
        return trimmed


class SendQuoteBody(BaseModel):
    quoteAmount: float
    sellerMessage: Optional[str] = None

    @field_validator("quoteAmount")
    @classmethod
    def positive_amount(cls, v: float) -> float:
        if v is None or v <= 0:
            raise ValueError("Quote amount must be greater than 0")
        return float(v)

    @field_validator("sellerMessage")
    @classmethod
    def trim_message(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        t = v.strip()
        if not t:
            return None
        if len(t) > SELLER_MESSAGE_MAX_LEN:
            raise ValueError(f"Seller message must be {SELLER_MESSAGE_MAX_LEN} characters or fewer")
        return t


class RejectCustomRequestBody(BaseModel):
    rejectionReason: Optional[str] = None

    @field_validator("rejectionReason")
    @classmethod
    def trim_reason(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        t = v.strip()
        if not t:
            return None
        if len(t) > REJECTION_REASON_MAX_LEN:
            raise ValueError(f"Rejection reason must be {REJECTION_REASON_MAX_LEN} characters or fewer")
        return t


def custom_request_public(doc: dict) -> dict:
    return {
        "requestId": doc["requestId"],
        "buyerId": doc["buyerId"],
        "sellerId": doc["sellerId"],
        "requestDetails": doc["requestDetails"],
        "status": doc["status"],
        "quoteAmount": doc.get("quoteAmount"),
        "sellerMessage": doc.get("sellerMessage"),
        "rejectionReason": doc.get("rejectionReason"),
        "createdAt": doc["createdAt"],
        "updatedAt": doc["updatedAt"],
    }


async def _transition_custom_request(
    request_id: str,
    user: dict,
    expected_statuses: List[str],
    new_status: str,
    extra: Optional[dict] = None,
    party: Literal["buyer", "seller"] = "buyer",
) -> dict:
    """Atomically claim a custom-request status transition. Mirrors _transition_order.

    Filter enforces ownership by either buyerId or sellerId depending on `party`.
    Returns the fresh document or raises HTTPException with a precise reason.
    """
    set_payload: Dict[str, Any] = {"status": new_status, "updatedAt": utc_now_iso()}
    if extra:
        set_payload.update(extra)

    filter_doc: Dict[str, Any] = {
        "requestId": request_id,
        "status": {"$in": expected_statuses},
    }
    if party == "seller":
        filter_doc["sellerId"] = user["userId"]
    else:
        filter_doc["buyerId"] = user["userId"]

    fresh = await db.custom_requests.find_one_and_update(
        filter_doc,
        {"$set": set_payload},
        return_document=ReturnDocument.AFTER,
    )
    if fresh:
        fresh.pop("_id", None)
        return fresh

    actual = await db.custom_requests.find_one({"requestId": request_id})
    if not actual:
        raise HTTPException(status_code=404, detail="Request not found")
    if party == "seller" and actual["sellerId"] != user["userId"]:
        raise HTTPException(status_code=403, detail="Not your request")
    if party == "buyer" and actual["buyerId"] != user["userId"]:
        raise HTTPException(status_code=403, detail="Not your request")
    raise HTTPException(
        status_code=400,
        detail=f"Cannot change status from '{actual['status']}' to '{new_status}'",
    )


# ---------- buyer routes ----------

@api_router.post("/buyer/custom-requests", status_code=201)
async def create_custom_request(req: CreateCustomRequestBody, user: dict = Depends(current_user)):
    ensure_buyer(user)
    # Reuse existing connection gating — keeps requests 1:1 between connected pairs
    await _ensure_accepted_connection(user["userId"], req.sellerId)
    seller = await db.users.find_one({"userId": req.sellerId, "userType": "seller"}, {"_id": 0})
    if not seller:
        raise HTTPException(status_code=404, detail="Seller not found")

    now = utc_now_iso()
    status = "NEW_REQUEST" if req.send else "SAVED"
    doc = {
        "requestId": str(uuid.uuid4()),
        "buyerId": user["userId"],
        "sellerId": req.sellerId,
        "requestDetails": req.requestDetails,
        "status": status,
        "quoteAmount": None,
        "sellerMessage": None,
        "rejectionReason": None,
        "createdAt": now,
        "updatedAt": now,
    }
    await db.custom_requests.insert_one(doc)

    if status == "NEW_REQUEST":
        await notify_user(
            req.sellerId,
            "custom_request_received",
            "New custom request",
            f"{user['firstName']} {user['lastName']} sent you a custom request.",
            {"customRequestId": doc["requestId"], "buyerId": user["userId"]},
        )

    return {"request": custom_request_public(doc)}


@api_router.get("/buyer/custom-requests")
async def list_buyer_custom_requests(user: dict = Depends(current_user)):
    ensure_buyer(user)
    docs = await db.custom_requests.find(
        {"buyerId": user["userId"]}, {"_id": 0}
    ).sort("createdAt", -1).to_list(1000)
    seller_ids = list({d["sellerId"] for d in docs})
    sellers = {
        s["userId"]: s
        for s in await db.users.find({"userId": {"$in": seller_ids}}, {"_id": 0}).to_list(1000)
    }
    return {
        "requests": [
            {
                **custom_request_public(d),
                "seller": seller_summary(sellers[d["sellerId"]]) if d["sellerId"] in sellers else None,
            }
            for d in docs
        ]
    }


@api_router.get("/custom-requests/{request_id}")
async def get_custom_request(request_id: str, user: dict = Depends(current_user)):
    doc = await db.custom_requests.find_one({"requestId": request_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Request not found")
    if user["userId"] not in (doc["buyerId"], doc["sellerId"]):
        raise HTTPException(status_code=403, detail="Not your request")
    counterparty: Optional[dict] = None
    if user["userType"] == "buyer":
        s = await db.users.find_one({"userId": doc["sellerId"]}, {"_id": 0})
        if s:
            counterparty = seller_summary(s)
    else:
        b = await db.users.find_one({"userId": doc["buyerId"]}, {"_id": 0})
        if b:
            counterparty = buyer_summary(b)
    return {"request": custom_request_public(doc), "counterparty": counterparty}


@api_router.put("/buyer/custom-requests/{request_id}")
async def update_custom_request(
    request_id: str,
    body: UpdateCustomRequestBody,
    user: dict = Depends(current_user),
):
    ensure_buyer(user)
    fresh = await _transition_custom_request(
        request_id,
        user,
        expected_statuses=["SAVED"],
        new_status="SAVED",
        extra={"requestDetails": body.requestDetails},
        party="buyer",
    )
    return {"request": custom_request_public(fresh)}


@api_router.delete("/buyer/custom-requests/{request_id}")
async def delete_custom_request(request_id: str, user: dict = Depends(current_user)):
    ensure_buyer(user)
    # Only SAVED drafts may be deleted (sent requests are immutable from the buyer side)
    existing = await db.custom_requests.find_one(
        {"requestId": request_id, "buyerId": user["userId"]}, {"_id": 0}
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Request not found")
    if existing["status"] != "SAVED":
        raise HTTPException(
            status_code=400,
            detail="Only saved drafts can be deleted",
        )
    await db.custom_requests.delete_one({"requestId": request_id, "buyerId": user["userId"]})
    return {"ok": True}


@api_router.post("/buyer/custom-requests/{request_id}/send")
async def send_custom_request(request_id: str, user: dict = Depends(current_user)):
    ensure_buyer(user)
    fresh = await _transition_custom_request(
        request_id,
        user,
        expected_statuses=["SAVED"],
        new_status="NEW_REQUEST",
        party="buyer",
    )
    await notify_user(
        fresh["sellerId"],
        "custom_request_received",
        "New custom request",
        f"{user['firstName']} {user['lastName']} sent you a custom request.",
        {"customRequestId": request_id, "buyerId": user["userId"]},
    )
    return {"request": custom_request_public(fresh)}


@api_router.post("/buyer/custom-requests/{request_id}/accept-quote")
async def accept_quote(request_id: str, user: dict = Depends(current_user)):
    ensure_buyer(user)
    fresh = await _transition_custom_request(
        request_id,
        user,
        expected_statuses=["QUOTE_SENT"],
        new_status="ACCEPTED",
        party="buyer",
    )
    await notify_user(
        fresh["sellerId"],
        "custom_request_accepted_by_buyer",
        "Quote accepted",
        f"{user['firstName']} {user['lastName']} accepted your quote.",
        {"customRequestId": request_id},
    )
    return {"request": custom_request_public(fresh)}


@api_router.post("/buyer/custom-requests/{request_id}/reject-quote")
async def reject_quote(request_id: str, user: dict = Depends(current_user)):
    ensure_buyer(user)
    fresh = await _transition_custom_request(
        request_id,
        user,
        expected_statuses=["QUOTE_SENT"],
        new_status="REJECTED_BY_BUYER",
        party="buyer",
    )
    await notify_user(
        fresh["sellerId"],
        "custom_request_rejected_by_buyer",
        "Quote rejected",
        f"{user['firstName']} {user['lastName']} rejected your quote.",
        {"customRequestId": request_id},
    )
    return {"request": custom_request_public(fresh)}


# ---------- seller routes ----------

@api_router.get("/seller/custom-requests")
async def list_seller_custom_requests(user: dict = Depends(current_user)):
    ensure_seller(user)
    # Sellers never see SAVED drafts (those are private to the buyer)
    docs = await db.custom_requests.find(
        {"sellerId": user["userId"], "status": {"$ne": "SAVED"}},
        {"_id": 0},
    ).sort("createdAt", -1).to_list(1000)
    buyer_ids = list({d["buyerId"] for d in docs})
    buyers = {
        b["userId"]: b
        for b in await db.users.find({"userId": {"$in": buyer_ids}}, {"_id": 0}).to_list(1000)
    }
    return {
        "requests": [
            {
                **custom_request_public(d),
                "buyer": buyer_summary(buyers[d["buyerId"]]) if d["buyerId"] in buyers else None,
            }
            for d in docs
        ]
    }


@api_router.post("/seller/custom-requests/{request_id}/quote")
async def send_quote(
    request_id: str,
    body: SendQuoteBody,
    user: dict = Depends(current_user),
):
    ensure_seller(user)
    fresh = await _transition_custom_request(
        request_id,
        user,
        expected_statuses=["NEW_REQUEST"],
        new_status="QUOTE_SENT",
        extra={"quoteAmount": body.quoteAmount, "sellerMessage": body.sellerMessage},
        party="seller",
    )
    biz = user.get("businessName") or f"{user['firstName']} {user['lastName']}"
    await notify_user(
        fresh["buyerId"],
        "custom_quote_received",
        "Quote received",
        f"{biz} sent a quote of ₹{body.quoteAmount:.2f}.",
        {"customRequestId": request_id},
    )
    return {"request": custom_request_public(fresh)}


@api_router.post("/seller/custom-requests/{request_id}/accept")
async def seller_accept_custom_request(request_id: str, user: dict = Depends(current_user)):
    ensure_seller(user)
    fresh = await _transition_custom_request(
        request_id,
        user,
        expected_statuses=["NEW_REQUEST"],
        new_status="ACCEPTED",
        party="seller",
    )
    biz = user.get("businessName") or f"{user['firstName']} {user['lastName']}"
    await notify_user(
        fresh["buyerId"],
        "custom_request_accepted_by_seller",
        "Request accepted",
        f"{biz} accepted your custom request.",
        {"customRequestId": request_id},
    )
    return {"request": custom_request_public(fresh)}


@api_router.post("/seller/custom-requests/{request_id}/reject")
async def seller_reject_custom_request(
    request_id: str,
    body: RejectCustomRequestBody,
    user: dict = Depends(current_user),
):
    ensure_seller(user)
    fresh = await _transition_custom_request(
        request_id,
        user,
        expected_statuses=["NEW_REQUEST"],
        new_status="REJECTED_BY_SELLER",
        extra={"rejectionReason": body.rejectionReason},
        party="seller",
    )
    biz = user.get("businessName") or f"{user['firstName']} {user['lastName']}"
    body_txt = "Your custom request was rejected."
    if body.rejectionReason:
        body_txt = f"Your custom request was rejected. Reason: {body.rejectionReason}"
    await notify_user(
        fresh["buyerId"],
        "custom_request_rejected_by_seller",
        "Request rejected",
        f"{biz}: {body_txt}",
        {"customRequestId": request_id},
    )
    return {"request": custom_request_public(fresh)}


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
