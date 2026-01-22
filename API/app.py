from flask import Flask, request, jsonify
from flask_cors import CORS
import logging
import tempfile
import base64
import re
import io
from datetime import datetime

#FILA + WORKER
from queue import Queue
from threading import Thread
import time

vistoria_queue = Queue(maxsize=100)  # evita overload

#Helpers
import json
from pathlib import Path
import traceback

BACKUP_DIR = Path("backups_vistorias")
BACKUP_DIR.mkdir(exist_ok=True)


#PDF
from flask import render_template
from weasyprint import HTML
import os
import uuid

from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials
from googleapiclient.http import MediaFileUpload
from googleapiclient.http import MediaIoBaseDownload

from dotenv import load_dotenv

print("=== DEBUG INICIAL ===")
print("Arquivo atual:", __file__)
print("Diretório atual (cwd):", os.getcwd())
print("Existe .env aqui?:", Path(".env").exists())
print("Existe service_account.json aqui?:", Path("service_account.json").exists())
print("=====================")
##

# --------------------------------------------------------------------------
# LOG
# --------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("vistoria-api")

# --------------------------------------------------------------------------
# FLASK
# --------------------------------------------------------------------------
app = Flask(__name__, template_folder=os.path.dirname(os.path.abspath(__file__)))
CORS(app)

# --------------------------------------------------------------------------
# CONFIG GOOGLE
# --------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent  # pasta API
SERVICE_ACCOUNT_PATH = BASE_DIR / "service-account.json"

print("SERVICE ACCOUNT PATH:", SERVICE_ACCOUNT_PATH)

if not SERVICE_ACCOUNT_PATH.exists():
    raise RuntimeError(f"Service account não encontrado: {SERVICE_ACCOUNT_PATH}")

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]
creds = Credentials.from_service_account_file(
    SERVICE_ACCOUNT_PATH,
     scopes=SCOPES
)

SHEET_ID = "1OypeFbnDkBMWNYSqH36DJYtR8l4lapWwG9j44fdzTXw"
SHEET_TAB = "Respostas_V2"
AUDITORIA_TAB = "Auditoria"

#Comparar
#1OypeFbnDkBMWNYSqH36DJYtR8l4lapWwG9j44fdzTXw
#1OypeFbnDkBMWNYSqH36DJYtR8l4lapWwG9j44fdzTXw
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID", "1OypeFbnDkBMWNYSqH36DJYtR8l4lapWwG9j44fdzTXw")

# Pasta/Unidade destino no Drive (pode ser Shared Drive). A service account deve ter acesso.
DRIVE_FOLDER_ID = "0AKLd3H4beidVUk9PVA"



from datetime import timedelta

CACHE_PENDENCIAS = {
    "data": None,
    "expires": None
}

drive_service = build("drive", "v3", credentials=creds)
import httplib2
from google_auth_httplib2 import AuthorizedHttp

http = httplib2.Http(timeout=60)
authed_http = AuthorizedHttp(creds, http=http)

sheets_service = build(
    "sheets",
    "v4",
    http=authed_http,
    cache_discovery=False
).spreadsheets()



# --------------------------------------------------------------------------
# HELPERS
# --------------------------------------------------------------------------
DATAURL_RE = re.compile(r"^data:(?P<mime>[^;]+);base64,(?P<data>.+)$")

#STATUS OFICIAIS DA AUDITORIA
STATUS_VALIDOS = {
    "PENDENTE",
    "EM_ANDAMENTO",
    "REALIZADA",
    "REALIZADA_COM_ATRASO",
    "CANCELADA",
    "INCOMPLETA",
    "EXPIRADA",
}

TRANSICOES_VALIDAS = {
    "PENDENTE": {"EM_ANDAMENTO", "CANCELADA"},
    "EM_ANDAMENTO": {"REALIZADA", "CANCELADA", "INCOMPLETA"},
    "EXPIRADA": {"REALIZADA_COM_ATRASO"},
}

#MiniDash da API
STATUS = {
    "started_at": datetime.utcnow(),
    "processing": False,
    "current_id": None,
    "processed": 0,
    "last_error": None,
    "last_success": None
}

def detect_mime_and_data(dataurl: str):
    """
    Recebe um data URL (data:...;base64,xxxxx) ou só o base64 cru.
    Retorna (mime, bytes, ext) ou (None, None, None) se inválido.
    """
    if not dataurl:
        return None, None, None
    m = DATAURL_RE.match(dataurl)
    if m:
        mime = m.group("mime")
        b64 = m.group("data")
    else:
        # se recebeu apenas base64 sem prefixo, assumir image/png
        mime = "image/png"
        b64 = dataurl
    try:
        raw = base64.b64decode(b64)
    except Exception as e:
        log.warning("Falha ao decodificar base64: %s", e)
        return None, None, None
    # extensão a partir do mime
    ext = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/webp": ".webp"
    }.get(mime, ".png")
    return mime, raw, ext

def upload_base64_to_drive(base64_data: str, filename_prefix: str):
    """
    Converte base64(dataURL) para arquivo temporário -> faz upload ao Drive (supportsAllDrives=True)
    Retorna link público (webContentLink/view) ou "" em caso de falha.
    """
    if not base64_data:
        log.info("SKIP upload: campo vazio para %s", filename_prefix)
        return ""

    mime, raw, ext = detect_mime_and_data(base64_data)
    if raw is None:
        log.warning("Base64 inválido para %s", filename_prefix)
        return ""

    temp_name = f"{filename_prefix}_{uuid.uuid4().hex}{ext}"
    temp_path = os.path.join(tempfile.gettempdir(), temp_name)
    try:
        with open(temp_path, "wb") as f:
            f.write(raw)
        log.info("Arquivo temporário criado: %s (bytes=%d, mime=%s)", temp_path, len(raw), mime)

        media = MediaFileUpload(temp_path, mimetype=mime, resumable=True)
        metadata = {"name": temp_name}
        if DRIVE_FOLDER_ID:
            metadata["parents"] = [DRIVE_FOLDER_ID]

        log.info("Iniciando upload para Drive: %s", temp_name)
        created = drive_service.files().create(
            body=metadata,
            media_body=media,
            fields="id, webViewLink, webContentLink",
            supportsAllDrives=True
        ).execute()

        file_id = created.get("id")
        if not file_id:
            log.error("Upload não retornou file id para %s", temp_name)
            try:
                os.remove(temp_path)
            except Exception:
                pass
            return ""

        # tentar criar permissão anyone (pode falhar por política do domínio)
        try:
            drive_service.permissions().create(
                fileId=file_id,
                body={"role": "reader", "type": "anyone"},
                supportsAllDrives=True
            ).execute()
            log.info("Permissão 'anyone' criada para file_id=%s", file_id)
        except Exception as pe:
            log.warning("Não foi possível setar permissão 'anyone' para %s: %s", file_id, pe)

        # preferir webContentLink/WebViewLink se disponível
        link = created.get("webContentLink") or created.get("webViewLink") or f"https://drive.google.com/file/d/{file_id}/view"
        log.info("Upload OK: id=%s link=%s", file_id, link)

        return link

    except Exception as e:
        log.exception("Erro no upload_base64_to_drive (%s): %s", filename_prefix, e)
        return ""
    finally:
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
                log.debug("Temp file removido: %s", temp_path)
        except Exception:
            pass

def upload_file_to_drive(file_path: str, filename: str, mime: str):
    """
    Faz upload de um arquivo físico (ex: PDF) para o Drive
    Retorna link público ou "" em caso de erro
    """
    try:
        media = MediaFileUpload(file_path, mimetype=mime, resumable=True)

        metadata = {
            "name": filename
        }

        if DRIVE_FOLDER_ID:
            metadata["parents"] = [DRIVE_FOLDER_ID]

        log.info("Iniciando upload do arquivo: %s", filename)

        created = drive_service.files().create(
            body=metadata,
            media_body=media,
            fields="id, webViewLink, webContentLink",
            supportsAllDrives=True
        ).execute()

        file_id = created.get("id")
        if not file_id:
            log.error("Upload não retornou file_id para %s", filename)
            return ""

        # liberar acesso público (se permitido)
        try:
            drive_service.permissions().create(
                fileId=file_id,
                body={"role": "reader", "type": "anyone"},
                supportsAllDrives=True
            ).execute()
        except Exception as e:
            log.warning("Permissão pública não aplicada: %s", e)

        link = (
            created.get("webContentLink")
            or created.get("webViewLink")
            or f"https://drive.google.com/file/d/{file_id}/view"
        )

        log.info("Upload PDF OK: %s", link)
        return link

    except Exception as e:
        log.exception("Erro upload_file_to_drive: %s", e)
        return ""

import time
from googleapiclient.errors import HttpError

def sheets_get_with_retry(service, spreadsheet_id, range_name, retries=3):
    for attempt in range(retries):
        try:
            return service.values().get(
                spreadsheetId=spreadsheet_id,
                range=range_name
            ).execute()
        except (HttpError, TimeoutError) as e:
            log.warning(
                "Erro Sheets (tentativa %d/%d): %s",
                attempt + 1, retries, e
            )
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt)  # backoff exponencial


def get_agend_v2_columns(filter_date=None):
    try:
        now = datetime.now()

        # ---------- CACHE ----------
        if (
            CACHE_PENDENCIAS["data"] is not None
            and CACHE_PENDENCIAS["expires"] is not None
            and CACHE_PENDENCIAS["expires"] > now
            and filter_date is None
        ):
            log.info("Retornando pendências do CACHE")
            return CACHE_PENDENCIAS["data"]

        range_name = "Agend_V2!A1:Z"

        result = sheets_get_with_retry(
            sheets_service,
            SPREADSHEET_ID,
            range_name
        )

        values = result.get("values", [])
        if not values:
            return []

        
        selected_data = []

        for row in values[1:]:  # pula cabeçalho
            date_value = row[1] if len(row) > 1 and isinstance(row[1], str) else ""     #B
            hora = row[2] if len(row) > 2 else ""           #C
            pre_ordem = row[4] if len(row) > 4 else ""      #E
            transportadora = row[5] if len(row) > 5 else "" #F
            status = row[10] if len(row) > 10 else ""       #K
            id_vistoria = row[24] if len(row) > 24 else ""  #Y
            placa = row[25] if len(row) > 25 else ""        #Z

            status_normalizado = status.strip().lower()
            if not date_value:
                continue 

            categoria_data = classificar_data(date_value)

            if (
                status_normalizado not in ("concluida", "cancelada")
                and categoria_data != "indefinida"
                
            ):
                selected_data.append({
                    "data": date_value,
                    "categoria_data": categoria_data,  # 👈 AQUI
                    "hora": hora,
                    "placa": placa,
                    "status": status,
                    "id": id_vistoria,
                    "pre_ordem": pre_ordem,
                    "transportadora": transportadora
                })



        selected_data.sort(key=lambda x: x.get("hora", ""))

        # ---------- SALVA CACHE ----------
        if filter_date is None:
            CACHE_PENDENCIAS["data"] = selected_data
            CACHE_PENDENCIAS["expires"] = now + timedelta(minutes=5)

        return selected_data

    except Exception as e:
        log.exception("Erro Sheets pendencias: %s", e)
        return None

def classificar_data(data_str: str) -> str:
    if not data_str or not isinstance(data_str, str):
        return "indefinida"

    data_str = data_str.strip()

    formatos = [
        "%d/%m/%Y",
        "%d/%m/%Y %H:%M",
        "%Y-%m-%d"
    ]

    for fmt in formatos:
        try:
            data = datetime.strptime(data_str, fmt).date()
            hoje = datetime.now().date()

            if data < hoje:
                return "Datas Anteriores"
            elif data == hoje:
                return "Data Atual"
            else:
                return "Datas Futuras"
        except ValueError:
            continue

    return "indefinida"

def extract_status(obj):
    return obj.get("status", "") if obj else ""


def montar_itens_inspecao(ii, pc, dv, tipo):
    itens = []

    def add(label, obj):
        if obj and obj.get("status"):
            itens.append({
                "pergunta": label,
                "resposta": obj.get("status")
            })

    add("Limpeza interna", ii.get("limpeza"))
    add("Danos estruturais", ii.get("danos"))
    add("Umidade", ii.get("umidade"))
    add("Resíduos", ii.get("residuos"))
    add("Odores", ii.get("odores"))

    add("Lonas de proteção", pc.get("lonasProtecao"))
    add("Equipamentos de segurança", pc.get("equipamentos"))

    if tipo == "Baú":
        add("Altura da porta", dv.get("caminhaoBau", {}).get("alturaPorta"))
        add("Largura da porta", dv.get("caminhaoBau", {}).get("larguraPorta"))
        add("Assoalho liso", dv.get("caminhaoBau", {}).get("assoalhoLiso"))

    if tipo == "Container":
        add("Verificação de peso", dv.get("container", {}).get("verificacaoPeso"))

    return itens


def montar_ocorrencias(ii, pc, dv):
    ocorrencias = []

    def check(obj):
        if obj and obj.get("outros"):
            ocorrencias.append(obj.get("outros"))

    for bloco in [ii, pc]:
        for v in bloco.values():
            check(v)

    for v in dv.get("caminhaoBau", {}).values():
        check(v)

    for v in dv.get("container", {}).values():
        check(v)

    return ocorrencias

def gerar_pdf_vistoria(context):
    html = render_template("vistoria_pdf.html", **context)

    pdf_path = os.path.join(
        tempfile.gettempdir(),
        f"vistoria_{uuid.uuid4().hex}.pdf"
    )

    base_dir = os.path.dirname(os.path.abspath(__file__))

    HTML(
        string=html,
        base_url=base_dir
    ).write_pdf(pdf_path)

    return pdf_path

    
# --- FUNÇÃO DE VALIDAÇÃO (fora de qualquer @app.post) ---
def validar_assinaturas(context):
    obrigatorias = ["motorista", "vistoriador"]
    assinaturas = context.get("assinaturas")
    if not assinaturas:
        raise ValueError("Contexto não contém 'assinaturas'.")
    for papel in obrigatorias:
        if papel not in assinaturas:
            raise ValueError(f"Assinatura obrigatória ausente: {papel}")
        if not assinaturas[papel].get("imagem") or not assinaturas[papel].get("nome"):
            raise ValueError(f"Assinatura obrigatória incompleta: {papel}")

import io
import base64
from googleapiclient.http import MediaIoBaseDownload

def baixar_imagem_drive_base64(DRIVE_FOLDER_ID : str) -> str:
    if not DRIVE_FOLDER_ID:
        return ""

    request = drive_service.files().get_media(DRIVE_FOLDER_ID=DRIVE_FOLDER_ID)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)

    done = False
    while not done:
        status, done = downloader.next_chunk()

    fh.seek(0)
    encoded = base64.b64encode(fh.read()).decode("utf-8")
    return f"data:image/png;base64,{encoded}"

def buscar_vistoria_por_placa(placa: str):
    result = sheets_service.values().get(
        spreadsheetId=SHEET_ID,
        range=f"{SHEET_TAB}!A2:Z500"
    ).execute()

    values = result.get("values", [])

    for idx, row in enumerate(values, start=2):
        placa_sheet = row[25] if len(row) > 25 else ""  # coluna Z
        if placa_sheet == placa:
            return idx, row

    return None, None

def data_eh_hoje(data_str: str) -> bool:
    hoje = datetime.now().strftime("%d/%m/%Y")
    return data_str == hoje

def registrar_auditoria(
    placa,
    status_anterior,
    status_novo,
    motivo,
    vistoriador,
    data_agendada,
    hora_agendada,
    ip
):
    linha = [
        datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        placa,
        status_anterior,
        status_novo,
        motivo,
        vistoriador,
        data_agendada,
        hora_agendada,
        ip
    ]

    sheets_service.values().append(
        spreadsheetId=SHEET_ID,
        range=AUDITORIA_TAB,
        valueInputOption="RAW",
        body={"values": [linha]}
    ).execute()

def achar_ou_criar_linha_por_id(id_vistoria: str):
    """
    Coluna A = ID
    - Se achar o ID → retorna a linha
    - Se não achar → cria nova linha com o ID
    """

    log.info("Buscando ID na Respostas_V2: %s", id_vistoria)

    result = sheets_service.values().get(
        spreadsheetId=SHEET_ID,
        range=f"{SHEET_TAB}!A2:A5000"
    ).execute()

    values = result.get("values", [])

    for idx, row in enumerate(values, start=2):
        if row and row[0] == id_vistoria:
            log.info("ID encontrado na linha %d", idx)
            return idx

    # não achou → cria nova linha
    nova_linha = len(values) + 2

    log.info("ID não encontrado, criando na linha %d", nova_linha)

    sheets_service.values().update(
        spreadsheetId=SHEET_ID,
        range=f"{SHEET_TAB}!A{nova_linha}",
        valueInputOption="RAW",
        body={"values": [[id_vistoria]]}
    ).execute()

    return nova_linha

def processar_vistoria(data: dict) -> dict:

    log.info("PROCESSAR_VISTORIA | Início do processamento")
    log.debug("PROCESSAR_VISTORIA | Payload completo: %s", json.dumps(data, indent=2))

    # --------------------
    # DADOS INICIAIS
    # --------------------
    di = data.get("dadosIniciais", {})
    ii = data.get("inspecaoInterna", {})
    pc = data.get("protecaoCarga", {})
    dv = data.get("detalhesVeiculo", {})
    fv = data.get("fotosVistoria", {})
    fin = data.get("finalizacao", {})

    id_vistoria = data.get("id", "")
    log.info("PROCESSAR_VISTORIA | ID=%s", id_vistoria)
    log.debug("DADOS INICIAIS: %s", di)
    log.debug("INSPECAO INTERNA: %s", ii)
    log.debug("PROTECAO CARGA: %s", pc)
    log.debug("DETALHES VEICULO: %s", dv)
    log.debug("FOTOS VISTORIA: %s", fv)
    log.debug("FINALIZACAO: %s", fin)

    # --------------------
    # UPLOAD FOTOS / ASSINATURAS
    # --------------------
    uploaded = {}
    try:
        placas = fv.get("placas", {})
        log.info("UPLOAD | Placas: %s", placas)
        uploaded["fotoPlaca1"] = upload_base64_to_drive(placas.get("fotoPlaca1"), "placa1")
        uploaded["fotoPlaca2"] = upload_base64_to_drive(placas.get("fotoPlaca2"), "placa2")
        uploaded["fotoPlaca3"] = upload_base64_to_drive(placas.get("fotoPlaca3"), "placa3")

        interior = fv.get("interiorCarroceria", {})
        log.info("UPLOAD | Interior Carroceria: %s", interior)
        uploaded["fotoInterior1"] = upload_base64_to_drive(interior.get("fotoInterior1"), "interior1")
        uploaded["fotoInterior2"] = upload_base64_to_drive(interior.get("fotoInterior2"), "interior2")

        log.info("UPLOAD | Assinaturas")
        uploaded["assinaturaMotorista"] = upload_base64_to_drive(fin.get("motoristaAssinatura"), "assinatura_motorista")
        uploaded["assinaturaVistoriador"] = upload_base64_to_drive(fin.get("vistoriadorAssinatura"), "assinatura_vistoriador")
        log.info("UPLOAD | Upload concluído: %s", uploaded.keys())
    except Exception as e:
        log.exception("UPLOAD | Erro no upload de fotos/assinaturas: %s", e)
        raise

    # --------------------
    # CONTEXTO PDF
    # --------------------
    try:
        context = {
            "data": datetime.now().strftime("%d/%m/%Y"),
            "chegada": di.get("chegada", ""),
            "vistoria": di.get("vistoria", ""),
            "fim": di.get("fim", ""),
            "ordem": di.get("numeroOrdem", ""),
            "transportadora": di.get("transportadora", ""),
            "operacao": di.get("operacao", ""),
            "produto": di.get("produto", ""),
            "ultimos_produtos": di.get("ultimosProdutos", ""),
            "tipo_veiculo": di.get("tipoVeiculo", ""),
            "status_final": fin.get("caminhaoLiberado", ""),
            "placas": [
                placas.get("placa1", ""),
                placas.get("placa2", ""),
                placas.get("placa3", "")
            ],
            "limpeza": extract_status(ii.get("limpeza")),
            "danos": extract_status(ii.get("danos")),
            "umidade": extract_status(ii.get("umidade")),
            "residuos": extract_status(ii.get("residuos")),
            "odores": extract_status(ii.get("odores")),
            "bocas_graneleiras": extract_status(ii.get("bocasGraneleiras")),
            "lonas": extract_status(ii.get("lonas")),
            "chapas_mdf": extract_status(ii.get("chapasMdf")),
            "lonas_protecao": extract_status(pc.get("lonasProtecao")),
            "equipamentos": extract_status(pc.get("equipamentos")),
            "tampas_laterais": extract_status(pc.get("tampasLaterais")),
            "bau_altura_porta": extract_status(dv.get("caminhaoBau", {}).get("alturaPorta")),
            "bau_largura_porta": extract_status(dv.get("caminhaoBau", {}).get("larguraPorta")),
            "bau_assoalho": extract_status(dv.get("caminhaoBau", {}).get("assoalhoLiso")),
            "container_peso": extract_status(dv.get("container", {}).get("verificacaoPeso")),
            "observacoes": fin.get("observacoes", ""),
            "assinaturas": {
                "motorista": {"nome": fin.get("motoristaNome", ""), "imagem": uploaded["assinaturaMotorista"]},
                "vistoriador": {"nome": fin.get("vistoriadorNome", ""), "imagem": uploaded["assinaturaVistoriador"]}
            }
        }
        log.info("PDF | Contexto criado")
        log.debug("PDF | Contexto detalhado: %s", json.dumps(context, indent=2))
    except Exception as e:
        log.exception("PDF | Erro ao criar contexto do PDF: %s", e)
        raise

    # --------------------
    # VALIDAÇÃO ASSINATURAS
    # --------------------
    try:
        log.info("VALIDAR | Assinaturas")
        validar_assinaturas(context)
        log.info("VALIDAR | Assinaturas OK")
    except Exception as e:
        log.exception("VALIDAR | Erro na validação de assinaturas: %s", e)
        raise

    # --------------------
    # GERAR PDF
    # --------------------
    try:
        pdf_path = gerar_pdf_vistoria(context)
        log.info("PDF | PDF gerado em %s", pdf_path)
        pdf_link = upload_file_to_drive(pdf_path, f"vistoria_{di.get('numeroOrdem','')}.pdf", "application/pdf")
        log.info("PDF | Upload do PDF concluído: %s", pdf_link)
    except Exception as e:
        log.exception("PDF | Erro na geração ou upload do PDF: %s", e)
        raise

    # --------------------
    # GOOGLE SHEETS
    # --------------------
    try:
        log.info("SHEETS | Preparando linha para Google Sheets")
        linha = [
            id_vistoria,
            "Concluida",
            di.get("chegada", ""),
            di.get("vistoria", ""),
            di.get("fim", ""),
            di.get("numeroOrdem", ""),
            di.get("transportadora", ""),
            di.get("operacao", ""),
            di.get("produto", ""),
            di.get("ultimosProdutos", ""),
            di.get("tipoVeiculo", ""),
            extract_status(ii.get("limpeza")),
            extract_status(ii.get("danos")),
            extract_status(ii.get("umidade")),
            extract_status(ii.get("residuos")),
            extract_status(ii.get("odores")),
            extract_status(ii.get("bocasGraneleiras")),
            extract_status(ii.get("lonas")),
            extract_status(ii.get("chapasMdf")),
            extract_status(pc.get("lonasProtecao")),
            extract_status(pc.get("equipamentos")),
            extract_status(pc.get("tampasLaterais")),
            extract_status(dv.get("caminhaoBau", {}).get("alturaPorta")),
            extract_status(dv.get("caminhaoBau", {}).get("larguraPorta")),
            extract_status(dv.get("caminhaoBau", {}).get("assoalhoLiso")),
            extract_status(dv.get("container", {}).get("verificacaoPeso")),
            "",
            "",
            fin.get("motoristaNome", ""),
            uploaded["assinaturaMotorista"],
            fin.get("vistoriadorNome", ""),
            uploaded["assinaturaVistoriador"],
            placas.get("placa1", ""),
            uploaded["fotoPlaca1"],
            placas.get("placa2", ""),
            uploaded["fotoPlaca2"],
            placas.get("placa3", ""),
            uploaded["fotoPlaca3"],
            uploaded["fotoInterior1"],
            uploaded["fotoInterior2"],
            fin.get("caminhaoLiberado", ""),
            fin.get("observacoes", ""),
            pdf_link
        ]
        response = sheets_service.values().append(
            spreadsheetId=SHEET_ID,
            range=f"{SHEET_TAB}!A2:A5000",            
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": [linha]}
        ).execute()

        updated_range = response["updates"]["updatedRange"]
        log.info("SHEETS | Linha criada em %s", updated_range)

    except Exception as e:
        log.exception("SHEETS | Erro ao enviar para Google Sheets: %s", e)
        raise

    log.info("PROCESSAR_VISTORIA | Vistoria concluída com sucesso | ID=%s", id_vistoria)

    return {"status": "ok", "id": id_vistoria, "pdf": pdf_link}

def salvar_backup_vistoria(payload: dict):
    try:
        di = payload.get("dadosIniciais", {})
        fv = payload.get("fotosVistoria", {})

        # tenta extrair placa de forma segura
        placa = (
            fv.get("placas", {}).get("placa1")
            or fv.get("placas", {}).get("placa2")
            or "SEM_PLACA"
        )

        placa = placa.replace(" ", "").upper()

        data_agendada = di.get("vistoria") or di.get("chegada") or datetime.now().strftime("%d/%m/%Y")
        try:
            data_fmt = datetime.strptime(data_agendada, "%d/%m/%Y")
        except ValueError:
            data_fmt = datetime.strptime(data_agendada, "%d/%m/%Y %H:%M")

        data_fmt = data_fmt.strftime("%Y-%m-%d")


        filename = f"{placa}_{data_fmt}.json"
        path = BACKUP_DIR / filename

        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        log.info("Backup da vistoria salvo em %s", path)

    except Exception as e:
        log.exception("Falha ao salvar backup da vistoria: %s", e)

def worker():
    while True:
        payload, result_holder = vistoria_queue.get()
        try:
            log.info("WORKER | Recebido payload na fila: %s", payload.get("id"))
            with app.app_context():  # 🔑 ISSO RESOLVE
                log.info("WORKER | Salvando backup da vistoria")
                salvar_backup_vistoria(payload)
                log.info("WORKER | Chamando processar_vistoria")
                result_holder["response"] = processar_vistoria(payload)
        except Exception as e:
            log.exception("WORKER | Erro no processamento da vistoria: %s", e)
            result_holder["error"] = str(e)
        finally:
            vistoria_queue.task_done()


Thread(target=worker, daemon=True).start()


# -------------------
# ENDPOINTS
# -------------------
@app.route("/api/status")
def status():
    return jsonify({
        "status": "online",
        "uptime_seconds": int(
            (datetime.utcnow() - STATUS["started_at"]).total_seconds()
        ),
        "fila": {
            "tamanho": vistoria_queue.qsize(),
            "limite": vistoria_queue.maxsize
        },
        "processamento": {
            "ativo": STATUS["processing"],
            "id_atual": STATUS["current_id"]
        },
        "estatisticas": {
            "processadas": STATUS["processed"],
            "ultimo_sucesso": STATUS["last_success"],
            "ultimo_erro": STATUS["last_error"]
        }
    })


@app.get("/")
def home():
    log.info("GET / chamada")
    return jsonify({"status": "API online"})

# ---- endpoint API JSON ----
@app.get("/pendencias")
def pendencias():
    
    date_filter = request.args.get("data")  # opcional: dd/mm/yyyy
    data = get_agend_v2_columns(date_filter)

    if data is None:
        return jsonify({"status": "API online", "error": "Não foi possível acessar a planilha"}), 500

    return jsonify({
        "status": "API online",
        "pendentes": data,
        "total": len(data)
    })

# -------------------
# NÃO MEXER
# -------------------
@app.post("/vistoria")
def receive_vistoria():
    if not request.json:
        return jsonify({"error": "Payload vazio"}), 400

    result_holder = {}

    try:
        vistoria_queue.put((request.json, result_holder), timeout=5)
    except:
        return jsonify({"error": "Fila cheia, tente novamente"}), 503

    # 🔒 AGUARDA PROCESSAMENTO
    while "response" not in result_holder and "error" not in result_holder:
        time.sleep(0.1)

    if "error" in result_holder:
        return jsonify({"error": result_holder["error"]}), 500

    return jsonify(result_holder["response"]), 200

@app.post("/cancelar")
def cancelar_vistoria():
    try:
        data = request.json
        log.info("Payload cancelar: %s", data)

        id_vistoria = data.get("id")
        nome = data.get("nome")
        motivo = data.get("motivo")

        if not id_vistoria or not nome or not motivo:
            return jsonify({"error": "id, nome e motivo são obrigatórios"}), 400

        # 🔑 só isso importa
        linha = achar_ou_criar_linha_por_id(id_vistoria)

        # Atualizações fixas
        sheets_service.values().update(
            spreadsheetId=SHEET_ID,
            range=f"{SHEET_TAB}!B{linha}",  # STATUS
            valueInputOption="RAW",
            body={"values": [["Cancelada"]]}
        ).execute()

        sheets_service.values().update(
            spreadsheetId=SHEET_ID,
            range=f"{SHEET_TAB}!AP{linha}",  # MOTIVO/Observação
            valueInputOption="RAW",
            body={"values": [[motivo]]}
        ).execute()

        sheets_service.values().update(
            spreadsheetId=SHEET_ID,
            range=f"{SHEET_TAB}!AE{linha}",  # VISTORIADOR
            valueInputOption="RAW",
            body={"values": [[nome]]}
        ).execute()

        log.info("Cancelamento OK | ID=%s | linha=%d", id_vistoria, linha)

        return jsonify({
            "status": "ok",
            "id": id_vistoria,
            "linha": linha
        }), 200

    except Exception as e:
        log.exception("Erro ao cancelar vistoria")
        return jsonify({"error": str(e)}), 500

@app.before_request
def log_request():
    print(">>>", request.method, request.path)


# --------------------------------------------------------------------------
# RUN
# --------------------------------------------------------------------------
# Gunicorn é o responsável por iniciar a aplicação
#if __name__ == "__main__":
#   log.info("SUBINDO API FLASK (DEV)")
#   HOST = os.getenv("API_HOST", "127.0.0.1")
#   PORT = int(os.getenv("API_PORT", 5000))
#   
#   app.run(host=HOST, port=PORT)

if __name__ == "__main__":
   log.info("SUBINDO API FLASK (DEV)")
   HOST = os.getenv("API_HOST", "192.168.53.193")
   PORT = int(os.getenv("API_PORT", 5000))
   
   app.run(host=HOST, port=PORT)

