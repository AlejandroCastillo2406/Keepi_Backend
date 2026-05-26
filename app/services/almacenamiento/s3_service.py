import logging
import re
import unicodedata
import uuid
from datetime import datetime
from typing import Any, BinaryIO, Dict, List

import boto3
from botocore.exceptions import ClientError

from app.core.config import settings

logger = logging.getLogger(__name__)


class S3Service:
    def __init__(self):
        self.s3_client = boto3.client("s3")
        self.bucket_name = (
            settings.aws_s3_bucket or "keepi-bucket"
        ).strip() or "keepi-bucket"

    async def ensure_bucket_exists(self) -> bool:
        try:

            try:
                self.s3_client.head_bucket(Bucket=self.bucket_name)
                logger.info(f"Bucket '{self.bucket_name}' ya existe")
                return True
            except ClientError as e:
                error_code = e.response["Error"]["Code"]
                if error_code == "404":
                    logger.info(f"Bucket '{self.bucket_name}' no existe, creándolo...")
                elif error_code == "403":
                    logger.error(
                        f"No tienes permisos para acceder al bucket '{self.bucket_name}'"
                    )
                    raise
                else:
                    logger.error(f"Error verificando bucket: {e}")
                    raise

            region = "us-east-1"
            if region == "us-east-1":

                self.s3_client.create_bucket(Bucket=self.bucket_name)
            else:

                self.s3_client.create_bucket(
                    Bucket=self.bucket_name,
                    CreateBucketConfiguration={"LocationConstraint": region},
                )

            logger.info(f"Bucket '{self.bucket_name}' creado exitosamente")

            cors_configuration = {
                "CORSRules": [
                    {
                        "AllowedHeaders": ["*"],
                        "AllowedMethods": ["GET", "PUT", "POST", "DELETE"],
                        "AllowedOrigins": ["*"],
                        "ExposeHeaders": ["ETag"],
                        "MaxAgeSeconds": 3000,
                    }
                ]
            }

            self.s3_client.put_bucket_cors(
                Bucket=self.bucket_name, CORSConfiguration=cors_configuration
            )
            logger.info(f"Configuración CORS aplicada al bucket '{self.bucket_name}'")

            return True

        except Exception as e:
            logger.error(f"Error asegurando que el bucket existe: {str(e)}")
            raise

    async def create_user_folder(self, user_id: str) -> Dict[str, Any]:
        try:
            folder_path = f"users/{user_id}/"

            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=folder_path,
                Body=b"",
                Metadata={
                    "user_id": user_id,
                    "created_at": datetime.utcnow().isoformat(),
                    "type": "folder",
                },
            )

            return {
                "success": True,
                "folder_path": folder_path,
                "message": "Carpeta de usuario creada exitosamente",
            }

        except Exception as e:
            logger.error(f"Error creando carpeta de usuario: {str(e)}")
            raise

    async def upload_document(
        self,
        user_id: str,
        file_data: BinaryIO,
        filename: str,
        content_type: str,
        folder: str = None,
    ) -> Dict[str, Any]:
        try:

            file_extension = filename.split(".")[-1] if "." in filename else ""
            unique_filename = f"{uuid.uuid4()}.{file_extension}"

            if not folder:

                folder = "other"

            if not folder.endswith("/"):
                folder += "/"

            await self._ensure_category_folder_exists(user_id, folder)

            file_path = f"users/{user_id}/{folder}{unique_filename}"

            file_content = file_data.read()
            file_size = len(file_content)

            original_filename_ascii = self._to_ascii_safe(filename)
            folder_ascii = (
                self._to_ascii_safe(folder.rstrip("/")) if folder else "other"
            )

            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=file_path,
                Body=file_content,
                ContentType=content_type,
                Metadata={
                    "user_id": user_id,
                    "original_filename": original_filename_ascii,
                    "uploaded_at": datetime.utcnow().isoformat(),
                    "folder": folder_ascii,
                },
            )

            signed_url = self._generate_signed_url(file_path, expiration=3600)

            return {
                "success": True,
                "file_path": file_path,
                "filename": unique_filename,
                "original_filename": filename,
                "signed_url": signed_url,
                "folder": folder,
                "size": file_size,
            }

        except Exception as e:
            logger.error(f"Error subiendo documento: {str(e)}")
            raise

    async def download_document(self, user_id: str, file_path: str) -> Dict[str, Any]:
        try:

            if not file_path.startswith(f"users/{user_id}/"):
                raise ValueError("No tienes permisos para acceder a este archivo")

            signed_url = self._generate_signed_url(file_path, expiration=3600)

            response = self.s3_client.head_object(
                Bucket=self.bucket_name, Key=file_path
            )

            return {
                "success": True,
                "signed_url": signed_url,
                "filename": response["Metadata"].get(
                    "original_filename", file_path.split("/")[-1]
                ),
                "content_type": response["ContentType"],
                "size": response["ContentLength"],
                "last_modified": response["LastModified"].isoformat(),
            }

        except Exception as e:
            logger.error(f"Error descargando documento: {str(e)}")
            raise

    async def delete_document(self, user_id: str, file_path: str) -> Dict[str, Any]:
        try:

            if not file_path.startswith(f"users/{user_id}/"):
                raise ValueError("No tienes permisos para eliminar este archivo")

            self.s3_client.delete_object(Bucket=self.bucket_name, Key=file_path)

            return {"success": True, "message": "Documento eliminado exitosamente"}

        except Exception as e:
            logger.error(f"Error eliminando documento: {str(e)}")
            raise

    async def list_user_documents(
        self, user_id: str, folder: str = None
    ) -> List[Dict[str, Any]]:
        try:
            prefix = f"users/{user_id}/"
            if folder:
                prefix += f"{folder}/"

            documents = []
            folders = []
            continuation_token = None

            while True:
                kwargs = {
                    "Bucket": self.bucket_name,
                    "Prefix": prefix,
                    "Delimiter": "/",
                }
                if continuation_token:
                    kwargs["ContinuationToken"] = continuation_token
                response = self.s3_client.list_objects_v2(**kwargs)

                for obj in response.get("Contents", []):
                    if obj["Key"].endswith("/"):
                        continue
                    filename = obj["Key"].split("/")[-1]
                    size = obj.get("Size", 0)
                    try:
                        metadata_response = self.s3_client.head_object(
                            Bucket=self.bucket_name, Key=obj["Key"]
                        )
                        meta = metadata_response.get("Metadata") or {}
                        documents.append(
                            {
                                "file_path": obj["Key"],
                                "filename": meta.get("original_filename", filename),
                                "size": size,
                                "last_modified": (
                                    obj.get("LastModified").isoformat()
                                    if obj.get("LastModified")
                                    else ""
                                ),
                                "content_type": metadata_response.get(
                                    "ContentType", ""
                                ),
                                "folder": meta.get("folder", "other"),
                            }
                        )
                    except Exception as head_err:
                        logger.warning(
                            "head_object falló para %s: %s", obj["Key"], head_err
                        )
                        documents.append(
                            {
                                "file_path": obj["Key"],
                                "filename": filename,
                                "size": size,
                                "last_modified": (
                                    obj.get("LastModified").isoformat()
                                    if obj.get("LastModified")
                                    else ""
                                ),
                                "content_type": "",
                                "folder": "other",
                            }
                        )

                for prefix_obj in response.get("CommonPrefixes", []):
                    folder_name = prefix_obj["Prefix"].rstrip("/").split("/")[-1]
                    folders.append({"name": folder_name, "path": prefix_obj["Prefix"]})

                continuation_token = response.get("NextContinuationToken")
                if not continuation_token:
                    break

            return {"documents": documents, "folders": folders}

        except Exception as e:
            logger.error(f"Error listando documentos: {str(e)}")
            raise

    async def create_folder(
        self, user_id: str, folder_name: str, parent_folder: str = None
    ) -> Dict[str, Any]:
        try:

            sanitized_folder_name = self._sanitize_folder_name(folder_name)

            folder_name_ascii = self._to_ascii_safe(folder_name)

            if parent_folder:

                sanitized_parent = self._sanitize_folder_name(parent_folder)
                folder_path = (
                    f"users/{user_id}/{sanitized_parent}/{sanitized_folder_name}/"
                )
            else:
                folder_path = f"users/{user_id}/{sanitized_folder_name}/"

            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=folder_path,
                Body=b"",
                Metadata={
                    "user_id": user_id,
                    "created_at": datetime.utcnow().isoformat(),
                    "type": "folder",
                    "parent_folder": (
                        self._to_ascii_safe(parent_folder) if parent_folder else "root"
                    ),
                    "folder_name": folder_name_ascii,
                },
            )

            return {
                "success": True,
                "folder_path": folder_path,
                "folder_name": sanitized_folder_name,
                "message": "Carpeta creada exitosamente",
            }

        except Exception as e:
            logger.error(f"Error creando carpeta: {str(e)}")
            raise

    async def rename_object(
        self, user_id: str, file_path: str, new_filename: str
    ) -> str:
        """Renombra el objeto S3 (misma carpeta, nuevo nombre de archivo)."""
        try:
            if not file_path.startswith(f"users/{user_id}/"):
                raise ValueError("No tienes permisos para renombrar este archivo")
            new_filename = (new_filename or "").strip()
            if not new_filename:
                raise ValueError("El nombre de archivo no puede estar vacío")
            if "/" in new_filename:
                raise ValueError("El nombre no puede contener barras")

            if "/" not in file_path:
                raise ValueError("Ruta de archivo inválida")

            directory, current_name = file_path.rsplit("/", 1)
            if new_filename == current_name:
                return file_path

            new_file_path = f"{directory}/{new_filename}"
            copy_source = {"Bucket": self.bucket_name, "Key": file_path}
            self.s3_client.copy_object(
                CopySource=copy_source,
                Bucket=self.bucket_name,
                Key=new_file_path,
            )
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=file_path)
            return new_file_path
        except Exception as e:
            logger.error(f"Error renombrando objeto S3: {str(e)}")
            raise

    async def move_document(
        self, user_id: str, file_path: str, new_folder: str
    ) -> Dict[str, Any]:
        try:

            if not file_path.startswith(f"users/{user_id}/"):
                raise ValueError("No tienes permisos para mover este archivo")

            filename = file_path.split("/")[-1]
            new_file_path = f"users/{user_id}/{new_folder}/{filename}"

            copy_source = {"Bucket": self.bucket_name, "Key": file_path}

            self.s3_client.copy_object(
                CopySource=copy_source, Bucket=self.bucket_name, Key=new_file_path
            )

            self.s3_client.delete_object(Bucket=self.bucket_name, Key=file_path)

            return {
                "success": True,
                "new_file_path": new_file_path,
                "message": "Documento movido exitosamente",
            }

        except Exception as e:
            logger.error(f"Error moviendo documento: {str(e)}")
            raise

    def _generate_signed_url(self, file_path: str, expiration: int = 3600) -> str:
        try:
            signed_url = self.s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket_name, "Key": file_path},
                ExpiresIn=expiration,
            )
            return signed_url

        except Exception as e:
            logger.error(f"Error generando URL firmada: {str(e)}")
            raise

    async def get_file_url(self, file_path: str, expiration: int = 3600) -> str:
        try:
            if not file_path:
                raise ValueError("Ruta de archivo inválida")
            self.s3_client.head_object(Bucket=self.bucket_name, Key=file_path)
            return self._generate_signed_url(file_path, expiration=expiration)
        except Exception as e:
            logger.error(f"Error obteniendo URL de archivo S3: {str(e)}")
            raise

    def get_file_bytes(self, file_path: str) -> tuple[bytes, str, str]:
        """Descarga el objeto S3 y devuelve (contenido, content_type, nombre_archivo)."""
        if not file_path:
            raise ValueError("Ruta de archivo inválida")
        response = self.s3_client.get_object(Bucket=self.bucket_name, Key=file_path)
        body = response["Body"].read()
        content_type = response.get("ContentType") or "application/octet-stream"
        meta = response.get("Metadata") or {}
        filename = meta.get("original_filename") or file_path.split("/")[-1]
        return body, content_type, filename

    async def _ensure_category_folder_exists(
        self, user_id: str, folder_name: str
    ) -> None:
        try:
            folder_path = f"users/{user_id}/{folder_name}"

            try:
                self.s3_client.head_object(Bucket=self.bucket_name, Key=folder_path)
                logger.info(
                    f"Carpeta de categoría '{folder_name}' ya existe para usuario {user_id}"
                )
                return
            except ClientError as e:
                if e.response["Error"]["Code"] == "404":

                    logger.info(
                        f"Creando carpeta de categoría '{folder_name}' para usuario {user_id}"
                    )
                else:
                    raise

            category_ascii = self._to_ascii_safe(folder_name.rstrip("/"))

            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=folder_path,
                Body=b"",
                Metadata={
                    "user_id": user_id,
                    "created_at": datetime.utcnow().isoformat(),
                    "type": "category_folder",
                    "category": category_ascii,
                },
            )

            logger.info(
                f"Carpeta de categoría '{folder_name}' creada exitosamente para usuario {user_id}"
            )

        except Exception as e:
            logger.error(
                f"Error asegurando que la carpeta de categoría existe: {str(e)}"
            )
            raise

    def _to_ascii_safe(self, text: str) -> str:
        try:

            normalized = unicodedata.normalize("NFD", text)

            ascii_text = normalized.encode("ascii", "ignore").decode("ascii")

            if not ascii_text.strip():

                ascii_text = re.sub(r"[^a-zA-Z0-9\-_\s]", "", text)
                ascii_text = re.sub(r"\s+", "_", ascii_text.strip())

            ascii_text = re.sub(r"\s+", " ", ascii_text.strip())
            return ascii_text[:100] if len(ascii_text) > 100 else ascii_text
        except Exception as e:
            logger.warning(
                f"Error convirtiendo a ASCII, usando versión sanitizada: {e}"
            )

            sanitized = re.sub(r"[^a-zA-Z0-9\-_\s]", "", text)
            return re.sub(r"\s+", "_", sanitized.strip())[:100]

    def _sanitize_folder_name(self, folder_name: str) -> str:
        try:

            normalized = unicodedata.normalize("NFD", folder_name)

            ascii_name = normalized.encode("ascii", "ignore").decode("ascii")

            if not ascii_name.strip():
                ascii_name = folder_name

            sanitized = re.sub(r"[^a-zA-Z0-9\-_]", "_", ascii_name)

            return sanitized[:50]
        except Exception as e:
            logger.warning(
                f"Error sanitizando nombre de carpeta, usando versión básica: {e}"
            )

            sanitized = re.sub(r"[^a-zA-Z0-9\-_]", "_", folder_name)
            return sanitized[:50]

    def _determine_folder_by_type(self, content_type: str) -> str:
        if content_type.startswith("image/"):
            return "images/"
        elif content_type == "application/pdf":
            return "pdfs/"
        elif "contract" in content_type or "agreement" in content_type:
            return "contracts/"
        elif "invoice" in content_type or "bill" in content_type:
            return "invoices/"
        elif "certificate" in content_type or "diploma" in content_type:
            return "certificates/"
        else:
            return "other/"

    async def get_storage_usage(self, user_id: str) -> Dict[str, Any]:
        try:
            prefix = f"users/{user_id}/"

            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name, Prefix=prefix
            )

            total_size = 0
            file_count = 0

            for obj in response.get("Contents", []):
                if not obj["Key"].endswith("/"):
                    total_size += obj["Size"]
                    file_count += 1

            return {
                "total_size_bytes": total_size,
                "total_size_mb": round(total_size / (1024 * 1024), 2),
                "file_count": file_count,
                "storage_limit_mb": 1000,
                "usage_percentage": round((total_size / (1024 * 1024 * 1024)) * 100, 2),
            }

        except Exception as e:
            logger.error(f"Error obteniendo uso de almacenamiento: {str(e)}")
            raise

    async def list_folders(self, prefix: str = "") -> List[Dict[str, Any]]:
        try:
            folders = []
            paginator = self.s3_client.get_paginator("list_objects_v2")

            await self.ensure_bucket_exists()

            page_iterator = paginator.paginate(
                Bucket=self.bucket_name, Prefix=prefix, Delimiter="/"
            )

            for page in page_iterator:

                if "CommonPrefixes" in page:
                    for folder in page["CommonPrefixes"]:
                        folder_name = folder["Prefix"]
                        if folder_name.endswith("/"):
                            folder_name = folder_name[:-1]

                        doc_count = await self._count_documents_in_folder(
                            folder["Prefix"]
                        )

                        folders.append(
                            {
                                "name": folder_name,
                                "document_count": doc_count,
                                "path": folder["Prefix"],
                            }
                        )

            return folders

        except Exception as e:
            logger.error(f"Error listando carpetas: {str(e)}")
            return []

    async def _count_documents_in_folder(self, folder_prefix: str) -> int:
        try:
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name, Prefix=folder_prefix, MaxKeys=1000
            )

            files = [
                obj
                for obj in response.get("Contents", [])
                if not obj["Key"].endswith("/")
            ]

            return len(files)

        except Exception as e:
            logger.error(
                f"Error contando documentos en carpeta {folder_prefix}: {str(e)}"
            )
            return 0
