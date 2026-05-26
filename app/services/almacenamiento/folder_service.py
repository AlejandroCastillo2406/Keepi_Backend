import logging
import re
import unicodedata
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.services.almacenamiento.drive_service import GoogleDriveService
from app.services.almacenamiento.s3_service import S3Service

logger = logging.getLogger(__name__)


class FolderService:

    def __init__(self, db: Session):
        self._db = db
        self.s3_service = S3Service()

    async def create_category_folder(
        self, user_id: str, category: str, storage_preference: str
    ) -> Dict[str, Any]:
        category = self._normalize_category_name(category) or category
        try:

            folder_name = self._clean_folder_name(category, storage_preference)

            if storage_preference == "keepi_cloud":

                folder_path = f"users/{user_id}/{folder_name}/"
                result = await self._create_s3_folder(folder_path)

            elif storage_preference == "google_drive":

                result = await self._create_drive_folder(folder_name, user_id)

            else:
                raise ValueError(
                    f"Tipo de almacenamiento no soportado: {storage_preference}"
                )

            return {
                "success": True,
                "folder_name": folder_name,
                "folder_path": result.get("path", ""),
                "folder_id": result.get("id", ""),
                "storage_type": storage_preference,
            }

        except Exception as e:
            logger.error(f"Error creando carpeta de categoría: {e}")
            return {
                "success": False,
                "error": str(e),
                "folder_name": category,
                "storage_type": storage_preference,
            }

    def _clean_folder_name(self, category: str, storage_preference: str = None) -> str:
        if storage_preference == "keepi_cloud":

            try:

                normalized = unicodedata.normalize("NFD", category)

                ascii_name = normalized.encode("ascii", "ignore").decode("ascii")

                if not ascii_name.strip():
                    ascii_name = category

                sanitized = re.sub(r"[^a-zA-Z0-9\-_]", "_", ascii_name)
                return sanitized[:50]
            except Exception as e:
                logger.warning(f"Error sanitizando nombre de carpeta: {e}")

                sanitized = re.sub(r"[^a-zA-Z0-9\-_]", "_", category)
                return sanitized[:50]
        else:

            clean_name = re.sub(r"\s+", " ", category.strip())

            if len(clean_name) > 100:
                clean_name = clean_name[:100]
            return clean_name

    async def _create_s3_folder(self, folder_path: str) -> Dict[str, Any]:
        try:

            await self.s3_service.ensure_bucket_exists()

            return {"path": folder_path, "id": folder_path, "created": True}

        except Exception as e:
            logger.error(f"Error creando carpeta en S3: {e}")
            raise

    async def _create_drive_folder(
        self, folder_name: str, user_id: str
    ) -> Dict[str, Any]:
        try:

            from app.services.autenticacion import GoogleOAuthService

            oauth_service = GoogleOAuthService(self._db)
            credentials = await oauth_service.refresh_user_tokens(user_id)

            if not credentials:
                raise Exception(
                    "Usuario no tiene credenciales de Google Drive configuradas"
                )

            drive_service = GoogleDriveService(credentials)

            existing_folder = await self._find_drive_folder_with_service(
                folder_name, drive_service
            )
            if existing_folder:
                return {
                    "path": existing_folder["name"],
                    "id": existing_folder["id"],
                    "created": False,
                    "already_exists": True,
                }

            folder_metadata = {
                "name": folder_name,
                "mimeType": "application/vnd.google-apps.folder",
                "parents": [],
            }

            folder = (
                drive_service.service.files()
                .create(body=folder_metadata, fields="id, name")
                .execute()
            )

            return {"path": folder_name, "id": folder["id"], "created": True}

        except Exception as e:
            logger.error(f"Error creando carpeta en Drive: {e}")
            raise

    async def _find_drive_folder_with_service(
        self, folder_name: str, drive_service: GoogleDriveService
    ) -> Optional[Dict[str, Any]]:
        try:

            escaped_name = folder_name.replace("'", "\\'").replace('"', '\\"')
            query = f"name='{escaped_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"

            logger.info("Buscando carpeta en Drive: '%s'", folder_name)
            logger.debug("Query Drive: %s", query)

            results = (
                drive_service.service.files()
                .list(q=query, fields="files(id, name)", spaces="drive")
                .execute()
            )

            folders = results.get("files", [])
            if folders:
                logger.info(
                    "Carpeta encontrada: '%s' (ID: %s)",
                    folders[0]["name"],
                    folders[0]["id"],
                )
                return folders[0]

            logger.warning("Carpeta '%s' no encontrada en Drive", folder_name)
            return None

        except Exception:
            logger.exception("Error buscando carpeta en Drive")
            import traceback

            logger.error(traceback.format_exc())
            return None

    def _normalize_category_name(self, category: str) -> str:
        raw = (category or "").strip()
        if raw.lower() == "recetas":
            return "recetas"
        return raw.title() if raw else ""

    async def ensure_category_folder_exists(
        self, user_id: str, category: str, storage_preference: str
    ) -> Dict[str, Any]:
        try:
            category = self._normalize_category_name(category) or category
            if storage_preference == "keepi_cloud":

                folder_name = self._clean_folder_name(category, storage_preference)
                folder_path = f"users/{user_id}/{folder_name}/"
                exists = await self._check_s3_folder_exists(folder_path)

                return {
                    "success": True,
                    "folder_exists": exists,
                    "folder_name": folder_name,
                    "folder_id": folder_path,
                    "folder_path": folder_path,
                    "storage_type": storage_preference,
                }

            elif storage_preference == "google_drive":
                folder_name = self._clean_folder_name(category, storage_preference)

                from app.services.autenticacion import GoogleOAuthService

                oauth_service = GoogleOAuthService(self._db)
                credentials = await oauth_service.refresh_user_tokens(user_id)

                if not credentials:

                    auth_data = await oauth_service.get_authorization_url(user_id)
                    return {
                        "success": False,
                        "requires_drive_auth": True,
                        "error": "Usuario no tiene credenciales de Google Drive configuradas",
                        "drive_auth_url": auth_data.get("authorization_url", ""),
                        "folder_name": category,
                        "storage_type": storage_preference,
                    }

                try:
                    drive_service = GoogleDriveService(credentials)
                    existing_folder = await self._find_drive_folder_with_service(
                        folder_name, drive_service
                    )

                    if existing_folder:
                        logger.info(
                            "Carpeta '%s' ya existe en Drive (ID: %s)",
                            folder_name,
                            existing_folder["id"],
                        )
                        return {
                            "success": True,
                            "folder_exists": True,
                            "folder_name": folder_name,
                            "folder_id": existing_folder["id"],
                            "folder_path": f"https://drive.google.com/drive/folders/{existing_folder['id']}",
                            "storage_type": storage_preference,
                        }

                    logger.info("Carpeta '%s' no existe, creando en Drive", folder_name)
                    try:
                        folder_id = await drive_service.create_folder(folder_name)
                        logger.info(
                            "Carpeta '%s' creada (ID: %s)", folder_name, folder_id
                        )
                        return {
                            "success": True,
                            "folder_exists": False,
                            "folder_name": folder_name,
                            "folder_id": folder_id,
                            "folder_path": f"https://drive.google.com/drive/folders/{folder_id}",
                            "storage_type": storage_preference,
                        }
                    except Exception as create_error:
                        logger.error(
                            f"Error creando carpeta en Google Drive: {create_error}"
                        )
                        raise Exception(
                            f"No se pudo crear la carpeta en Google Drive: {str(create_error)}"
                        )

                except Exception as drive_error:

                    if (
                        "invalid_grant" in str(drive_error)
                        or "credentials" in str(drive_error).lower()
                    ):

                        auth_data = await oauth_service.get_authorization_url(user_id)
                        return {
                            "success": False,
                            "requires_drive_auth": True,
                            "error": "Credenciales de Google Drive expiradas o inválidas",
                            "drive_auth_url": auth_data.get("authorization_url", ""),
                            "folder_name": category,
                            "storage_type": storage_preference,
                        }
                    else:
                        raise drive_error
            else:
                raise ValueError(
                    f"Tipo de almacenamiento no soportado: {storage_preference}"
                )

        except Exception as e:
            logger.error(f"Error verificando/creando carpeta de categoría: {e}")
            return {
                "success": False,
                "error": str(e),
                "folder_name": category,
                "storage_type": storage_preference,
            }

    async def _check_s3_folder_exists(self, folder_path: str) -> bool:
        try:

            response = self.s3_service.s3_client.list_objects_v2(
                Bucket=self.s3_service.bucket_name, Prefix=folder_path, MaxKeys=1
            )

            return "Contents" in response and len(response["Contents"]) > 0

        except Exception as e:
            logger.error(f"Error verificando carpeta en S3: {e}")
            return False
