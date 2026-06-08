"""Plantilla HTML unificada para correos clínicos (cuestionario, análisis, etc.)."""
from __future__ import annotations

from datetime import datetime
from html import escape as html_escape

from app.core.config import settings

# Acento Keepi (alineado con correos de pago)
_ACCENT = "#F26D2D"
_ACCENT_DARK = "#C2410C"
_LOGO_URL = (
    "https://raw.githubusercontent.com/AlejandroCastillo2406/Keepi_Front/"
    "master/assets/icons/logo.png"
)


def _brand() -> str:
    raw = (getattr(settings, "email_brand_name", None) or "").strip()
    if raw.startswith("http"):
        return "Keepi"
    return raw or "Keepi"


def _footer_block() -> str:
    year = datetime.now().year
    legal = (getattr(settings, "email_copyright_legal_name", None) or "").strip()
    if not legal:
        legal = f"{_brand()} © {year}"
    help_link = (getattr(settings, "email_link_help", None) or "").strip()
    support = (getattr(settings, "email_support_address", None) or "").strip()
    help_part = ""
    if help_link and help_link.startswith("http"):
        safe_help = html_escape(help_link, quote=True)
        help_part = (
            f' <a href="{safe_help}" style="color:{_ACCENT};text-decoration:none;">'
            "Centro de ayuda</a>"
        )
    support_part = ""
    if support and "@" in support:
        safe_sup = html_escape(support, quote=True)
        support_part = (
            f' o escríbenos a <a href="mailto:{safe_sup}" '
            f'style="color:{_ACCENT};text-decoration:none;">{safe_sup}</a>'
        )
    return f"""
      <p style="margin:28px 0 0;padding-top:22px;border-top:1px solid #E5E7EB;
                 font-size:13px;line-height:1.6;color:#9CA3AF;text-align:center;">
        ¿Necesitas ayuda?{help_part}{support_part}.
      </p>
      <p style="margin:12px 0 0;font-size:10px;color:#D1D5DB;text-align:center;
                letter-spacing:0.04em;">
        {html_escape(legal)}
      </p>"""


def _format_doctor_display(doctor_name: str) -> str:
    name = (doctor_name or "").strip() or "Tu médico"
    if name.lower().startswith(("dr.", "dr ", "dra.", "dra ")):
        return name
    return f"Dr. {name}"


def build_clinical_action_email_html(
    *,
    patient_name: str,
    doctor_name: str,
    headline: str,
    body_paragraphs: list[str],
    cta_label: str,
    cta_href: str,
    footer_note: str,
    highlight_box_html: str = "",
    badge_subtitle: str = "Solicitud de tu médico",
    secondary_cta_label: str = "", # <-- NUEVO PARÁMETRO
    secondary_cta_href: str = "",  # <-- NUEVO PARÁMETRO
) -> str:
    """
    Correo de acción del paciente (cuestionario, análisis, etc.) con nombre del doctor visible.
    """
    safe_brand = html_escape(_brand(), quote=True)
    safe_patient = html_escape((patient_name or "").strip() or "Hola", quote=True)
    safe_doctor = html_escape(_format_doctor_display(doctor_name), quote=True)
    safe_headline = html_escape(headline.strip(), quote=True)
    safe_badge = html_escape(badge_subtitle.strip(), quote=True)
    
    href = (cta_href or "").strip()
    label = (cta_label or "").strip()
    show_cta = href.startswith("http") and bool(label)
    safe_href = html_escape(href, quote=True)
    safe_cta = html_escape(label, quote=True)
    
    # Procesamiento del segundo botón
    sec_href = (secondary_cta_href or "").strip()
    sec_label = (secondary_cta_label or "").strip()
    show_sec_cta = sec_href.startswith("http") and bool(sec_label)
    safe_sec_href = html_escape(sec_href, quote=True)
    safe_sec_cta = html_escape(sec_label, quote=True)
    
    safe_footer = html_escape(footer_note.strip(), quote=True)

    cta_block = ""
    if show_cta or show_sec_cta:
        buttons_html = ""
        # Botón Principal
        if show_cta:
            buttons_html += f"""
              <a href="{safe_href}" target="_blank"
                style="display:inline-block;background:{_ACCENT};color:#ffffff;
                  text-decoration:none;font-size:15px;font-weight:600;
                  padding:14px 32px;border-radius:50px;min-width:200px;
                  text-align:center;box-shadow:0 4px 14px rgba(242,109,45,0.35);">
                {safe_cta}
              </a>
            """
        # Botón Secundario
        if show_sec_cta:
            margin_top = "margin-top: 14px;" if show_cta else ""
            buttons_html += f"""
              <div style="{margin_top}">
                  <a href="{safe_sec_href}" target="_blank"
                    style="display:inline-block;background:#FFF7ED;color:{_ACCENT_DARK};
                      text-decoration:none;font-size:15px;font-weight:600;
                      padding:14px 32px;border-radius:50px;min-width:200px;
                      text-align:center;border: 1px solid #FED7AA;">
                    {safe_sec_cta}
                  </a>
              </div>
            """

        cta_block = f"""
            <table role="presentation" border="0" cellpadding="0" cellspacing="0"
              style="margin:26px 0 8px;" width="100%">
              <tr>
                <td align="center">
                  {buttons_html}
                </td>
              </tr>
            </table>"""

    paragraphs_html = "".join(
        f'<p style="margin:0 0 14px;font-size:15px;line-height:1.65;color:#374151;">'
        f"{html_escape(p.strip(), quote=True)}</p>"
        for p in body_paragraphs
        if p and p.strip()
    )

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>{safe_headline} – {safe_brand}</title>
</head>
<body style="margin:0;padding:0;background:#f5f5f5;
  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">

  <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%"
    style="background:#f5f5f5;padding:32px 16px;">
    <tr><td align="center">

      <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%"
        style="max-width:440px;background:#ffffff;border-radius:16px;
               box-shadow:0 6px 28px rgba(0,0,0,0.08);overflow:hidden;">
        <tr>
          <td style="height:5px;background:{_ACCENT};font-size:0;line-height:0;">&nbsp;</td>
        </tr>
        <tr>
          <td style="padding:32px 28px 28px;">

            <table role="presentation" border="0" cellpadding="0" cellspacing="0"
              style="margin:0 0 22px;">
              <tr>
                <td valign="middle" style="padding-right:12px;">
                  <img src="{_LOGO_URL}" alt="{safe_brand}" width="40" height="40"
                    style="display:block;border-radius:10px;"/>
                </td>
                <td valign="middle">
                  <span style="font-size:22px;font-weight:800;color:#111827;
                    letter-spacing:-0.3px;">{safe_brand}</span>
                </td>
              </tr>
            </table>

            <table role="presentation" width="100%" border="0" cellpadding="0" cellspacing="0"
              style="margin:0 0 22px;background:#FFF7ED;border:1px solid #FED7AA;
                     border-radius:12px;">
              <tr>
                <td style="padding:14px 16px;">
                  <p style="margin:0 0 4px;font-size:11px;font-weight:700;
                    letter-spacing:0.06em;text-transform:uppercase;color:#9A3412;">
                    {safe_badge}
                  </p>
                  <p style="margin:0;font-size:18px;font-weight:700;color:#7C2D12;line-height:1.3;">
                    {safe_doctor}
                  </p>
                </td>
              </tr>
            </table>

            <p style="margin:0 0 8px;font-size:15px;color:#6B7280;">Hola {safe_patient},</p>
            <h1 style="margin:0 0 16px;font-size:22px;font-weight:700;color:#111827;
              line-height:1.3;">{safe_headline}</h1>

            {paragraphs_html}
            {highlight_box_html}
            {cta_block}

            <p style="margin:0;font-size:13px;line-height:1.55;color:#9CA3AF;text-align:center;">
              {safe_footer}
            </p>
            {_footer_block()}

          </td>
        </tr>
      </table>

    </td></tr>
  </table>
</body>
</html>"""