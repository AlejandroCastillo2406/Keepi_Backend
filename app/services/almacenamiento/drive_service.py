import io
from typing import Any, Dict, List, Optional

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload, MediaIoBaseUpload


class GoogleDriveService:

    def __init__(self, credentials: Credentials):
        self.credentials = credentials
        self.service = build("drive", "v3", credentials=credentials)
        self.folders_cache = {}

    async def create_folder(self, name: str, parent_id: Optional[str] = None) -> str:
        try:
            folder_metadata = {
                "name": name,
                "mimeType": "application/vnd.google-apps.folder",
            }

            if parent_id:
                folder_metadata["parents"] = [parent_id]

            folder = (
                self.service.files().create(body=folder_metadata, fields="id").execute()
            )

            folder_id = folder.get("id")
            self.folders_cache[name] = folder_id
            return folder_id

        except HttpError as error:
            print(f"Error creando carpeta: {error}")
            raise

    async def get_or_create_folder(
        self, name: str, parent_id: Optional[str] = None
    ) -> str:

        if name in self.folders_cache:
            return self.folders_cache[name]

        try:

            query = f"name='{name}' and mimeType='application/vnd.google-apps.folder'"
            if parent_id:
                query += f" and '{parent_id}' in parents"

            results = (
                self.service.files()
                .list(q=query, spaces="drive", fields="files(id, name)")
                .execute()
            )

            files = results.get("files", [])

            if files:
                folder_id = files[0]["id"]
                self.folders_cache[name] = folder_id
                return folder_id
            else:

                return await self.create_folder(name, parent_id)

        except HttpError as error:
            print(f"Error buscando/creando carpeta: {error}")
            raise

    async def upload_file(
        self,
        file_path: str,
        file_name: str,
        folder_id: str,
        mime_type: Optional[str] = None,
    ) -> str:
        try:
            if not mime_type:
                mime_type = "application/octet-stream"

            file_metadata = {"name": file_name, "parents": [folder_id]}

            media = MediaFileUpload(file_path, mimetype=mime_type, resumable=True)

            file = (
                self.service.files()
                .create(
                    body=file_metadata,
                    media_body=media,
                    fields="id, name, size, mimeType, createdTime",
                )
                .execute()
            )

            return file.get("id")

        except HttpError as error:
            print(f"Error subiendo archivo: {error}")
            raise

    async def get_folder_structure(
        self, folder_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        try:
            query = "mimeType='application/vnd.google-apps.folder'"
            if folder_id:
                query += f" and '{folder_id}' in parents"
            else:
                query += " and 'root' in parents"

            results = (
                self.service.files()
                .list(
                    q=query,
                    spaces="drive",
                    fields="files(id, name, createdTime, modifiedTime)",
                    orderBy="name",
                )
                .execute()
            )

            folders = []
            for folder in results.get("files", []):
                folders.append(
                    {
                        "id": folder["id"],
                        "name": folder["name"],
                        "created_time": folder.get("createdTime"),
                        "modified_time": folder.get("modifiedTime"),
                    }
                )

            return folders

        except HttpError as error:
            print(f"Error obteniendo estructura de carpetas: {error}")
            raise

    async def get_files_in_folder(self, folder_id: str) -> List[Dict[str, Any]]:
        try:
            results = (
                self.service.files()
                .list(
                    q=f"'{folder_id}' in parents and mimeType!='application/vnd.google-apps.folder'",
                    spaces="drive",
                    fields="files(id, name, size, mimeType, createdTime, modifiedTime)",
                    orderBy="name",
                )
                .execute()
            )

            files = []
            for file in results.get("files", []):
                files.append(
                    {
                        "id": file["id"],
                        "name": file["name"],
                        "size": file.get("size"),
                        "mime_type": file.get("mimeType"),
                        "created_time": file.get("createdTime"),
                        "modified_time": file.get("modifiedTime"),
                    }
                )

            return files

        except HttpError as error:
            print(f"Error obteniendo archivos: {error}")
            raise

    async def delete_file(self, file_id: str) -> bool:
        try:
            self.service.files().delete(fileId=file_id).execute()
            return True
        except HttpError as error:
            print(f"Error eliminando archivo: {error}")
            return False

    async def get_file_download_url(self, file_id: str) -> str:
        try:
            file = (
                self.service.files()
                .get(fileId=file_id, fields="webViewLink, webContentLink")
                .execute()
            )

            return file.get("webContentLink", "")

        except HttpError as error:
            print(f"Error obteniendo URL de descarga: {error}")
            return ""

    async def get_file_view_info(self, file_id: str) -> Dict[str, Any]:
        try:
            file = (
                self.service.files()
                .get(
                    fileId=file_id, fields="name, mimeType, webViewLink, webContentLink"
                )
                .execute()
            )
            return {
                "view_url": file.get("webViewLink") or file.get("webContentLink") or "",
                "download_url": file.get("webContentLink", ""),
                "name": file.get("name", ""),
                "mime_type": file.get("mimeType", ""),
            }
        except HttpError as error:
            print(f"Error obteniendo info de archivo: {error}")
            raise

    async def get_all_files(self) -> List[Dict[str, Any]]:
        try:
            all_files = []
            page_token = None

            while True:
                results = (
                    self.service.files()
                    .list(
                        q="mimeType!='application/vnd.google-apps.folder'",
                        spaces="drive",
                        fields="nextPageToken, files(id, name, size, mimeType, createdTime, modifiedTime, description, parents)",
                        pageToken=page_token,
                        pageSize=1000,
                    )
                    .execute()
                )

                files = results.get("files", [])
                for file in files:
                    all_files.append(
                        {
                            "id": file["id"],
                            "name": file["name"],
                            "size": file.get("size"),
                            "mime_type": file.get("mimeType"),
                            "created_time": file.get("createdTime"),
                            "modified_time": file.get("modifiedTime"),
                            "description": file.get("description", ""),
                            "parents": file.get("parents", []),
                        }
                    )

                page_token = results.get("nextPageToken")
                if not page_token:
                    break

            return all_files

        except HttpError as error:
            print(f"Error obteniendo todos los archivos: {error}")
            return []

    async def download_file(self, file_id: str) -> tuple[bytes, str, str]:
        try:

            file_metadata = (
                self.service.files()
                .get(fileId=file_id, fields="name, mimeType")
                .execute()
            )

            file_name = file_metadata.get("name", "unknown")
            mime_type = file_metadata.get("mimeType", "application/octet-stream")

            request = self.service.files().get_media(fileId=file_id)
            file_content = io.BytesIO()
            downloader = MediaIoBaseDownload(file_content, request)

            done = False
            while done is False:
                status, done = downloader.next_chunk()

            return file_content.getvalue(), file_name, mime_type

        except HttpError as error:
            print(f"Error descargando archivo: {error}")
            raise

    async def move_file_to_folder(self, file_id: str, folder_id: str) -> bool:
        try:

            file = self.service.files().get(fileId=file_id, fields="parents").execute()

            previous_parents = ",".join(file.get("parents", []))

            self.service.files().update(
                fileId=file_id,
                addParents=folder_id,
                removeParents=previous_parents,
                fields="id, parents",
            ).execute()

            return True

        except HttpError as error:
            print(f"Error moviendo archivo: {error}")
            return False

    async def update_file_description(self, file_id: str, description: str) -> bool:
        try:
            self.service.files().update(
                fileId=file_id, body={"description": description}
            ).execute()

            return True

        except HttpError as error:
            print(f"Error actualizando descripción: {error}")
            return False

    async def rename_file(self, file_id: str, new_name: str) -> bool:
        """Renombra el archivo en Google Drive (nombre visible en Drive)."""
        try:
            self.service.files().update(
                fileId=file_id,
                body={"name": new_name},
                fields="id, name",
            ).execute()
            return True
        except HttpError as error:
            print(f"Error renombrando archivo: {error}")
            raise

    async def upload_file(
        self, file_data: bytes, file_name: str, folder_id: str, mime_type: str
    ) -> str:
        try:
            file_metadata = {"name": file_name, "parents": [folder_id]}

            media = MediaIoBaseUpload(
                io.BytesIO(file_data), mimetype=mime_type, resumable=True
            )

            file = (
                self.service.files()
                .create(body=file_metadata, media_body=media, fields="id")
                .execute()
            )

            return file.get("id")

        except HttpError as error:
            print(f"Error subiendo archivo: {error}")
            raise

    async def list_folders(self) -> List[Dict[str, Any]]:
        try:

            query = "mimeType='application/vnd.google-apps.folder' and trashed=false"
            results = (
                self.service.files()
                .list(
                    q=query,
                    fields="nextPageToken, files(id, name, parents, createdTime, modifiedTime)",
                )
                .execute()
            )

            folders = []
            for folder in results.get("files", []):

                doc_count = await self._count_documents_in_folder(folder["id"])

                folders.append(
                    {
                        "id": folder["id"],
                        "name": folder["name"],
                        "document_count": doc_count,
                        "path": (
                            folder.get("parents", [None])[0]
                            if folder.get("parents")
                            else None
                        ),
                        "created_time": folder.get("createdTime"),
                        "modified_time": folder.get("modifiedTime"),
                    }
                )

            return folders

        except HttpError as error:
            print(f"Error listando carpetas: {error}")
            return []

    async def _count_documents_in_folder(self, folder_id: str) -> int:
        try:

            query = f"'{folder_id}' in parents and mimeType!='application/vnd.google-apps.folder' and trashed=false"
            results = self.service.files().list(q=query, fields="files(id)").execute()

            return len(results.get("files", []))

        except HttpError as error:
            print(f"Error contando documentos en carpeta {folder_id}: {error}")
            return 0
