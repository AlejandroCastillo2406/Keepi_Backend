from dataclasses import dataclass
from datetime import date, datetime, timezone
from html import escape as html_escape

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import settings
from app.services.notificaciones.email_template_env import require_email_template_config


@dataclass
class PaymentEmailResult:
    success: bool
    error: str | None = None
    ses_message_id: str | None = None


_SPANISH_MONTHS_FULL = (
    "Enero",
    "Febrero",
    "Marzo",
    "Abril",
    "Mayo",
    "Junio",
    "Julio",
    "Agosto",
    "Septiembre",
    "Octubre",
    "Noviembre",
    "Diciembre",
)


def format_unix_to_spanish_date(ts: int) -> str:
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    return f"{dt.day} de {_SPANISH_MONTHS_FULL[dt.month - 1]} de {dt.year}"


@dataclass(frozen=True)
class PaymentReceiptDetails:

    plan_line: str
    amount_line: str
    total_paid_line: str
    paid_date_display: str
    receipt_reference: str
    payment_method_line: str

    @staticmethod
    def generic_placeholder() -> "PaymentReceiptDetails":
        today = date.today()
        dstr = f"{today.day} de {_SPANISH_MONTHS_FULL[today.month - 1]} de {today.year}"
        brand = (settings.email_brand_name or "").strip() or "—"
        return PaymentReceiptDetails(
            plan_line=f"Plan {brand}",
            amount_line="—",
            total_paid_line="—",
            paid_date_display=dstr,
            receipt_reference="—",
            payment_method_line="—",
        )


def _svg_check() -> str:
    u = html_escape(settings.email_url_icon_check)
    return (
        f'<img src="{u}" '
        'alt="" width="84" height="84" '
        'style="display:block;width:84px;height:84px;margin:0 auto;" />'
    )


def _svg_error() -> str:
    return (
        '<table role="presentation" cellspacing="0" cellpadding="0" border="0"'
        ' align="center" style="margin:0 auto;">'
        "<tr>"
        '<td width="64" height="64"'
        ' style="width:64px;height:64px;border-radius:50%;background:#DC2626;'
        "text-align:center;vertical-align:middle;"
        'font-size:28px;color:#ffffff;font-weight:700;line-height:64px;">'
        "&#10005;"
        "</td>"
        "</tr>"
        "</table>"
    )


def _svg_card() -> str:
    u = html_escape(settings.email_url_icon_card)
    return (
        f'<img src="{u}" '
        'alt="" width="18" height="13" '
        'style="vertical-align:middle;display:inline-block;margin-right:0;width:18px;height:13px;" />'
    )


def _vencimiento_icon_img(width: int = 64, height: int = 64) -> str:
    u = html_escape(settings.email_url_icon_vencimiento)
    return (
        f'<img src="{u}" '
        f'alt="" width="{width}" height="{height}" '
        f'style="display:block;width:{width}px;height:{height}px;margin:0 auto;" />'
    )


def _footer_socials_img(width: int = 118, height: int = 24) -> str:
    u = html_escape(settings.email_url_footer_socials)
    return (
        f'<img src="{u}" '
        f'alt="" width="{width}" height="{height}" '
        f'style="display:block;width:{width}px;height:{height}px;margin:0 auto;" />'
    )


def _build_html(
    icon_svg: str,
    title: str,
    subtitle: str,
    receipt: PaymentReceiptDetails,
) -> str:
    require_email_template_config()
    card_svg = _svg_card()
    safe_plan = html_escape(receipt.plan_line)
    safe_amount = html_escape(receipt.amount_line)
    safe_total = html_escape(receipt.total_paid_line)
    safe_date = html_escape(receipt.paid_date_display)
    safe_ref = html_escape(receipt.receipt_reference)
    safe_pm = html_escape(receipt.payment_method_line)
    year = datetime.now().year
    safe_brand = html_escape(settings.email_brand_name)
    safe_legal = html_escape(settings.email_copyright_legal_name)
    safe_link_account = html_escape(settings.email_link_account)
    safe_link_help = html_escape(settings.email_link_help)
    safe_support = html_escape(settings.email_support_address)
    return f"""\
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8"/>
  <title>{html_escape(title)} – {safe_brand}</title>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
</head>
<body style="margin:0;padding:0;background:#f5f5f5;
  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">

  <!-- outer wrapper -->
  <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%"
    style="background:#f5f5f5;padding:32px 16px;">
    <tr>
      <td align="center">

        <!-- card -->
        <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%"
          style="max-width:420px;background:#ffffff;border-radius:16px;
                 box-shadow:0 6px 28px rgba(0,0,0,0.09);">
          <tr>
            <td style="padding:40px 28px 32px 28px;">

              <!-- icon -->
              <div style="text-align:center;margin-bottom:22px;">
                {icon_svg}
              </div>

              <!-- title -->
              <h1 style="margin:0 0 12px 0;font-size:24px;font-weight:700;
                          color:#111827;text-align:center;line-height:1.3;">
                {title}
              </h1>

              <!-- subtitle -->
              <p style="margin:0 0 28px 0;font-size:14px;line-height:1.65;
                         color:#6B7280;text-align:center;">
                {subtitle}
              </p>

              <!-- ─── ORDER SUMMARY ─── -->
              <table role="presentation" cellspacing="0" cellpadding="0"
                     border="0" width="100%">

                <!-- separator line -->
                <tr>
                  <td colspan="2" height="1"
                      style="background:#E5E7EB;font-size:0;line-height:0;padding:0;"
                  >&nbsp;</td>
                </tr>
                <tr>
                  <td colspan="2" height="16"
                      style="font-size:0;line-height:0;padding:0;"
                  >&nbsp;</td>
                </tr>

                <!-- header labels -->
                <tr>
                  <td style="font-size:10px;color:#9CA3AF;letter-spacing:0.07em;
                              text-transform:uppercase;padding-bottom:10px;">
                    Resumen del pedido
                  </td>
                  <td align="right"
                      style="font-size:11px;color:#9CA3AF;padding-bottom:10px;">
                    Ref. {safe_ref}
                  </td>
                </tr>

                <!-- plan row -->
                <tr>
                  <td style="font-size:14px;color:#111827;padding-bottom:16px;">
                    {safe_plan}
                  </td>
                  <td align="right"
                      style="font-size:14px;font-weight:700;color:#111827;
                             padding-bottom:16px;">
                    {safe_amount}
                  </td>
                </tr>

                <!-- separator line -->
                <tr>
                  <td colspan="2" height="1"
                      style="background:#E5E7EB;font-size:0;line-height:0;padding:0;"
                  >&nbsp;</td>
                </tr>
                <tr>
                  <td colspan="2" height="16"
                      style="font-size:0;line-height:0;padding:0;"
                  >&nbsp;</td>
                </tr>

                <!-- total row -->
                <tr>
                  <td style="font-size:14px;color:#111827;padding-bottom:16px;">
                    Total pagado
                  </td>
                  <td align="right"
                      style="font-size:16px;font-weight:700;color:#F26D2D;
                             padding-bottom:16px;">
                    {safe_total}
                  </td>
                </tr>

                <!-- separator line -->
                <tr>
                  <td colspan="2" height="1"
                      style="background:#E5E7EB;font-size:0;line-height:0;padding:0;"
                  >&nbsp;</td>
                </tr>
                <tr>
                  <td colspan="2" height="16"
                      style="font-size:0;line-height:0;padding:0;"
                  >&nbsp;</td>
                </tr>

                <!-- date / payment method -->
                <tr>
                  <td style="vertical-align:top;padding-bottom:4px;">
                    <div style="font-size:10px;color:#9CA3AF;letter-spacing:0.07em;
                                text-transform:uppercase;margin-bottom:5px;">
                      Fecha
                    </div>
                    <div style="font-size:14px;font-weight:600;color:#111827;">
                      {safe_date}
                    </div>
                  </td>
                  <td align="right" style="vertical-align:top;padding-bottom:4px;">
                    <div style="font-size:10px;color:#9CA3AF;letter-spacing:0.07em;
                                text-transform:uppercase;margin-bottom:5px;">
                      Método de pago
                    </div>
                    <table role="presentation" cellspacing="0" cellpadding="0" border="0" align="right">
                      <tr>
                        <td style="vertical-align:middle;padding-right:1px;">
                          {card_svg}
                        </td>
                        <td style="vertical-align:middle;font-size:14px;font-weight:600;color:#111827;white-space:nowrap;">
                          {safe_pm}
                        </td>
                      </tr>
                    </table>
                  </td>
                </tr>

              </table>
              <!-- ─── END ORDER SUMMARY ─── -->

              <!-- button -->
              <div style="margin-top:28px;">
                <a href="{safe_link_account}"
                   style="display:block;background:#F26D2D;color:#ffffff;
                          text-decoration:none;font-size:15px;font-weight:600;
                          padding:15px 0;border-radius:50px;text-align:center;">
                  Ir a mi cuenta
                </a>
              </div>

              <!-- help text -->
              <p style="margin:24px 0 0 0;padding-top:22px;
                         border-top:1px solid #E5E7EB;
                         font-size:13px;line-height:1.6;
                         color:#9CA3AF;text-align:center;">
                ¿Tienes alguna pregunta? Visita nuestro
                <a href="{safe_link_help}"
                   style="color:#F26D2D;text-decoration:none;">Centro de Ayuda</a>
                o contáctanos directamente en
                <a href="mailto:{safe_support}"
                   style="color:#F26D2D;text-decoration:none;">{safe_support}</a>.
              </p>

              <!-- copyright -->
              <p style="margin:16px 0 0 0;font-size:10px;color:#D1D5DB;
                         text-align:center;letter-spacing:0.04em;">
                &copy; {year} {safe_legal}. TODOS LOS DERECHOS RESERVADOS.
              </p>

            </td>
          </tr>
        </table>
        <!-- end card -->

      </td>
    </tr>
  </table>
</body>
</html>"""


def _build_success_html(
    user_name: str | None,
    receipt: PaymentReceiptDetails | None = None,
) -> str:
    require_email_template_config()
    r = receipt or PaymentReceiptDetails.generic_placeholder()
    safe_name = html_escape(user_name) if user_name else ""
    name_part = f" {safe_name}" if safe_name else ""
    subtitle = (
        f"¡Gracias por tu suscripción{name_part}! Hemos recibido tu pago "
        "correctamente y tu cuenta ya está activa."
    )
    return _build_html(
        icon_svg=_svg_check(),
        title="Confirmación de Pago",
        subtitle=subtitle,
        receipt=r,
    )


def _build_vencimiento_html(user_name: str | None) -> str:
    require_email_template_config()
    display_name = html_escape(user_name or settings.email_placeholder_display_name)
    safe_brand = html_escape(settings.email_brand_name)
    safe_link_account = html_escape(settings.email_link_account)
    safe_legal = html_escape(settings.email_copyright_legal_name)
    year = datetime.now().year
    vencimiento_icon = _vencimiento_icon_img(64, 64)
    footer_socials = _footer_socials_img(118, 24)
    return f"""\
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8"/>
  <title>Recordatorio de vencimiento – {safe_brand}</title>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
</head>
<body style="margin:0;padding:0;background:#f7efe9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
  <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="background:#f7efe9;">
    <tr>
      <td align="center">
        <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="max-width:500px;background:#fff7f2;">
          <tr>
            <td style="background:linear-gradient(135deg,#f56a17 0%,#8c8c93 100%);padding:26px 16px 18px 16px;">
              <div style="display:inline-block;background:#ff6a1a;color:#ffffff;font-size:11px;font-weight:700;line-height:1;padding:5px 10px;border-radius:14px;text-transform:uppercase;letter-spacing:0.02em;">
                Urgente
              </div>
              <div style="margin-top:12px;font-size:24px;font-weight:700;line-height:1.25;color:#ffffff;max-width:230px;">
                Tu documento vence pronto
              </div>
            </td>
          </tr>
          <tr>
            <td style="background:#fff7f2;padding:0 10px 10px 10px;">
              <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="background:#ffffff;border-radius:0 0 18px 18px;">
                <tr>
                  <td style="padding:28px 26px 24px 26px;text-align:center;">
                    <div style="margin:0 auto 14px auto;">{vencimiento_icon}</div>
                    <div style="font-size:20px;font-weight:700;line-height:1.25;color:#1f2937;margin-bottom:18px;">
                      Recordatorio de vencimiento
                    </div>
                    <div style="font-size:16px;line-height:1.9;color:#5f6f86;margin:0 auto;max-width:390px;">
                      Hola <span style="font-weight:700;color:#273449;">{display_name}</span>, te recordamos que tu<br/>
                      documento<br/>
                      <span style="font-style:italic;color:#ff6a1a;">'Cotización Cetelem'</span><br/>
                      vence en <span style="font-weight:700;color:#1f2937;">3 días (27 de Octubre).</span>
                    </div>
                    <div style="height:26px;line-height:26px;font-size:1px;">&nbsp;</div>
                    <div style="font-size:17px;line-height:1.7;color:#5f6f86;max-width:420px;margin:0 auto;">
                      ¿Deseas renovarlo o archivarlo para<br/>
                      mantener tus registros actualizados?
                    </div>
                    <div style="height:34px;line-height:34px;font-size:1px;">&nbsp;</div>
                    <a href="{safe_link_account}" style="display:block;background:#ff620f;color:#ffffff;text-decoration:none;font-size:17px;font-weight:700;line-height:1;padding:20px 18px;border-radius:16px;box-shadow:0 10px 24px rgba(255,98,15,0.24);">
                      Gestionar Documento
                    </a>
                    <div style="height:18px;line-height:18px;font-size:1px;">&nbsp;</div>
                    <a href="{safe_link_account}" style="font-size:16px;font-weight:500;line-height:1.4;color:#ff6a1a;text-decoration:none;">
                      Ir directamente a la aplicación
                    </a>
                  </td>
                </tr>
                <tr>
                  <td style="border-top:1px solid #f1ddd0;padding:20px 26px 16px 26px;text-align:center;">
                    <div style="font-size:12px;line-height:1.6;color:#7f8da3;max-width:360px;margin:0 auto;">
                      Este es un mensaje automático enviado por {safe_brand}.<br/>
                      Si tienes alguna duda, contacta con nuestro soporte<br/>
                      técnico.
                    </div>
                    <div style="height:14px;line-height:14px;font-size:1px;">&nbsp;</div>
                    <div style="margin:0 auto 12px auto;">{footer_socials}</div>
                    <div style="font-size:11px;line-height:1.4;color:#b0b8c7;letter-spacing:0.02em;">
                      © {year} {safe_legal}
                    </div>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def _format_spanish_date(d: date) -> str:
    return f"{d.day} de {_SPANISH_MONTHS_FULL[d.month - 1]}"


def _format_days_spanish(days: int) -> str:
    if days == 1:
        return "1 día"
    return f"{days} días"


def _build_vencimiento_html_real(
    user_name: str | None,
    document_title: str,
    expiry_date: date,
    days_before: int,
) -> str:
    require_email_template_config()
    display_name = html_escape(user_name or settings.email_placeholder_display_name)
    safe_document_title = html_escape(document_title)
    safe_days_text = _format_days_spanish(days_before)
    safe_expiry_date = _format_spanish_date(expiry_date)

    safe_brand = html_escape(settings.email_brand_name)
    safe_link_account = html_escape(settings.email_link_account)
    safe_legal = html_escape(settings.email_copyright_legal_name)
    year = datetime.now().year

    vencimiento_icon = _vencimiento_icon_img(64, 64)
    footer_socials = _footer_socials_img(118, 24)

    return f"""\
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8"/>
  <title>Recordatorio de vencimiento – {safe_brand}</title>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
</head>
<body style="margin:0;padding:0;background:#f7efe9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
  <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="background:#f7efe9;">
    <tr>
      <td align="center">
        <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="max-width:500px;background:#fff7f2;">
          <tr>
            <td style="background:linear-gradient(135deg,#f56a17 0%,#8c8c93 100%);padding:26px 16px 18px 16px;">
              <div style="display:inline-block;background:#ff6a1a;color:#ffffff;font-size:11px;font-weight:700;line-height:1;padding:5px 10px;border-radius:14px;text-transform:uppercase;letter-spacing:0.02em;">
                Urgente
              </div>
              <div style="margin-top:12px;font-size:24px;font-weight:700;line-height:1.25;color:#ffffff;max-width:230px;">
                Tu documento vence pronto
              </div>
            </td>
          </tr>
          <tr>
            <td style="background:#fff7f2;padding:0 10px 10px 10px;">
              <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="background:#ffffff;border-radius:0 0 18px 18px;">
                <tr>
                  <td style="padding:28px 26px 24px 26px;text-align:center;">
                    <div style="margin:0 auto 14px auto;">{vencimiento_icon}</div>
                    <div style="font-size:20px;font-weight:700;line-height:1.25;color:#1f2937;margin-bottom:18px;">
                      Recordatorio de vencimiento
                    </div>
                    <div style="font-size:16px;line-height:1.9;color:#5f6f86;margin:0 auto;max-width:390px;">
                      Hola <span style="font-weight:700;color:#273449;">{display_name}</span>, te recordamos que tu<br/>
                      documento<br/>
                      <span style="font-style:italic;color:#ff6a1a;">'{safe_document_title}'</span><br/>
                      vence en <span style="font-weight:700;color:#1f2937;">{safe_days_text} ({safe_expiry_date}).</span>
                    </div>
                    <div style="height:26px;line-height:26px;font-size:1px;">&nbsp;</div>
                    <div style="font-size:17px;line-height:1.7;color:#5f6f86;max-width:420px;margin:0 auto;">
                      ¿Deseas renovarlo o archivarlo para<br/>
                      mantener tus registros actualizados?
                    </div>
                    <div style="height:34px;line-height:34px;font-size:1px;">&nbsp;</div>
                    <a href="{safe_link_account}" style="display:block;background:#ff620f;color:#ffffff;text-decoration:none;font-size:17px;font-weight:700;line-height:1;padding:20px 18px;border-radius:16px;box-shadow:0 10px 24px rgba(255,98,15,0.24);">
                      Gestionar Documento
                    </a>
                    <div style="height:18px;line-height:18px;font-size:1px;">&nbsp;</div>
                    <a href="{safe_link_account}" style="font-size:16px;font-weight:500;line-height:1.4;color:#ff6a1a;text-decoration:none;">
                      Ir directamente a la aplicación
                    </a>
                  </td>
                </tr>
                <tr>
                  <td style="border-top:1px solid #f1ddd0;padding:20px 26px 16px 26px;text-align:center;">
                    <div style="font-size:12px;line-height:1.6;color:#7f8da3;max-width:360px;margin:0 auto;">
                      Este es un mensaje automático enviado por {safe_brand}.<br/>
                      Si tienes alguna duda, contacta con nuestro soporte<br/>
                      técnico.
                    </div>
                    <div style="height:14px;line-height:14px;font-size:1px;">&nbsp;</div>
                    <div style="margin:0 auto 12px auto;">{footer_socials}</div>
                    <div style="font-size:11px;line-height:1.4;color:#b0b8c7;letter-spacing:0.02em;">
                      © {year} {safe_legal}
                    </div>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def send_vencimiento_email_ses(
    to_email: str,
    user_name: str | None,
    document_title: str,
    expiry_date: date,
    days_before: int,
) -> PaymentEmailResult:
    try:
        html = _build_vencimiento_html_real(
            user_name=user_name,
            document_title=document_title,
            expiry_date=expiry_date,
            days_before=days_before,
        )
    except ValueError as exc:
        return PaymentEmailResult(success=False, error=str(exc))

    subject = f"Tu documento vence pronto – {settings.email_brand_name}"

    source_email = settings.ses_from_email
    source_name = settings.ses_from_name

    client = boto3.client(
        "ses",
        region_name=settings.aws_region,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
    )

    try:
        result = client.send_email(
            Source=f"{source_name} <{source_email}>",
            Destination={"ToAddresses": [to_email]},
            Message={
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": {"Html": {"Data": html, "Charset": "UTF-8"}},
            },
        )
        return PaymentEmailResult(success=True, ses_message_id=result.get("MessageId"))
    except (BotoCoreError, ClientError) as exc:
        return PaymentEmailResult(success=False, error=str(exc))


def send_payment_email_ses(
    to_email: str,
    kind: str,
    user_name: str | None = None,
    receipt: PaymentReceiptDetails | None = None,
) -> PaymentEmailResult:
    if kind not in {"success", "vencimiento"}:
        return PaymentEmailResult(success=False, error="tipo inválido")

    try:
        html = (
            _build_success_html(user_name, receipt=receipt)
            if kind == "success"
            else _build_vencimiento_html(user_name)
        )
    except ValueError as exc:
        return PaymentEmailResult(success=False, error=str(exc))

    brand = settings.email_brand_name
    subject = (
        f"Confirmación de pago – {brand}"
        if kind == "success"
        else f"Tu documento vence pronto – {brand}"
    )

    source_email = settings.ses_from_email
    source_name = settings.ses_from_name

    client = boto3.client(
        "ses",
        region_name=settings.aws_region,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
    )

    try:
        result = client.send_email(
            Source=f"{source_name} <{source_email}>",
            Destination={"ToAddresses": [to_email]},
            Message={
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": {"Html": {"Data": html, "Charset": "UTF-8"}},
            },
        )
        return PaymentEmailResult(success=True, ses_message_id=result.get("MessageId"))
    except (BotoCoreError, ClientError) as exc:
        return PaymentEmailResult(success=False, error=str(exc))


def send_simple_html_email_ses(
    to_email: str, subject: str, html_body: str
) -> PaymentEmailResult:
    source_email = (settings.ses_from_email or "").strip()
    source_name = (settings.ses_from_name or "").strip() or source_email
    if not source_email:
        return PaymentEmailResult(success=False, error="SES_FROM_EMAIL no configurado")
    if not settings.aws_access_key_id or not settings.aws_secret_access_key:
        return PaymentEmailResult(
            success=False, error="Credenciales AWS no configuradas"
        )

    client = boto3.client(
        "ses",
        region_name=settings.aws_region,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
    )

    try:
        result = client.send_email(
            Source=f"{source_name} <{source_email}>",
            Destination={"ToAddresses": [to_email.strip()]},
            Message={
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": {"Html": {"Data": html_body, "Charset": "UTF-8"}},
            },
        )
        return PaymentEmailResult(success=True, ses_message_id=result.get("MessageId"))
    except (BotoCoreError, ClientError) as exc:
        return PaymentEmailResult(success=False, error=str(exc))
