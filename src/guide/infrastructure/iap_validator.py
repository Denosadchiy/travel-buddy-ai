"""
In-App Purchase validators for Apple App Store and Google Play.

Apple:  verifyReceipt endpoint (production → sandbox fallback on status 21007)
Google: Purchases.products.get via OAuth2 service account

parse_refund_notification() handles App Store Server Notifications and Google RTDN.
"""
import base64
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx
from google.oauth2 import service_account
from google.auth.transport.requests import Request as GoogleAuthRequest

from src.config import settings

logger = logging.getLogger(__name__)

_APPLE_PRODUCTION_URL = "https://buy.itunes.apple.com/verifyReceipt"
_APPLE_SANDBOX_URL = "https://sandbox.itunes.apple.com/verifyReceipt"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GOOGLE_PURCHASES_URL = (
    "https://androidpublisher.googleapis.com/androidpublisher/v3"
    "/applications/{package_name}/purchases/products/{product_id}/tokens/{purchase_token}"
)


@dataclass
class IAPValidationResult:
    is_valid: bool
    transaction_id: str
    original_transaction_id: str | None
    product_id: str
    purchase_date: datetime | None
    is_refunded: bool = False
    error_message: str | None = None


# ---------------------------------------------------------------------------
# Apple
# ---------------------------------------------------------------------------

async def validate_apple(receipt_data: str, product_id: str) -> IAPValidationResult:
    """Validate Apple receipt via verifyReceipt.

    Automatically falls back to sandbox when production returns status 21007.
    """
    async with httpx.AsyncClient(timeout=30) as client:
        result = await _apple_verify(client, receipt_data, _APPLE_PRODUCTION_URL)
        if result.get("status") == 21007:
            # Receipt is from sandbox environment
            logger.info("Apple IAP: production returned 21007, retrying against sandbox")
            result = await _apple_verify(client, receipt_data, _APPLE_SANDBOX_URL)

        status = result.get("status", -1)
        if status != 0:
            return IAPValidationResult(
                is_valid=False,
                transaction_id="",
                original_transaction_id=None,
                product_id=product_id,
                purchase_date=None,
                error_message=f"Apple verifyReceipt status={status}",
            )

        # Find the latest receipt for the requested product_id
        receipts = result.get("latest_receipt_info") or result.get("receipt", {}).get("in_app", [])
        matching = [r for r in receipts if r.get("product_id") == product_id]
        if not matching:
            return IAPValidationResult(
                is_valid=False,
                transaction_id="",
                original_transaction_id=None,
                product_id=product_id,
                purchase_date=None,
                error_message="Product not found in receipt",
            )

        latest = max(matching, key=lambda r: int(r.get("purchase_date_ms", 0)))
        purchase_ms = int(latest.get("purchase_date_ms", 0))
        purchase_dt = datetime.fromtimestamp(purchase_ms / 1000, tz=timezone.utc) if purchase_ms else None
        is_refunded = latest.get("cancellation_date_ms") is not None

        return IAPValidationResult(
            is_valid=not is_refunded,
            transaction_id=latest.get("transaction_id", ""),
            original_transaction_id=latest.get("original_transaction_id"),
            product_id=product_id,
            purchase_date=purchase_dt,
            is_refunded=is_refunded,
        )


async def _apple_verify(client: httpx.AsyncClient, receipt_data: str, url: str) -> dict:
    payload = {
        "receipt-data": receipt_data,
        "password": settings.apple_shared_secret,
        "exclude-old-transactions": True,
    }
    resp = await client.post(url, json=payload)
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Google
# ---------------------------------------------------------------------------

async def validate_google(purchase_token: str, product_id: str) -> IAPValidationResult:
    """Validate Google Play purchase via Publisher API (OAuth2 service account)."""
    access_token = await _google_access_token()
    package_name = settings.google_play_package_name
    url = _GOOGLE_PURCHASES_URL.format(
        package_name=package_name,
        product_id=product_id,
        purchase_token=purchase_token,
    )
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, headers={"Authorization": f"Bearer {access_token}"})
        if resp.status_code == 404:
            return IAPValidationResult(
                is_valid=False,
                transaction_id=purchase_token,
                original_transaction_id=None,
                product_id=product_id,
                purchase_date=None,
                error_message="Purchase not found in Google Play",
            )
        resp.raise_for_status()
        data = resp.json()

    # purchaseState: 0 = purchased, 1 = cancelled, 2 = pending
    purchase_state = data.get("purchaseState", 1)
    consumption_state = data.get("consumptionState", 0)
    order_id = data.get("orderId", purchase_token)
    purchase_time_ms = int(data.get("purchaseTimeMillis", 0))
    purchase_dt = datetime.fromtimestamp(purchase_time_ms / 1000, tz=timezone.utc) if purchase_time_ms else None

    return IAPValidationResult(
        is_valid=purchase_state == 0,
        transaction_id=order_id,
        original_transaction_id=None,
        product_id=product_id,
        purchase_date=purchase_dt,
        is_refunded=purchase_state == 1,
        error_message=None if purchase_state == 0 else f"purchaseState={purchase_state}",
    )


async def _google_access_token() -> str:
    """Obtain OAuth2 access token from base64-encoded service account JSON."""
    sa_json = base64.b64decode(settings.google_service_account_json_b64).decode()
    sa_info = json.loads(sa_json)
    scopes = ["https://www.googleapis.com/auth/androidpublisher"]
    credentials = service_account.Credentials.from_service_account_info(sa_info, scopes=scopes)
    # Refresh synchronously (google-auth doesn't have async support yet)
    credentials.refresh(GoogleAuthRequest())
    return credentials.token


# ---------------------------------------------------------------------------
# Refund webhook parser
# ---------------------------------------------------------------------------

async def parse_refund_notification(platform: str, payload: dict) -> dict:
    """Parse App Store Server Notification or Google RTDN refund event.

    Returns normalized dict: {transaction_id, original_transaction_id, product_id, platform, is_refund}
    """
    if platform == "apple":
        notification_type = payload.get("notificationType", "")
        signed_payload = payload.get("data", {})
        transaction_info = signed_payload.get("signedTransactionInfo", {})
        return {
            "transaction_id": transaction_info.get("transactionId", ""),
            "original_transaction_id": transaction_info.get("originalTransactionId"),
            "product_id": transaction_info.get("productId", ""),
            "platform": "apple",
            "is_refund": notification_type in ("REFUND", "REVOKE"),
        }

    if platform == "google":
        rtdn = payload.get("subscriptionNotification") or payload.get("oneTimeProductNotification", {})
        notification_type = rtdn.get("notificationType", 0)
        return {
            "transaction_id": rtdn.get("purchaseToken", ""),
            "original_transaction_id": None,
            "product_id": rtdn.get("sku", ""),
            "platform": "google",
            # notificationType 2 = CANCELED/REVOKED for one-time; 12 = REVOKED for subscription
            "is_refund": notification_type in (2, 12),
        }

    raise ValueError(f"Unknown platform: {platform!r}")
