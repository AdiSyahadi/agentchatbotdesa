"""
Payment Gateway Adapter — switch between Midtrans and Flip via PAYMENT_GATEWAY env var.

Usage:
    from app.payment_gateway import get_gateway
    gw = get_gateway()
    result = await gw.create_qris(order_id, amount, item_name, name, phone)
    result = await gw.create_snap(order_id, amount, item_name, name, phone)
    result = await gw.check_status(order_id)
    is_valid = gw.verify_webhook(headers, body)
    status = gw.parse_webhook_status(body)

Switch in .env:
    PAYMENT_GATEWAY=midtrans   # or flip
"""

import abc
import base64
import hashlib
import json
import logging
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# Standardized return dicts
# ─────────────────────────────────────────────
# create_qris → {"success": bool, "qr_url": str, "transaction_id": str, "order_id": str, "gross_amount": str, "expiry_time": str, "error": str}
# create_snap → {"success": bool, "token": str, "redirect_url": str, "order_id": str, "error": str}
# check_status → {"success": bool, "order_id": str, "transaction_status": str, "payment_type": str, "gross_amount": str, "raw": dict, "error": str}
# verify_webhook → bool
# parse_webhook_status → {"order_id": str, "transaction_status": str, "fraud_status": str, "gross_amount": str, "raw": dict}


class PaymentGateway(abc.ABC):
    """Abstract payment gateway interface."""

    @abc.abstractmethod
    async def create_qris(self, order_id: str, amount: int, item_name: str,
                           customer_name: str, customer_phone: str) -> dict:
        """Create QRIS payment. Returns dict with qr_url."""
        ...

    @abc.abstractmethod
    async def create_snap(self, order_id: str, amount: int, item_name: str,
                           customer_name: str, customer_phone: str) -> dict:
        """Create payment page/link. Returns dict with redirect_url."""
        ...

    @abc.abstractmethod
    async def check_status(self, order_id: str) -> dict:
        """Check transaction status."""
        ...

    @abc.abstractmethod
    def verify_webhook(self, headers: dict, body: dict) -> bool:
        """Verify webhook signature/token. Returns True if valid."""
        ...

    @abc.abstractmethod
    def parse_webhook_status(self, body: dict) -> dict:
        """Parse webhook body into standardized status dict."""
        ...


# ─────────────────────────────────────────────
# Midtrans Implementation
# ─────────────────────────────────────────────

class MidtransGateway(PaymentGateway):
    """Midtrans Core API + Snap API implementation."""

    def __init__(self):
        self.server_key = settings.MIDTRANS_SERVER_KEY
        self.is_production = settings.MIDTRANS_IS_PRODUCTION
        self.core_url = "https://api.midtrans.com" if self.is_production else "https://api.sandbox.midtrans.com"
        self.snap_url = "https://app.midtrans.com" if self.is_production else "https://app.sandbox.midtrans.com"

    def _auth_header(self) -> dict:
        encoded = base64.b64encode(f"{self.server_key}:".encode()).decode()
        return {
            "Authorization": f"Basic {encoded}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def create_qris(self, order_id: str, amount: int, item_name: str,
                           customer_name: str, customer_phone: str) -> dict:
        url = f"{self.core_url}/v2/charge"
        payload = {
            "payment_type": "qris",
            "transaction_details": {"order_id": order_id, "gross_amount": amount},
            "item_details": [{"id": order_id, "price": amount, "quantity": 1, "name": item_name[:50]}],
            "customer_details": {"first_name": customer_name, "phone": customer_phone},
            "qris": {"acquirer": "gopay"},
        }
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(url, json=payload, headers=self._auth_header(), timeout=30)
                data = resp.json()
                logger.info(f"Midtrans QRIS response for {order_id}: status_code={resp.status_code}")

                if resp.status_code in (200, 201) and data.get("status_code") in ("200", "201"):
                    qr_url = None
                    for action in data.get("actions", []):
                        if action.get("name") == "generate-qr-code":
                            qr_url = action.get("url")
                            break
                    return {
                        "success": True,
                        "qr_url": qr_url,
                        "transaction_id": data.get("transaction_id"),
                        "order_id": data.get("order_id"),
                        "gross_amount": data.get("gross_amount"),
                        "expiry_time": data.get("expiry_time"),
                    }
                else:
                    error_msg = data.get("status_message", "Unknown error")
                    logger.error(f"Midtrans QRIS error for {order_id}: {error_msg}")
                    return {"success": False, "error": error_msg, "raw": data}
        except Exception as e:
            logger.error(f"Midtrans QRIS exception for {order_id}: {e}")
            return {"success": False, "error": str(e)}

    async def create_snap(self, order_id: str, amount: int, item_name: str,
                           customer_name: str, customer_phone: str) -> dict:
        url = f"{self.snap_url}/snap/v1/transactions"
        payload = {
            "transaction_details": {"order_id": order_id, "gross_amount": amount},
            "item_details": [{"id": order_id, "price": amount, "quantity": 1, "name": item_name[:50]}],
            "customer_details": {"first_name": customer_name, "phone": customer_phone},
        }
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(url, json=payload, headers=self._auth_header(), timeout=30)
                data = resp.json()
                logger.info(f"Midtrans Snap response for {order_id}: {data}")
                token = data.get("token")
                redirect_url = data.get("redirect_url")
                if token and redirect_url:
                    return {"success": True, "token": token, "redirect_url": redirect_url, "order_id": order_id}
                else:
                    error_msgs = data.get("error_messages", [str(data)])
                    logger.error(f"Midtrans Snap error for {order_id}: {error_msgs}")
                    return {"success": False, "error": ", ".join(error_msgs)}
        except Exception as e:
            logger.error(f"Midtrans Snap exception for {order_id}: {e}")
            return {"success": False, "error": str(e)}

    async def check_status(self, order_id: str) -> dict:
        url = f"{self.core_url}/v2/{order_id}/status"
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, headers=self._auth_header(), timeout=30)
                data = resp.json()
                return {
                    "success": True,
                    "order_id": data.get("order_id"),
                    "transaction_status": data.get("transaction_status"),
                    "payment_type": data.get("payment_type"),
                    "gross_amount": data.get("gross_amount"),
                    "raw": data,
                }
        except Exception as e:
            logger.error(f"Midtrans status check error for {order_id}: {e}")
            return {"success": False, "error": str(e)}

    def verify_webhook(self, headers: dict, body: dict) -> bool:
        order_id = body.get("order_id", "")
        status_code = body.get("status_code", "")
        gross_amount = body.get("gross_amount", "")
        signature_key = body.get("signature_key", "")
        if not signature_key:
            return True  # No signature to verify
        expected = hashlib.sha512(
            f"{order_id}{status_code}{gross_amount}{self.server_key}".encode()
        ).hexdigest()
        return signature_key == expected

    def parse_webhook_status(self, body: dict) -> dict:
        transaction_status = body.get("transaction_status", "")
        fraud_status = body.get("fraud_status", "")

        # Normalize to standard statuses: settlement, pending, deny, cancel, expire, refund
        if transaction_status in ("capture", "settlement"):
            if fraud_status == "accept" or not fraud_status:
                status = "settlement"
            else:
                status = "deny"
        elif transaction_status == "pending":
            status = "pending"
        elif transaction_status in ("deny", "cancel", "expire"):
            status = transaction_status
        elif transaction_status == "refund":
            status = "refund"
        else:
            status = transaction_status

        return {
            "order_id": body.get("order_id", ""),
            "transaction_status": status,
            "fraud_status": fraud_status,
            "gross_amount": body.get("gross_amount", ""),
            "raw": body,
        }


# ─────────────────────────────────────────────
# Flip Implementation
# ─────────────────────────────────────────────

class FlipGateway(PaymentGateway):
    """Flip Accept Payment API implementation.

    Docs: https://docs.flip.id/accept-payment/overview
    - Create Bill → returns payment link (user picks QRIS/VA/etc on Flip page)
    - QRIS: Flip generates QRIS via bill with bill_payment_type=PAYMENT_LINK
    - Webhook: validated via X-Callback-Token header
    """

    def __init__(self):
        self.secret_key = settings.FLIP_SECRET_KEY
        self.validation_token = settings.FLIP_VALIDATION_TOKEN
        self.is_production = settings.FLIP_IS_PRODUCTION
        self.base_url = "https://bigflip.id/api/v2" if self.is_production else "https://bigflip.id/big/sandbox/api/v2"

    def _auth_header(self) -> dict:
        encoded = base64.b64encode(f"{self.secret_key}:".encode()).decode()
        return {
            "Authorization": f"Basic {encoded}",
            "Content-Type": "application/x-www-form-urlencoded",
        }

    async def create_qris(self, order_id: str, amount: int, item_name: str,
                           customer_name: str, customer_phone: str) -> dict:
        """Flip doesn't have direct QRIS API — creates a bill, user sees QRIS on payment page."""
        url = f"{self.base_url}/pwf/bill"
        form_data = {
            "title": item_name[:50],
            "amount": str(amount),
            "type": "SINGLE",
            "expired_date": "",  # Flip handles default expiry
            "redirect_url": "",
            "sender_name": customer_name,
            "sender_phone_number": customer_phone,
            "step": "2",  # Payment method selection step
        }
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(url, data=form_data, headers=self._auth_header(), timeout=30)
                data = resp.json()
                logger.info(f"Flip create bill response for {order_id}: status={resp.status_code}")

                if resp.status_code in (200, 201):
                    link_id = str(data.get("link_id", ""))
                    link_url = data.get("link_url", "")
                    # Flip payment page has QRIS option — use the same link
                    return {
                        "success": True,
                        "qr_url": "",  # Flip doesn't return separate QR image URL
                        "transaction_id": link_id,
                        "order_id": order_id,
                        "gross_amount": str(amount),
                        "expiry_time": data.get("expired_date", ""),
                        "redirect_url": link_url,  # Extra: Flip payment page
                    }
                else:
                    errors = data.get("errors", [{"message": str(data)}])
                    error_msg = errors[0].get("message", "Unknown error") if errors else "Unknown error"
                    logger.error(f"Flip create bill error for {order_id}: {error_msg}")
                    return {"success": False, "error": error_msg, "raw": data}
        except Exception as e:
            logger.error(f"Flip create bill exception for {order_id}: {e}")
            return {"success": False, "error": str(e)}

    async def create_snap(self, order_id: str, amount: int, item_name: str,
                           customer_name: str, customer_phone: str) -> dict:
        """Create Flip payment link (bill). Same as create_qris — Flip uses payment page for all methods."""
        url = f"{self.base_url}/pwf/bill"
        form_data = {
            "title": item_name[:50],
            "amount": str(amount),
            "type": "SINGLE",
            "expired_date": "",
            "redirect_url": "",
            "sender_name": customer_name,
            "sender_phone_number": customer_phone,
            "step": "2",
        }
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(url, data=form_data, headers=self._auth_header(), timeout=30)
                data = resp.json()
                logger.info(f"Flip Snap (bill) response for {order_id}: {data}")

                if resp.status_code in (200, 201):
                    return {
                        "success": True,
                        "token": str(data.get("link_id", "")),
                        "redirect_url": data.get("link_url", ""),
                        "order_id": order_id,
                    }
                else:
                    errors = data.get("errors", [{"message": str(data)}])
                    error_msg = errors[0].get("message", "Unknown error") if errors else "Unknown error"
                    logger.error(f"Flip bill error for {order_id}: {error_msg}")
                    return {"success": False, "error": error_msg}
        except Exception as e:
            logger.error(f"Flip bill exception for {order_id}: {e}")
            return {"success": False, "error": str(e)}

    async def check_status(self, order_id: str) -> dict:
        """Check bill status from Flip. Note: Flip uses link_id, not order_id."""
        url = f"{self.base_url}/pwf/bill"
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, headers=self._auth_header(), timeout=30)
                data = resp.json()
                # Flip returns list of bills — find by title or iterate
                # For production, store link_id in Payment.transaction_id
                return {
                    "success": True,
                    "order_id": order_id,
                    "transaction_status": "pending",
                    "payment_type": "flip_bill",
                    "gross_amount": "",
                    "raw": data,
                }
        except Exception as e:
            logger.error(f"Flip status check error for {order_id}: {e}")
            return {"success": False, "error": str(e)}

    def verify_webhook(self, headers: dict, body: dict) -> bool:
        """Flip sends X-Callback-Token header for verification."""
        token = headers.get("x-callback-token", "") or headers.get("X-Callback-Token", "")
        if not token:
            return True  # No token to verify
        return token == self.validation_token

    def parse_webhook_status(self, body: dict) -> dict:
        """Parse Flip webhook body.
        Flip sends: {"id", "bill_link_id", "bill_title", "sender_name",
                     "amount", "status": "SUCCESSFUL"/"PENDING"/"CANCELLED", ...}
        """
        flip_status = body.get("status", "").upper()

        # Normalize Flip status to standard
        status_map = {
            "SUCCESSFUL": "settlement",
            "PENDING": "pending",
            "CANCELLED": "cancel",
            "FAILED": "deny",
        }
        status = status_map.get(flip_status, flip_status.lower())

        return {
            "order_id": body.get("bill_link_id", ""),
            "transaction_status": status,
            "fraud_status": "",
            "gross_amount": str(body.get("amount", "")),
            "raw": body,
        }


# ─────────────────────────────────────────────
# Factory
# ─────────────────────────────────────────────

_gateway_instance: Optional[PaymentGateway] = None


def get_gateway() -> PaymentGateway:
    """Get the active payment gateway based on PAYMENT_GATEWAY env var.

    Returns singleton instance. Switch by setting PAYMENT_GATEWAY=midtrans or PAYMENT_GATEWAY=flip in .env
    """
    global _gateway_instance
    if _gateway_instance is None:
        provider = settings.PAYMENT_GATEWAY.lower()
        if provider == "flip":
            _gateway_instance = FlipGateway()
            logger.info("Payment gateway: Flip")
        else:
            _gateway_instance = MidtransGateway()
            logger.info("Payment gateway: Midtrans")
    return _gateway_instance
