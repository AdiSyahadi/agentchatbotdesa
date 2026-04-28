import base64
import json
import logging
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

SANDBOX_CORE_URL = "https://api.sandbox.midtrans.com"
PRODUCTION_CORE_URL = "https://api.midtrans.com"
SANDBOX_SNAP_URL = "https://app.sandbox.midtrans.com"
PRODUCTION_SNAP_URL = "https://app.midtrans.com"


def _get_core_url() -> str:
    return PRODUCTION_CORE_URL if settings.MIDTRANS_IS_PRODUCTION else SANDBOX_CORE_URL


def _get_snap_url() -> str:
    return PRODUCTION_SNAP_URL if settings.MIDTRANS_IS_PRODUCTION else SANDBOX_SNAP_URL


def _get_auth_header() -> dict:
    """Basic Auth header using Server Key."""
    encoded = base64.b64encode(f"{settings.MIDTRANS_SERVER_KEY}:".encode()).decode()
    return {
        "Authorization": f"Basic {encoded}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


async def create_qris_transaction(
    order_id: str,
    amount: int,
    item_name: str,
    customer_name: str,
    customer_phone: str,
) -> dict:
    """Create a QRIS payment transaction via Midtrans Core API.

    Returns dict with keys: success, qr_url, transaction_id, order_id, or error.
    """
    url = f"{_get_core_url()}/v2/charge"
    payload = {
        "payment_type": "qris",
        "transaction_details": {
            "order_id": order_id,
            "gross_amount": amount,
        },
        "item_details": [
            {
                "id": order_id,
                "price": amount,
                "quantity": 1,
                "name": item_name[:50],
            }
        ],
        "customer_details": {
            "first_name": customer_name,
            "phone": customer_phone,
        },
        "qris": {
            "acquirer": "gopay",
        },
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload, headers=_get_auth_header(), timeout=30)
            data = resp.json()
            logger.info(f"Midtrans QRIS response for {order_id}: status_code={resp.status_code}")

            if resp.status_code in (200, 201) and data.get("status_code") in ("200", "201"):
                # Extract QR URL from actions
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


async def create_va_transaction(
    order_id: str,
    amount: int,
    bank: str,
    item_name: str,
    customer_name: str,
    customer_phone: str,
) -> dict:
    """Create a Virtual Account payment transaction via Midtrans Core API.

    bank: bca, bni, bri, permata, cimb
    Returns dict with keys: success, va_number, bank, transaction_id, order_id, or error.
    """
    url = f"{_get_core_url()}/v2/charge"
    payload = {
        "payment_type": "bank_transfer",
        "transaction_details": {
            "order_id": order_id,
            "gross_amount": amount,
        },
        "item_details": [
            {
                "id": order_id,
                "price": amount,
                "quantity": 1,
                "name": item_name[:50],
            }
        ],
        "customer_details": {
            "first_name": customer_name,
            "phone": customer_phone,
        },
        "bank_transfer": {
            "bank": bank.lower(),
        },
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload, headers=_get_auth_header(), timeout=30)
            data = resp.json()
            logger.info(f"Midtrans VA response for {order_id}: status_code={resp.status_code}")

            if resp.status_code in (200, 201) and data.get("status_code") in ("200", "201"):
                # Extract VA number
                va_number = None
                va_numbers = data.get("va_numbers", [])
                if va_numbers:
                    va_number = va_numbers[0].get("va_number")

                # Permata uses permata_va_number
                if not va_number:
                    va_number = data.get("permata_va_number")

                return {
                    "success": True,
                    "va_number": va_number,
                    "bank": bank.upper(),
                    "transaction_id": data.get("transaction_id"),
                    "order_id": data.get("order_id"),
                    "gross_amount": data.get("gross_amount"),
                    "expiry_time": data.get("expiry_time"),
                }
            else:
                error_msg = data.get("status_message", "Unknown error")
                logger.error(f"Midtrans VA error for {order_id}: {error_msg}")
                return {"success": False, "error": error_msg, "raw": data}

    except Exception as e:
        logger.error(f"Midtrans VA exception for {order_id}: {e}")
        return {"success": False, "error": str(e)}


async def create_snap_transaction(
    order_id: str,
    amount: int,
    item_name: str,
    customer_name: str,
    customer_phone: str,
) -> dict:
    """Create a Snap payment transaction. Returns redirect_url for Midtrans payment page.

    User opens the URL in browser and can choose QRIS, VA, or any enabled payment method.
    """
    url = f"{_get_snap_url()}/snap/v1/transactions"
    payload = {
        "transaction_details": {
            "order_id": order_id,
            "gross_amount": amount,
        },
        "item_details": [
            {
                "id": order_id,
                "price": amount,
                "quantity": 1,
                "name": item_name[:50],
            }
        ],
        "customer_details": {
            "first_name": customer_name,
            "phone": customer_phone,
        },
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload, headers=_get_auth_header(), timeout=30)
            data = resp.json()
            logger.info(f"Midtrans Snap response for {order_id}: {data}")

            token = data.get("token")
            redirect_url = data.get("redirect_url")

            if token and redirect_url:
                return {
                    "success": True,
                    "token": token,
                    "redirect_url": redirect_url,
                    "order_id": order_id,
                }
            else:
                error_msgs = data.get("error_messages", [str(data)])
                logger.error(f"Midtrans Snap error for {order_id}: {error_msgs}")
                return {"success": False, "error": ", ".join(error_msgs)}

    except Exception as e:
        logger.error(f"Midtrans Snap exception for {order_id}: {e}")
        return {"success": False, "error": str(e)}


async def check_transaction_status(order_id: str) -> dict:
    """Check transaction status from Midtrans."""
    url = f"{_get_core_url()}/v2/{order_id}/status"

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=_get_auth_header(), timeout=30)
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
