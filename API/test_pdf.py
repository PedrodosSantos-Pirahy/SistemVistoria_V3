import os
import tempfile
import uuid
from datetime import datetime
from weasyprint import HTML
from jinja2 import Environment, FileSystemLoader
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# ---------------------------
# CONFIG GOOGLE
# ---------------------------
SERVICE_ACCOUNT_FILE = r"C:\Users\pedrosantos\OneDrive - PIRAHY\DEV\Sistema Vistorias - Pirahy\SistemVistoria\API\service-account.json"
DRIVE_FOLDER_ID = "0AKLd3H4beidVUk9PVA"
SCOPES = ["https://www.googleapis.com/auth/drive"]

creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
drive_service = build("drive", "v3", credentials=creds)

# ---------------------------
# FUNÇÃO DE UPLOAD PDF
# ---------------------------
def upload_file_to_drive(file_path: str, filename: str, mime: str = "application/pdf"):
    media = MediaFileUpload(file_path, mimetype=mime, resumable=True)
    metadata = {"name": filename}
    if DRIVE_FOLDER_ID:
        metadata["parents"] = [DRIVE_FOLDER_ID]
    created = drive_service.files().create(
        body=metadata,
        media_body=media,
        fields="id, webViewLink, webContentLink",
        supportsAllDrives=True
    ).execute()
    file_id = created.get("id")
    try:
        drive_service.permissions().create(
            fileId=file_id,
            body={"role": "reader", "type": "anyone"},
            supportsAllDrives=True
        ).execute()
    except:
        pass
    return created.get("webContentLink") or created.get("webViewLink") or f"https://drive.google.com/file/d/{file_id}/view"

# ---------------------------
# CONTEXTO DE TESTE
# ---------------------------
context = {
    "data": datetime.now().strftime("%d/%m/%Y"),
    "chegada": "08:00",
    "vistoria": "09:30",
    "fim": "10:00",
    "ordem": "12345",
    "transportadora": "Transportadora XYZ",
    "operacao": "Carga",
    "produto": "Cimento",
    "ultimos_produtos": "Areia, Pedra, Tijolo",
    "tipo_veiculo": "Baú",
    "status_final": "APROVADO",
    "placas": ["ABC-1234", "DEF-5678", "GHI-9012"],
    "limpeza": "Conforme",
    "danos": "Conforme",
    "umidade": "Não Conforme",
    "residuos": "Conforme",
    "odores": "Conforme",
    "bocas_graneleiras": "Conforme",
    "lonas": "Conforme",
    "chapas_mdf": "Conforme",
    "lonas_protecao": "Conforme",
    "equipamentos": "Conforme",
    "tampas_laterais": "Conforme",
    "bau_altura_porta": "Conforme",
    "bau_largura_porta": "Conforme",
    "bau_assoalho": "Conforme",
    "container_peso": "",
    "observacoes": "Nenhuma observação adicional.",
    "assinaturas": {
        "cq": {"nome": "Pedro CQ", "imagem": ""},
        "motorista": {"nome": "João Motorista", "imagem": ""},
        "vistoriador": {"nome": "Carlos Vistoriador", "imagem": ""}
    }
}

# ---------------------------
# GERAR PDF USANDO TEMPLATE vistoria_pdf.html
# ---------------------------
base_dir = os.path.dirname(os.path.abspath(__file__))
env = Environment(loader=FileSystemLoader(base_dir))
template = env.get_template("vistoria_pdf.html")
html_rendered = template.render(context)

pdf_path = os.path.join(tempfile.gettempdir(), f"vistoria_test_{uuid.uuid4().hex}.pdf")
HTML(string=html_rendered, base_url=base_dir).write_pdf(pdf_path)
print("PDF gerado em:", pdf_path)

# ---------------------------
# UPLOAD DRIVE
# ---------------------------
link = upload_file_to_drive(pdf_path, f"vistoria_test_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf")
print("Link Drive:", link)
