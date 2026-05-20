import logging
import uuid
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.document import DocumentCreate as ModelDocumentCreate
from app.models.document import DocumentResponse as ModelDocumentResponse
from app.models.document import DocumentUpdate as ModelDocumentUpdate

DocumentCreate = ModelDocumentCreate
DocumentResponse = ModelDocumentResponse

from app.services.almacenamiento import FolderService
from app.services.aws import AWSService, DocumentAnalysisService
from app.services.usuarios import UserConfigService

if TYPE_CHECKING:
    from app.interfaces.document_interface import IDocumentRepository
    from app.repositories.folder_repository import FolderRepository

logger = logging.getLogger(__name__)


def _response_from_orm(doc: Document):
    return ModelDocumentResponse.from_orm(doc)


class DocumentService:

    def __init__(
        self,
        db: Session,
        document_repository: "IDocumentRepository",
        folder_repository: "FolderRepository",
    ):
        self.db = db
        self._document_repository = document_repository
        self._folder_repository = folder_repository
        self.aws_service = AWSService()
        self.user_config_service = UserConfigService(self.db)
        self.folder_service = FolderService(self.db)
        self.ai_analysis_service = DocumentAnalysisService()

    def list_documents_by_drive_file_ids(
        self, user_id: str, drive_file_ids: List[str]
    ) -> List[Document]:
        if not drive_file_ids:
            return []
        return self._document_repository.list_for_user_drive_file_ids(
            uuid.UUID(str(user_id)), drive_file_ids
        )

    def list_documents_by_s3_keys(
        self, user_id: str, s3_keys: List[str]
    ) -> List[Document]:
        if not s3_keys:
            return []
        return self._document_repository.list_for_user_s3_keys(
            uuid.UUID(str(user_id)), s3_keys
        )

    def get_document_by_id_any(self, document_id) -> Optional[Document]:
        return self._document_repository.get_by_id_any_user(document_id)

    def persist_document_entity(self, doc: Document) -> Document:
        return self._document_repository.persist(doc)

    async def get_user_documents(self, user_id: str) -> List[ModelDocumentResponse]:
        try:
            documents = self._document_repository.get_by_user_id(user_id)
            return [_response_from_orm(doc) for doc in documents]
        except Exception:
            logger.exception("Error obteniendo documentos")
            return []

    async def get_document_by_id(
        self, document_id: str, user_id: str
    ) -> Optional[ModelDocumentResponse]:
        try:
            document = self._document_repository.get_by_id(document_id, user_id)
            return _response_from_orm(document) if document else None
        except Exception:
            logger.exception("Error obteniendo documento")
            return None

    async def create_document(
        self, user_id: str, document_data: ModelDocumentCreate
    ) -> ModelDocumentResponse:
        try:
            folder_id = None
            drive_folder_id = getattr(document_data, "drive_folder_id", None)
            if drive_folder_id and document_data.category:
                folder = self._folder_repository.get_or_create_for_category_drive(
                    user_id, document_data.category, drive_folder_id
                )
                folder_id = folder.id
            data_to_pass = document_data.model_copy(
                update={"folder_id": str(folder_id) if folder_id else None}
            )
            doc = self._document_repository.create(user_id, data_to_pass)
            return _response_from_orm(doc)
        except Exception:
            logger.exception("Error creando documento")
            self.db.rollback()
            raise

    async def update_document(
        self, document_id: str, user_id: str, document_data: ModelDocumentUpdate
    ) -> Optional[ModelDocumentResponse]:
        try:
            doc = self._document_repository.update(document_id, user_id, document_data)
            return _response_from_orm(doc) if doc else None
        except Exception:
            logger.exception("Error actualizando documento")
            self.db.rollback()
            return None

    async def delete_document(self, document_id: str, user_id: str) -> bool:
        try:
            return self._document_repository.delete(document_id, user_id)
        except Exception:
            logger.exception("Error eliminando documento")
            self.db.rollback()
            return False

    async def get_document_categories(self, user_id: str) -> List[str]:
        try:
            return self._document_repository.list_distinct_categories(user_id)
        except Exception as e:
            print(f"Error obteniendo categorías: {e}")
            return []

    async def get_expiring_documents(
        self, user_id: str, days: int = 30
    ) -> List[DocumentResponse]:
        try:
            cutoff_date = datetime.now() + timedelta(days=days)
            documents = self._document_repository.list_expiring_before(
                user_id, cutoff_date
            )
            return [DocumentResponse.from_orm(doc) for doc in documents]
        except Exception as e:
            print(f"Error obteniendo documentos por vencer: {e}")
            return []

    async def search_documents(
        self, user_id: str, query: str
    ) -> List[DocumentResponse]:
        try:
            documents = self._document_repository.search_by_user_text(user_id, query)
            return [DocumentResponse.from_orm(doc) for doc in documents]
        except Exception as e:
            print(f"Error buscando documentos: {e}")
            return []

    async def process_document_with_bedrock(
        self, user_id: str, file_data: bytes, file_name: str, file_type: str
    ) -> DocumentResponse:
        try:

            user_config = await self.user_config_service.get_user_config(user_id)
            storage_preference = (
                user_config.cloud_provider.value
                if user_config and user_config.cloud_provider
                else "keepi_cloud"
            )

            ai_analysis = await self.ai_analysis_service.analyze_document(
                file_data, file_type, file_name, user_id, self.db
            )

            if ai_analysis.get("suggested_category") == "SUBSCRIPTION_REQUIRED":

                from fastapi import HTTPException

                raise HTTPException(
                    status_code=402,
                    detail={
                        "error": "subscription_required",
                        "message": ai_analysis.get(
                            "subscription_required_message", "Suscripción requerida"
                        ),
                        "subscription_info": ai_analysis.get("subscription_info", {}),
                        "code": "SUBSCRIPTION_REQUIRED",
                    },
                )

            if (
                ai_analysis.get("suggested_category")
                == "MANUAL_CLASSIFICATION_REQUIRED"
            ):

                document_data = DocumentCreate(
                    name=file_name,
                    category="Pendiente de clasificación",
                    file_name=file_name,
                    file_type=file_type,
                    file_size=len(file_data),
                    file_url=None,
                    cloud_provider=storage_preference,
                    s3_key=None,
                    extracted_text=ai_analysis.get("extracted_text", ""),
                    ai_analysis=ai_analysis,
                    expiry_date=ai_analysis.get("expiry_date"),
                    document_number=ai_analysis.get("document_number"),
                    organization=ai_analysis.get("organization"),
                )

                return await self.create_document(user_id, document_data)

            category = ai_analysis.get("suggested_category", "Documento")
            expiry_date = ai_analysis.get("expiry_date")
            confidence = ai_analysis.get("confidence_score", 0.5)

            folder_result = await self.folder_service.ensure_category_folder_exists(
                user_id, category, storage_preference
            )

            if not folder_result.get("success"):

                if folder_result.get("requires_drive_auth"):
                    from app.exceptions import DriveAuthRequiredException

                    raise DriveAuthRequiredException(
                        message=folder_result.get(
                            "error", "Se requiere autorización de Google Drive"
                        ),
                        drive_auth_url=folder_result.get("drive_auth_url", ""),
                    )
                else:
                    logger.warning(
                        "Error creando carpeta de categoría: %s",
                        folder_result.get("error"),
                    )

            file_url = None
            s3_key = None
            drive_file_id = None
            drive_folder_id = None

            if storage_preference == "keepi_cloud":

                folder_name = folder_result.get("folder_name", category)
                folder_path = f"users/{user_id}/{folder_name}/"

                file_url = await self.aws_service.upload_to_s3_with_folder(
                    file_data, file_name, user_id, folder_name
                )
                s3_key = f"{folder_path}{file_name}"

            elif storage_preference == "google_drive":

                from app.services.almacenamiento import GoogleDriveService
                from app.services.autenticacion import GoogleOAuthService

                oauth_service = GoogleOAuthService(self.db)
                user_credentials = await oauth_service.refresh_user_tokens(user_id)

                if not user_credentials:
                    from fastapi import HTTPException

                    raise HTTPException(
                        status_code=401,
                        detail="Usuario no ha autorizado acceso a Google Drive. Use /api/v1/auth/google/authorize primero.",
                    )

                drive_service = GoogleDriveService(user_credentials)
                drive_folder_id = folder_result.get("folder_id")

                if not drive_folder_id:

                    logger.warning(
                        "No se obtuvo folder_id para categoría '%s', creando carpeta",
                        category,
                    )
                    folder_creation = await self.folder_service.create_category_folder(
                        user_id, category, storage_preference
                    )
                    drive_folder_id = folder_creation.get("folder_id")

                    if not drive_folder_id:
                        logger.warning(
                            "No se pudo crear carpeta para '%s', usando General como fallback",
                            category,
                        )
                        drive_folder_id = await drive_service.get_or_create_folder(
                            "General"
                        )
                        category = "General"

                logger.info(
                    "Subiendo archivo '%s' a carpeta '%s' (ID: %s)",
                    file_name,
                    category,
                    drive_folder_id,
                )
                drive_file_id = await drive_service.upload_file(
                    file_data, file_name, drive_folder_id, file_type
                )
                logger.info(
                    "Archivo subido a Google Drive (File ID: %s)", drive_file_id
                )

                file_url = await drive_service.get_file_download_url(drive_file_id)
                if not file_url:

                    file_url = f"https://drive.google.com/file/d/{drive_file_id}/view"

                s3_key = f"drive/{drive_folder_id}/{drive_file_id}"

            document_data = DocumentCreate(
                name=file_name,
                category=category,
                file_name=file_name,
                file_type=file_type,
                file_size=len(file_data),
                file_url=file_url,
                cloud_provider=storage_preference,
                s3_key=s3_key,
                extracted_text=ai_analysis.get("extracted_text", ""),
                ai_analysis=ai_analysis,
                expiry_date=expiry_date,
                document_number=ai_analysis.get("document_number"),
                organization=ai_analysis.get("organization"),
                tags=ai_analysis.get("tags", []),
                drive_file_id=drive_file_id,
                drive_folder_id=drive_folder_id,
            )

            return await self.create_document(user_id, document_data)

        except Exception as e:
            print(f"Error procesando documento con Bedrock: {e}")
            raise

    async def _get_existing_folder_names(self, user_id: str) -> List[str]:
        try:
            from app.models.user_config import CloudProvider
            from app.services.almacenamiento import GoogleDriveService
            from app.services.autenticacion import GoogleOAuthService

            user_config = await self.user_config_service.get_user_config(user_id)
            if (
                not user_config
                or user_config.cloud_provider != CloudProvider.GOOGLE_DRIVE
            ):
                return []
            oauth = GoogleOAuthService(self.db)
            credentials = await oauth.refresh_user_tokens(user_id)
            if not credentials:
                return []
            drive = GoogleDriveService(credentials)
            folders = await drive.get_folder_structure()
            return [f["name"] for f in folders if f.get("name")]
        except Exception as e:
            logger.warning(
                "No se pudieron listar carpetas existentes para análisis: %s", e
            )
            return []

    async def analyze_document_only(
        self, user_id: str, file_data: bytes, file_name: str, file_type: str
    ) -> Dict[str, Any]:
        import re

        logger.info(
            "analyze_document_only: usuario=%s, archivo=%s, tamaño=%s bytes",
            user_id,
            file_name,
            len(file_data),
        )
        existing_folders = await self._get_existing_folder_names(user_id)
        ai_analysis = await self.ai_analysis_service.analyze_document(
            file_data,
            file_type,
            file_name,
            user_id,
            self.db,
            existing_category_names=existing_folders,
        )
        if ai_analysis.get("suggested_category") == "SUBSCRIPTION_REQUIRED":
            return {
                "subscription_required": True,
                "message": ai_analysis.get(
                    "subscription_required_message", "Suscripción requerida"
                ),
                "subscription_info": ai_analysis.get("subscription_info", {}),
            }
        if ai_analysis.get("suggested_category") == "MANUAL_CLASSIFICATION_REQUIRED":
            return {
                "manual_classification_required": True,
                "message": ai_analysis.get(
                    "manual_classification_message", "Clasificación manual"
                ),
                "category": "Pendiente de clasificación",
                "recommended_name": file_name,
                "expiry_date": None,
                "tags": ai_analysis.get("tags", []),
                "confidence_score": 0,
            }
        category = ai_analysis.get("suggested_category", "Documento")
        recommended_name = ai_analysis.get("recommended_name")
        if not recommended_name or not recommended_name.strip():
            safe_cat = re.sub(r"[^\w\s\-]", "", category).strip().replace(" ", "_")[:40]
            base = file_name.rsplit(".", 1)[0] if "." in file_name else file_name
            ext = file_name.rsplit(".", 1)[-1] if "." in file_name else ""
            recommended_name = (
                f"{safe_cat}_{base}.{ext}" if ext else f"{safe_cat}_{base}"
            )
        else:
            recommended_name = recommended_name.strip()
        return {
            "category": category,
            "recommended_name": recommended_name,
            "expiry_date": ai_analysis.get("expiry_date"),
            "tags": ai_analysis.get("tags", []),
            "confidence_score": ai_analysis.get("confidence_score", 0.5),
            "manual_classification_required": False,
            "subscription_required": False,
            "subscription_info": ai_analysis.get("subscription_info"),
        }

    async def mark_document_replaced(
        self,
        user_id: str,
        old_document_id: str,
        new_document_id: str,
    ) -> None:
        from datetime import timezone

        old = self._document_repository.get_by_id(old_document_id, user_id)
        if not old:
            raise ValueError("Documento a reemplazar no encontrado")
        ai = dict(old.ai_analysis) if isinstance(old.ai_analysis, dict) else {}
        if ai.get("replaced") is True:
            raise ValueError("Este documento ya fue marcado como reemplazado")
        ai["replaced"] = True
        ai["replaced_at"] = datetime.now(timezone.utc).isoformat()
        ai["replaced_by_document_id"] = str(new_document_id)
        note = "[Documento reemplazado]"
        description = old.description or ""
        if note not in description:
            description = f"{description}\n{note}".strip() if description else note
        await self.update_document(
            old_document_id,
            user_id,
            ModelDocumentUpdate(
                ai_analysis=ai,
                description=description,
            ),
        )
        new_doc = self._document_repository.get_by_id(new_document_id, user_id)
        if new_doc:
            self._notify_document_replaced(user_id, old, new_doc)

    def _notify_document_replaced(
        self, user_id: str, old_doc: Document, new_doc: Document
    ) -> None:
        from app.services.notificaciones import notify_user_push_and_db

        old_name = (
            getattr(old_doc, "name", None)
            or getattr(old_doc, "file_name", None)
            or "Documento"
        )
        new_name = (
            getattr(new_doc, "name", None)
            or getattr(new_doc, "file_name", None)
            or "Documento"
        )
        old_cat = getattr(old_doc, "category", None) or ""
        new_cat = getattr(new_doc, "category", None) or ""
        message = f"«{old_name}» fue reemplazado por «{new_name}»."
        payload = {
            "type": "document_replaced",
            "old_document_id": str(old_doc.id),
            "new_document_id": str(new_doc.id),
            "old_document_name": old_name,
            "new_document_name": new_name,
            "old_category": old_cat,
            "new_category": new_cat,
        }
        push_data = {k: str(v) for k, v in payload.items()}
        try:
            notify_user_push_and_db(
                self.db,
                user_id,
                title="Documento reemplazado",
                message=message,
                notification_type="document_replaced",
                payload=payload,
                document_id=str(new_doc.id),
                push_data=push_data,
            )
        except Exception:
            logger.exception(
                "No se pudo enviar notificación de reemplazo user=%s old=%s new=%s",
                user_id,
                old_doc.id,
                new_doc.id,
            )

    async def save_analyzed_document(
        self,
        user_id: str,
        file_data: bytes,
        file_name: str,
        file_type: str,
        category: str,
        save_as_name: str,
        expiry_date: Optional[datetime] = None,
        document_number: Optional[str] = None,
        organization: Optional[str] = None,
        tags: Optional[List[str]] = None,
        replaces_document_id: Optional[str] = None,
    ) -> ModelDocumentResponse:
        category = category.strip().title() if category else category
        user_config = await self.user_config_service.get_user_config(user_id)
        storage_preference = (
            user_config.cloud_provider.value
            if user_config and user_config.cloud_provider
            else "keepi_cloud"
        )
        folder_result = await self.folder_service.ensure_category_folder_exists(
            user_id, category, storage_preference
        )
        if not folder_result.get("success"):
            if folder_result.get("requires_drive_auth"):
                from app.exceptions import DriveAuthRequiredException

                raise DriveAuthRequiredException(
                    message=folder_result.get(
                        "error", "Se requiere autorización de Google Drive"
                    ),
                    drive_auth_url=folder_result.get("drive_auth_url", ""),
                )
            raise ValueError(
                folder_result.get("error", "No se pudo crear o acceder a la carpeta")
            )
        file_url = None
        s3_key = None
        drive_file_id = None
        drive_folder_id = None
        if storage_preference == "keepi_cloud":
            folder_name = folder_result.get("folder_name", category)
            file_url = await self.aws_service.upload_to_s3_with_folder(
                file_data, save_as_name, user_id, folder_name
            )
            s3_key = f"users/{user_id}/{folder_name}/{save_as_name}"
        elif storage_preference == "google_drive":
            from app.services.almacenamiento import GoogleDriveService
            from app.services.autenticacion import GoogleOAuthService

            oauth_service = GoogleOAuthService(self.db)
            user_credentials = await oauth_service.refresh_user_tokens(user_id)
            if not user_credentials:
                raise ValueError("Usuario no ha autorizado acceso a Google Drive")
            drive_service = GoogleDriveService(user_credentials)
            drive_folder_id = folder_result.get("folder_id")
            if not drive_folder_id:
                folder_creation = await self.folder_service.create_category_folder(
                    user_id, category, storage_preference
                )
                drive_folder_id = folder_creation.get("folder_id")
                if not drive_folder_id:
                    drive_folder_id = await drive_service.get_or_create_folder(
                        "General"
                    )
            drive_file_id = await drive_service.upload_file(
                file_data, save_as_name, drive_folder_id, file_type
            )
            file_url = f"https://drive.google.com/file/d/{drive_file_id}/view"
            s3_key = f"drive/{drive_folder_id}/{drive_file_id}"
        ai_analysis: dict = {
            "keepi_classified": True,
        }
        if replaces_document_id:
            old = self._document_repository.get_by_id(replaces_document_id, user_id)
            if not old:
                raise ValueError("Documento a reemplazar no encontrado")
            old_ai = (
                dict(old.ai_analysis) if isinstance(old.ai_analysis, dict) else {}
            )
            if old_ai.get("replaced") is True:
                raise ValueError("Este documento ya fue marcado como reemplazado")
            expiry = getattr(old, "expiry_date", None)
            if expiry is None:
                raise ValueError(
                    "Solo se pueden reemplazar documentos con fecha de vencimiento"
                )
            ai_analysis["replaces_document_id"] = str(replaces_document_id)

        document_data = DocumentCreate(
            name=save_as_name,
            category=category,
            description="Documento clasificado y guardado con Keepi",
            file_url=file_url,
            file_name=save_as_name,
            file_size=len(file_data),
            file_type=file_type,
            expiry_date=expiry_date,
            cloud_provider=storage_preference,
            s3_key=s3_key,
            ai_analysis=ai_analysis,
            tags=tags or [],
            drive_file_id=drive_file_id,
            drive_folder_id=drive_folder_id,
        )
        created = await self.create_document(user_id, document_data)
        if replaces_document_id:
            await self.mark_document_replaced(
                user_id, replaces_document_id, str(created.id)
            )
        return created

    async def process_document_with_aws(
        self, user_id: str, file_data: bytes, file_name: str, file_type: str
    ) -> DocumentResponse:
        try:

            user_config = await self.user_config_service.get_user_config(user_id)
            cloud_provider = (
                user_config.cloud_provider if user_config else "google_drive"
            )

            file_url = None
            s3_key = None

            if cloud_provider == "keepi_cloud":

                await self.aws_service.create_user_folders(user_id)

                file_url = await self.aws_service.upload_to_s3_temp(
                    file_data, file_name, user_id
                )
                s3_key = f"users/{user_id}/temp/{file_name}"

            extraction_result = await self.aws_service.extract_text_from_document(
                file_data, file_name, file_type
            )
            extracted_text = extraction_result.get("text", "")

            ai_analysis = None
            category = "General"

            logger.debug("Texto extraído: %d caracteres", len(extracted_text))
            if extracted_text and len(extracted_text.strip()) > 10:
                try:

                    comprehend_result = await self.aws_service.categorize_document(
                        extracted_text
                    )
                    logger.debug(
                        "Comprehend categoría: %s",
                        comprehend_result.get("category", "N/A"),
                    )
                    ai_analysis = {
                        "extraction": extraction_result,
                        "comprehend": comprehend_result,
                    }

                    category = comprehend_result.get("category", "General")

                    if cloud_provider == "keepi_cloud":

                        category_folder = await self.aws_service.create_category_folder(
                            user_id, category
                        )

                        new_file_url = await self.aws_service.move_file_in_s3(
                            user_id,
                            file_name,
                            "temp",
                            f"categorias/{self.aws_service._sanitize_folder_name(category)}",
                        )

                        file_url = new_file_url
                        s3_key = f"users/{user_id}/categorias/{self.aws_service._sanitize_folder_name(category)}/{file_name}"

                except Exception as e:
                    logger.warning("Error en categorización: %s", e)
                    ai_analysis = {
                        "extraction": extraction_result,
                        "comprehend_error": str(e),
                    }
            else:
                ai_analysis = {
                    "extraction": extraction_result,
                    "no_text_to_analyze": True,
                }

                if cloud_provider == "keepi_cloud":
                    category_folder = await self.aws_service.create_category_folder(
                        user_id, "General"
                    )
                    new_file_url = await self.aws_service.move_file_in_s3(
                        user_id, file_name, "temp", "categorias/General"
                    )
                    file_url = new_file_url
                    s3_key = f"users/{user_id}/categorias/General/{file_name}"

            document_data = DocumentCreate(
                name=file_name,
                category=category,
                file_name=file_name,
                file_type=file_type,
                file_size=len(file_data),
                file_url=file_url,
                cloud_provider=cloud_provider,
                s3_key=s3_key,
                extracted_text=extracted_text,
                ai_analysis=ai_analysis,
            )

            return await self.create_document(user_id, document_data)

        except Exception:
            logger.exception("Error procesando documento con AWS")
            raise

    async def upload_patient_clinical_study(
        self,
        user_id: str,
        *,
        filename: str,
        mime_type: str,
        content: bytes,
        category: str = "Análisis Clínicos",
        description: str = "Subido desde la solicitud del doctor",
    ) -> Document:
        import io

        from app.services.almacenamiento import GoogleDriveService, S3Service
        from app.services.autenticacion import GoogleOAuthService

        uid = str(user_id)
        user_config = await self.user_config_service.get_or_create_user_config(uid)
        cloud_provider = (
            user_config.cloud_provider.value
            if user_config and user_config.cloud_provider
            else "google_drive"
        )
        folder_result = await self.folder_service.ensure_category_folder_exists(
            uid, category, cloud_provider
        )
        if not folder_result.get("success"):
            err = folder_result.get(
                "error", "No se pudo preparar la carpeta de destino"
            )
            if folder_result.get("requires_drive_auth"):
                raise ValueError(
                    f"DRIVE_AUTH|{folder_result.get('drive_auth_url', '')}|{err}"
                )
            raise ValueError(err)

        drive_file_id = None
        s3_key = None
        file_url = None

        if cloud_provider == "google_drive":
            oauth_service = GoogleOAuthService(self.db)
            credentials = await oauth_service.refresh_user_tokens(uid)
            if not credentials:
                raise ValueError("GOOGLE_UNAUTHORIZED")
            drive_folder_id = folder_result.get("folder_id")
            if not drive_folder_id:
                raise RuntimeError("No se obtuvo carpeta en Google Drive")
            drive_service = GoogleDriveService(credentials)
            drive_file_id = await drive_service.upload_file(
                content, filename, drive_folder_id, mime_type
            )
            if drive_file_id:
                file_url = f"https://drive.google.com/file/d/{drive_file_id}/view"
        else:
            s3_service = S3Service()
            folder_name = folder_result.get("folder_name") or "other"
            upload_res = await s3_service.upload_document(
                uid,
                io.BytesIO(content),
                filename,
                mime_type,
                folder=folder_name,
            )
            s3_key = upload_res.get("file_path")
            file_url = upload_res.get("signed_url")

        document = Document(
            id=uuid.uuid4(),
            user_id=uuid.UUID(uid),
            name=filename,
            category=category,
            description=description,
            file_url=file_url,
            file_name=filename,
            file_size=len(content),
            file_type=mime_type.split("/")[0],
            cloud_provider=cloud_provider,
            drive_file_id=drive_file_id,
            s3_key=s3_key,
        )
        try:
            return self.persist_document_entity(document)
        except Exception:
            self.db.rollback()
            raise
