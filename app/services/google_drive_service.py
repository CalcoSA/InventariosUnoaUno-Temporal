import io
from googleapiclient.http import MediaIoBaseUpload
from app.constants import MIME_XLSX
from app.errors import FunctionalError
from app.services.google_request import execute


class GoogleDriveService:
    def __init__(self, auth):
        self.auth = auth

    def api(self):
        return self.auth.api('drive', 'v3').files()

    def metadata(self, file_id):
        return execute(self.api().get(fileId=file_id, fields='id,name,mimeType,parents,webViewLink', supportsAllDrives=True))

    def parent(self, file_id):
        parents = self.metadata(file_id).get('parents', [])
        if not parents:
            raise FunctionalError('No se encontró la carpeta de los formatos.')
        return parents[0]

    def list_files(self, folder):
        token = None
        while True:
            result = execute(self.api().list(q=f"'{folder}' in parents and trashed = false", fields='nextPageToken,files(id,name,mimeType)',
                pageToken=token, pageSize=1000, supportsAllDrives=True, includeItemsFromAllDrives=True))
            yield from result.get('files', [])
            token = result.get('nextPageToken')
            if not token:
                break

    def convert_xlsx(self, file_id, name, folder):
        content = execute(self.api().get_media(fileId=file_id, supportsAllDrives=True))
        media = MediaIoBaseUpload(io.BytesIO(content), mimetype=MIME_XLSX, resumable=False)
        return execute(self.api().create(body={'name': name, 'mimeType': 'application/vnd.google-apps.spreadsheet', 'parents': [folder]},
                    media_body=media, fields='id,name', supportsAllDrives=True), retry_safe=False)

    def move(self, file_id, folder):
        parents = self.metadata(file_id).get('parents', [])
        if parents == [folder]:
            return
        execute(self.api().update(fileId=file_id, addParents=folder, removeParents=','.join(parents), fields='id,parents', supportsAllDrives=True))
