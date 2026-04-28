from __future__ import annotations

from app.core.config import settings

REQUIRED_EMAIL_TEMPLATE_KEYS: list[tuple[str, str]] = [
    ("EMAIL_URL_ICON_CHECK", "email_url_icon_check"),
    ("EMAIL_URL_ICON_CARD", "email_url_icon_card"),
    ("EMAIL_URL_ICON_VENCIMIENTO", "email_url_icon_vencimiento"),
    ("EMAIL_URL_FOOTER_SOCIALS", "email_url_footer_socials"),
    ("EMAIL_LINK_ACCOUNT", "email_link_account"),
    ("EMAIL_LINK_HELP", "email_link_help"),
    ("EMAIL_SUPPORT_ADDRESS", "email_support_address"),
    ("EMAIL_BRAND_NAME", "email_brand_name"),
    ("EMAIL_COPYRIGHT_LEGAL_NAME", "email_copyright_legal_name"),
    ("EMAIL_PLACEHOLDER_DISPLAY_NAME", "email_placeholder_display_name"),
    ("SES_FROM_EMAIL", "ses_from_email"),
    ("SES_FROM_NAME", "ses_from_name"),
]


def missing_email_template_config() -> list[str]:
    missing: list[str] = []
    for env_name, attr in REQUIRED_EMAIL_TEMPLATE_KEYS:
        raw = getattr(settings, attr, None)
        if raw is None or not str(raw).strip():
            missing.append(env_name)
    return missing


def require_email_template_config() -> None:
    m = missing_email_template_config()
    if m:
        raise ValueError(
            "Faltan variables en .env para correos HTML (Cloudinary + enlaces + SES). "
            "Revisa backend/.env.example — faltan: " + ", ".join(m)
        )
