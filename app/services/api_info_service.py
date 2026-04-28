from app.core.config import settings


class ApiInfoService:
    @staticmethod
    def root_payload() -> dict:
        return {
            "service": settings.api_title,
            "version": settings.api_version,
            "status": "ok",
        }
