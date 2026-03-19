import os
from dataclasses import dataclass

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import settings


@dataclass
class PaymentEmailResult:
    success: bool
    error: str | None = None


def _email_asset_base_url() -> str:
    explicit_base_url = os.getenv("EMAIL_ASSET_BASE_URL")
    if explicit_base_url:
        return explicit_base_url.rstrip("/")

    redirect_uri = settings.google_redirect_uri or ""
    if "/api" in redirect_uri:
        return redirect_uri.rsplit("/api", 1)[0].rstrip("/")

    if settings.public_base_url:
        return settings.public_base_url.rstrip("/")

    return "https://keepi.onrender.com"


def _svg_check() -> str:
    return (
        f'<img src="{_email_asset_base_url()}/email-assets/check_orange.png" '
        'alt="" width="84" height="84" '
        'style="display:block;width:84px;height:84px;margin:0 auto;" />'
    )


def _svg_error() -> str:
    return (
        '<table role="presentation" cellspacing="0" cellpadding="0" border="0"'
        ' align="center" style="margin:0 auto;">'
        '<tr>'
        '<td width="64" height="64"'
        ' style="width:64px;height:64px;border-radius:50%;background:#DC2626;'
        'text-align:center;vertical-align:middle;'
        'font-size:28px;color:#ffffff;font-weight:700;line-height:64px;">'
        '&#10005;'
        '</td>'
        '</tr>'
        '</table>'
    )


def _svg_card() -> str:
    return (
        f'<img src="{_email_asset_base_url()}/email-assets/card_icon.png" '
        'alt="" width="18" height="13" '
        'style="vertical-align:middle;display:inline-block;margin-right:0;width:18px;height:13px;" />'
    )


def _build_html(icon_svg: str, title: str, subtitle: str) -> str:
    card_svg = _svg_card()
    return f"""\
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8"/>
  <title>{title} – Keepi</title>
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
                    Recibo #KP-88219
                  </td>
                </tr>

                <!-- plan row -->
                <tr>
                  <td style="font-size:14px;color:#111827;padding-bottom:16px;">
                    Plan Anual Keepi Pro
                  </td>
                  <td align="right"
                      style="font-size:14px;font-weight:700;color:#111827;
                             padding-bottom:16px;">
                    $79.99 USD
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
                    $79.99 USD
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
                      24 de Mayo, 2024
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
                          Visa &bull;&bull;&bull;&bull; 4242
                        </td>
                      </tr>
                    </table>
                  </td>
                </tr>

              </table>
              <!-- ─── END ORDER SUMMARY ─── -->

              <!-- button -->
              <div style="margin-top:28px;">
                <a href="https://keepi.app/account"
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
                <a href="https://keepi.app/help"
                   style="color:#F26D2D;text-decoration:none;">Centro de Ayuda</a>
                o contáctanos directamente en
                <a href="mailto:soporte@keepi.app"
                   style="color:#F26D2D;text-decoration:none;">soporte@keepi.app</a>.
              </p>

              <!-- copyright -->
              <p style="margin:16px 0 0 0;font-size:10px;color:#D1D5DB;
                         text-align:center;letter-spacing:0.04em;">
                &copy; 2024 KEEPI INC. TODOS LOS DERECHOS RESERVADOS.
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


def _build_success_html(user_name: str | None) -> str:
    name = f" {user_name}" if user_name else ""
    return _build_html(
        icon_svg=_svg_check(),
        title="Confirmación de Pago",
        subtitle=(
            f"¡Gracias por tu suscripción{name}! Hemos recibido tu pago "
            "correctamente y tu cuenta ya está activa."
        ),
    )


def _build_error_html(user_name: str | None) -> str:
    name = f" {user_name}" if user_name else ""
    return _build_html(
        icon_svg=_svg_error(),
        title="Error al procesar el pago",
        subtitle=(
            f"Hola{name}, no pudimos procesar tu pago. "
            "Por favor revisa tu método de pago o inténtalo nuevamente."
        ),
    )


def send_payment_email_ses(
    to_email: str,
    kind: str,
    user_name: str | None = None,
) -> PaymentEmailResult:
    if kind not in {"success", "error"}:
        return PaymentEmailResult(success=False, error="tipo inválido")

    html = _build_success_html(user_name) if kind == "success" else _build_error_html(user_name)
    subject = (
        "Confirmación de pago – Keepi"
        if kind == "success"
        else "Error al procesar tu pago – Keepi"
    )

    source_email = os.getenv("SES_FROM_EMAIL", "soporte@keepi.app")
    source_name = os.getenv("SES_FROM_NAME", "Keepi")

    client = boto3.client(
        "ses",
        region_name=settings.aws_region,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
    )

    try:
        client.send_email(
            Source=f"{source_name} <{source_email}>",
            Destination={"ToAddresses": [to_email]},
            Message={
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": {"Html": {"Data": html, "Charset": "UTF-8"}},
            },
        )
        return PaymentEmailResult(success=True)
    except (BotoCoreError, ClientError) as exc:
        return PaymentEmailResult(success=False, error=str(exc))
