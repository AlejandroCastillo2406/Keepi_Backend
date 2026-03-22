"""
Arma los datos del recibo para el correo de confirmación a partir de Checkout Session (Stripe).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import stripe

from app.services.notificaciones.payment_email_service import (
    PaymentReceiptDetails,
    format_unix_to_spanish_date,
)
from app.services.stripe.stripe_config import ensure_stripe_key

logger = logging.getLogger(__name__)

# https://stripe.com/docs/currencies#zero-decimal
_ZERO_DECIMAL = frozenset(
    {
        "BIF",
        "CLP",
        "DJF",
        "GNF",
        "JPY",
        "KMF",
        "KRW",
        "MGA",
        "PYG",
        "RWF",
        "UGX",
        "VND",
        "VUV",
        "XAF",
        "XOF",
        "XPF",
    }
)


def _format_stripe_money(amount_total: Optional[int], currency: Optional[str]) -> str:
    if amount_total is None:
        return "—"
    cur = (currency or "usd").upper()
    if cur in _ZERO_DECIMAL:
        return f"{amount_total:,} {cur}"
    value = amount_total / 100.0
    return f"{value:,.2f} {cur}"


def _as_dict(obj: Any) -> Dict[str, Any]:
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    try:
        if hasattr(stripe, "util") and hasattr(stripe.util, "convert_to_dict"):
            return stripe.util.convert_to_dict(obj)
    except Exception:
        pass
    try:
        return dict(obj)
    except Exception:
        return {}


def _plan_from_line_items(session: Any) -> str:
    s = _as_dict(session)
    li = s.get("line_items")
    if not li:
        return "Suscripción Keepi"
    data = li.get("data") or []
    if not data:
        return "Suscripción Keepi"
    first = _as_dict(data[0])
    desc = first.get("description")
    if desc:
        return str(desc).strip() or "Suscripción Keepi"
    price = _as_dict(first.get("price"))
    prod = price.get("product")
    prod_d = _as_dict(prod)
    name = prod_d.get("name")
    if name:
        return str(name).strip() or "Suscripción Keepi"
    prod_id = prod if isinstance(prod, str) else prod_d.get("id")
    if prod_id and isinstance(prod_id, str):
        try:
            ensure_stripe_key()
            p = stripe.Product.retrieve(prod_id)
            pn = getattr(p, "name", None) or _as_dict(p).get("name")
            if pn:
                return str(pn)
        except Exception:
            pass
    return "Suscripción Keepi"


def _receipt_ref_from_session(session: Any) -> str:
    s = _as_dict(session)
    inv = s.get("invoice")
    inv_id = inv if isinstance(inv, str) else _as_dict(inv).get("id")
    if inv_id:
        try:
            ensure_stripe_key()
            inv_obj = stripe.Invoice.retrieve(inv_id)
            num = getattr(inv_obj, "number", None) or _as_dict(inv_obj).get("number")
            if num:
                return str(num)
            return str(inv_id)
        except Exception:
            return str(inv_id)
    sid = s.get("id") or "—"
    return str(sid)


def _payment_method_line(session: Any) -> str:
    s = _as_dict(session)
    inv = s.get("invoice")
    inv_id = inv if isinstance(inv, str) else _as_dict(inv).get("id")
    if not inv_id:
        return "—"
    try:
        ensure_stripe_key()
        inv_obj = stripe.Invoice.retrieve(
            inv_id,
            expand=["payment_intent.payment_method"],
        )
        idict = _as_dict(inv_obj)
        pi = idict.get("payment_intent")
        if isinstance(pi, str):
            pi = stripe.PaymentIntent.retrieve(pi, expand=["payment_method"])
            pi = _as_dict(pi)
        else:
            pi = _as_dict(pi)
        pm = pi.get("payment_method")
        if isinstance(pm, str):
            pm = stripe.PaymentMethod.retrieve(pm)
            pm = _as_dict(pm)
        else:
            pm = _as_dict(pm)
        card = _as_dict(pm.get("card"))
        brand = (card.get("brand") or "tarjeta").capitalize()
        last4 = card.get("last4")
        if last4:
            return f"{brand} •••• {last4}"
        return brand
    except Exception as exc:
        logger.debug("No se pudo obtener método de pago del invoice %s: %s", inv_id, exc)
        return "—"


def _details_from_snapshot(session_id: str, snap: Dict[str, Any]) -> PaymentReceiptDetails:
    amt = snap.get("amount_total")
    cur = snap.get("currency")
    created = snap.get("created")
    paid_on = format_unix_to_spanish_date(int(created)) if created else "—"
    money = _format_stripe_money(int(amt) if amt is not None else None, str(cur) if cur else None)
    return PaymentReceiptDetails(
        plan_line="Suscripción Keepi",
        amount_line=money,
        total_paid_line=money,
        paid_date_display=paid_on,
        receipt_reference=str(snap.get("id") or session_id),
        payment_method_line="—",
    )


def build_receipt_from_checkout_session(
    session_id: str,
    session_snapshot: Optional[Dict[str, Any]] = None,
) -> PaymentReceiptDetails:
    """
    Obtiene monto, moneda, línea de producto, fecha, recibo y tarjeta desde Stripe.
    Si falla la API, usa solo lo que venga en session_snapshot (objeto del webhook).
    """
    snap = session_snapshot or {}
    if not session_id:
        return _details_from_snapshot("—", snap)

    try:
        ensure_stripe_key()
        sess = stripe.checkout.Session.retrieve(
            session_id,
            expand=["line_items.data.price.product"],
        )
    except Exception as exc:
        logger.warning(
            "No se pudo recuperar la sesión de checkout %s: %s; se usan datos parciales",
            session_id,
            exc,
        )
        return _details_from_snapshot(session_id, snap)

    s = _as_dict(sess)
    amt = s.get("amount_total")
    if amt is None and snap.get("amount_total") is not None:
        amt = snap.get("amount_total")
    cur = s.get("currency") or snap.get("currency")
    created = s.get("created") or snap.get("created")
    paid_on = format_unix_to_spanish_date(int(created)) if created else "—"
    money = _format_stripe_money(int(amt) if amt is not None else None, str(cur) if cur else None)

    plan = _plan_from_line_items(sess)
    receipt_ref = _receipt_ref_from_session(sess)
    pm = _payment_method_line(sess)

    return PaymentReceiptDetails(
        plan_line=plan,
        amount_line=money,
        total_paid_line=money,
        paid_date_display=paid_on,
        receipt_reference=receipt_ref,
        payment_method_line=pm,
    )
