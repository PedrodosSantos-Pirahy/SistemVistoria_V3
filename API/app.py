from flask import Flask, request, jsonify
from flask_cors import CORS
import logging
import tempfile
import base64
import re
import io
from datetime import datetime, timedelta

# FILA + WORKER
from queue import Queue
from threading import Thread
import time

# Adicione o Lock aqui
from threading import Thread, Lock

# Helpers
import json
from pathlib import Path
import traceback
import os
import uuid

# PDF
from flask import render_template
from weasyprint import HTML

from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials
from googleapiclient.http import MediaFileUpload
from googleapiclient.http import MediaIoBaseDownload
from googleapiclient.errors import HttpError

import httplib2
from google_auth_httplib2 import AuthorizedHttp
from dotenv import load_dotenv

# --------------------------------------------------------------------------
# CONFIGURAÇÃO DE LOGS (LIMPO E SEM POLUIÇÃO DE FONTES)
# --------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt='%H:%M:%S')
log = logging.getLogger("vistoria-api")

# 🤫 SILENCIAR BIBLIOTECAS EXTERNAS (Aqui está a mágica)
# Isso remove toda aquela sujeira de 'Reading maxp table', 'glyf pruned', etc.
logging.getLogger("fontTools").setLevel(logging.ERROR)
logging.getLogger("weasyprint").setLevel(logging.ERROR)
logging.getLogger("googleapiclient").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

log.info("=== 🚀 DEBUG INICIAL ===")
log.info("Arquivo atual: %s", __file__)
log.info("Diretório atual (cwd): %s", os.getcwd())

# --------------------------------------------------------------------------
# FLASK & CONFIGS
# --------------------------------------------------------------------------
BACKUP_DIR = Path("backups_vistorias")
BACKUP_DIR.mkdir(exist_ok=True)

vistoria_queue = Queue(maxsize=100)

app = Flask(__name__, template_folder=os.path.dirname(os.path.abspath(__file__)))
CORS(app)

BASE_DIR = Path(__file__).resolve().parent
SERVICE_ACCOUNT_PATH = BASE_DIR / "service-account.json"

log.info("SERVICE ACCOUNT PATH: %s", SERVICE_ACCOUNT_PATH)

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

# IDs
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID", "1OypeFbnDkBMWNYSqH36DJYtR8l4lapWwG9j44fdzTXw")
SHEET_ID = SPREADSHEET_ID # Mantendo compatibilidade com seu código
SHEET_TAB = "Respostas_V2"
AUDITORIA_TAB = "Auditoria"
DRIVE_FOLDER_ID = "0AKLd3H4beidVUk9PVA"

CACHE_PENDENCIAS = {
    "data": None,
    "expires": None
}

# Serviços Google
http = httplib2.Http(timeout=60)
authed_http = AuthorizedHttp(creds, http=http)

drive_service = build("drive", "v3", credentials=creds)
sheets_service = build(
    "sheets",
    "v4",
    http=authed_http,
    cache_discovery=False
).spreadsheets()

# --------------------------------------------------------------------------
# HELPERS & CONSTANTES
# --------------------------------------------------------------------------
DATAURL_RE = re.compile(r"^data:(?P<mime>[^;]+);base64,(?P<data>.+)$")

STATUS_VALIDOS = {
    "PENDENTE", "EM_ANDAMENTO", "REALIZADA",
    "REALIZADA_COM_ATRASO", "CANCELADA", "INCOMPLETA", "EXPIRADA",
}

STATUS = {
    "started_at": datetime.utcnow(),
    "processing": False,
    "current_id": None,
    "processed": 0,
    "last_error": None,
    "last_success": None
}
def invalidar_cache_pendencias():
    global CACHE_PENDENCIAS
    log.info("🧹 [CACHE] Invalidando cache de pendências...")
    CACHE_PENDENCIAS["data"] = None
    CACHE_PENDENCIAS["expires"] = None

def detect_mime_and_data(dataurl: str):
    if not dataurl:
        return None, None, None
    m = DATAURL_RE.match(dataurl)
    if m:
        mime = m.group("mime")
        b64 = m.group("data")
    else:
        mime = "image/png"
        b64 = dataurl
    try:
        raw = base64.b64decode(b64)
    except Exception as e:
        log.warning("⚠️ Falha ao decodificar base64: %s", e)
        return None, None, None
    
    ext = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/webp": ".webp"
    }.get(mime, ".png")
    return mime, raw, ext

def upload_base64_to_drive(base64_data: str, filename_prefix: str):
    """
    Log otimizado: Mostra tamanho em KB ao invés do conteúdo
    """
    if not base64_data:
        log.info("ℹ️ [DRIVE] Campo vazio para %s", filename_prefix)
        return ""

    mime, raw, ext = detect_mime_and_data(base64_data)
    if raw is None:
        log.warning("⚠️ [DRIVE] Base64 inválido para %s", filename_prefix)
        return ""

    # LOG NOVO: Tamanho do arquivo
    tamanho_kb = len(raw) / 1024
    temp_name = f"{filename_prefix}_{uuid.uuid4().hex}{ext}"
    temp_path = os.path.join(tempfile.gettempdir(), temp_name)
    
    try:
        with open(temp_path, "wb") as f:
            f.write(raw)
        
        log.info("📤 [DRIVE] Uploading: %s | %.2f KB | Mime: %s", filename_prefix, tamanho_kb, mime)

        media = MediaFileUpload(temp_path, mimetype=mime, resumable=True)
        metadata = {"name": temp_name}
        if DRIVE_FOLDER_ID:
            metadata["parents"] = [DRIVE_FOLDER_ID]

        created = drive_service.files().create(
            body=metadata,
            media_body=media,
            fields="id, webViewLink, webContentLink",
            supportsAllDrives=True
        ).execute()

        file_id = created.get("id")
        if not file_id:
            log.error("❌ [DRIVE] Falha: Não retornou ID para %s", temp_name)
            return ""

        try:
            drive_service.permissions().create(
                fileId=file_id,
                body={"role": "reader", "type": "anyone"},
                supportsAllDrives=True
            ).execute()
        except Exception as pe:
            log.warning("⚠️ [DRIVE] Falha permissão 'anyone' para %s: %s", file_id, pe)

        link = created.get("webContentLink") or created.get("webViewLink") or f"https://drive.google.com/file/d/{file_id}/view"
        log.info("✅ [DRIVE] Sucesso: %s", filename_prefix)

        return link

    except Exception as e:
        log.error("❌ [DRIVE] Erro crítico (%s): %s", filename_prefix, e)
        return ""
    finally:
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except Exception:
            pass

def upload_file_to_drive(file_path: str, filename: str, mime: str):
    try:
        media = MediaFileUpload(file_path, mimetype=mime, resumable=True)
        metadata = {"name": filename}
        if DRIVE_FOLDER_ID:
            metadata["parents"] = [DRIVE_FOLDER_ID]

        log.info("📤 [PDF] Iniciando upload: %s", filename)

        created = drive_service.files().create(
            body=metadata,
            media_body=media,
            fields="id, webViewLink, webContentLink",
            supportsAllDrives=True
        ).execute()

        file_id = created.get("id")
        if not file_id:
            log.error("❌ [PDF] Upload não retornou file_id")
            return ""

        try:
            drive_service.permissions().create(
                fileId=file_id,
                body={"role": "reader", "type": "anyone"},
                supportsAllDrives=True
            ).execute()
        except Exception as e:
            log.warning("⚠️ [PDF] Permissão pública falhou: %s", e)

        link = created.get("webContentLink") or created.get("webViewLink") or f"https://drive.google.com/file/d/{file_id}/view"
        log.info("✅ [PDF] PDF disponível em: %s", link)
        return link

    except Exception as e:
        log.exception("❌ [PDF] Erro upload_file_to_drive: %s", e)
        return ""

def sheets_get_with_retry(service, spreadsheet_id, range_name, retries=3):
    for attempt in range(retries):
        try:
            return service.values().get(
                spreadsheetId=spreadsheet_id,
                range=range_name
            ).execute()
        except (HttpError, TimeoutError) as e:
            log.warning("⚠️ [SHEETS] Tentativa %d/%d falhou: %s", attempt + 1, retries, e)
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt)

def get_agend_v2_columns(filter_date=None, force_refresh=False):
    try:
        now = datetime.now()

        if (CACHE_PENDENCIAS["data"] is not None
            and CACHE_PENDENCIAS["expires"] is not None
            and CACHE_PENDENCIAS["expires"] > now
            and filter_date is None
        ):
            # log.info("CACHE HIT: Retornando pendências locais") # Comentei para poluir menos, descomente se quiser
            return CACHE_PENDENCIAS["data"]

        range_name = "Agend_V2!A1:Z"
        result = sheets_get_with_retry(sheets_service, SPREADSHEET_ID, range_name)
        values = result.get("values", [])
        
        if not values:
            return []

        selected_data = []
        for row in values[1:]:
            date_value = row[1] if len(row) > 1 and isinstance(row[1], str) else ""
            hora = row[2] if len(row) > 2 else ""
            pre_ordem = row[4] if len(row) > 4 else ""
            transportadora = row[5] if len(row) > 5 else ""
            status = row[10] if len(row) > 10 else ""
            pirahy = row[23] if len(row) > 23 else ""
            id_vistoria = row[24] if len(row) > 24 else ""
            placa = row[25] if len(row) > 25 else ""

            hoje = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            
            try:
                # Converte a data da string (ajuste o formato '%d/%m/%Y' se sua planilha usar outro)
                data_objeto = datetime.strptime(date_value, '%d/%m/%Y')
            except ValueError:
                continue

            status_normalizado = status.strip().lower()
            categoria_data = classificar_data(date_value)

            # NOVA REGRA: 
            # 1. Data deve ser hoje ou futura (data_objeto >= hoje)
            # 2. Status não pode ser concluído ou cancelado
            # 3. Categoria não pode ser indefinida
            if (data_objeto >= hoje and 
                status_normalizado not in ("concluida", "cancelada") and 
                categoria_data != "indefinida"):
                
                selected_data.append({
                    "data": date_value,
                    "categoria_data": categoria_data,
                    "hora": hora,
                    "placa": placa,
                    "status": status,
                    "local": pirahy,
                    "id": id_vistoria,
                    "pre_ordem": pre_ordem,
                    "transportadora": transportadora
                })

        # app.py

# ... dentro de get_agend_v2_columns ...

        selected_data.sort(key=lambda x: (
            datetime.strptime(x.get("data", "01/01/2000"), '%d/%m/%Y'), 
            x.get("hora", "")
        ))

        if filter_date is None:
            CACHE_PENDENCIAS["data"] = selected_data
            
            # 🔴 MUDE DE: minutes=5 PARA: seconds=30
            CACHE_PENDENCIAS["expires"] = now + timedelta(seconds=30) 

        return selected_data
    
    except Exception as e:
        log.exception("❌ [SHEETS] Erro ao buscar pendencias: %s", e)
        return None

def classificar_data(data_str: str) -> str:
    if not data_str or not isinstance(data_str, str):
        return "indefinida"
    data_str = data_str.strip()
    formatos = ["%d/%m/%Y", "%d/%m/%Y %H:%M", "%Y-%m-%d"]
    for fmt in formatos:
        try:
            data = datetime.strptime(data_str, fmt).date()
            hoje = datetime.now().date()
            if data < hoje: return "Datas Anteriores"
            elif data == hoje: return "Data Atual"
            else: return "Datas Futuras"
        except ValueError:
            continue
    return "indefinida"

def extract_status(obj):
    return obj.get("status", "") if obj else ""

def montar_itens_inspecao(ii, pc, dv, tipo):
    itens = []
    def add(label, obj):
        if obj and obj.get("status"):
            itens.append({"pergunta": label, "resposta": obj.get("status")})

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
    pdf_path = os.path.join(tempfile.gettempdir(), f"vistoria_{uuid.uuid4().hex}.pdf")
    base_dir = os.path.dirname(os.path.abspath(__file__))
    HTML(string=html, base_url=base_dir).write_pdf(pdf_path)
    return pdf_path

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

def baixar_imagem_drive_base64(DRIVE_FOLDER_ID : str) -> str:
    if not DRIVE_FOLDER_ID: return ""
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
        placa_sheet = row[25] if len(row) > 25 else ""
        if placa_sheet == placa:
            return idx, row
    return None, None

def registrar_auditoria(placa, status_anterior, status_novo, motivo, vistoriador, data_agendada, hora_agendada, ip):
    linha = [
        datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        placa, status_anterior, status_novo, motivo, vistoriador,
        data_agendada, hora_agendada, ip
    ]
    sheets_service.values().append(
        spreadsheetId=SHEET_ID,
        range=AUDITORIA_TAB,
        valueInputOption="RAW",
        body={"values": [linha]}
    ).execute()

def achar_ou_criar_linha_por_id(id_vistoria: str):
    log.info("🔎 [SHEETS] Buscando ID: %s", id_vistoria)
    result = sheets_service.values().get(
        spreadsheetId=SHEET_ID,
        range=f"{SHEET_TAB}!A2:A5000"
    ).execute()
    values = result.get("values", [])
    for idx, row in enumerate(values, start=2):
        if row and row[0] == id_vistoria:
            return idx
    
    nova_linha = len(values) + 2
    log.info("➕ [SHEETS] ID novo, criando na linha %d", nova_linha)
    sheets_service.values().update(
        spreadsheetId=SHEET_ID,
        range=f"{SHEET_TAB}!A{nova_linha}",
        valueInputOption="RAW",
        body={"values": [[id_vistoria]]}
    ).execute()
    return nova_linha

# --------------------------------------------------------------------------
# PROCESSAMENTO PRINCIPAL
# --------------------------------------------------------------------------
def processar_vistoria(data: dict) -> dict:
    # Capturar placa e ID para o log de abertura
    id_log = data.get("id", "S/ID")
    placa_log = data.get("dadosIniciais", {}).get("placa1", "N/A")
    log.info("▶️ [PROCESS] Iniciando processamento | ID: %s | Placa: %s", id_log, placa_log)

    # DADOS INICIAIS
    di = data.get("dadosIniciais", {})
    ii = data.get("inspecaoInterna", {})
    pc = data.get("protecaoCarga", {})
    dv = data.get("detalhesVeiculo", {})
    fv = data.get("fotosVistoria", {})
    fin = data.get("finalizacao", {})
    id_vistoria = data.get("id", "")

    # UPLOAD FOTOS / ASSINATURAS
    uploaded = {}
    try:
        placas = fv.get("placas", {})
        # LOGS INTERNOS DO UPLOAD JÁ MOSTRAM TAMANHO
        uploaded["fotoPlaca1"] = upload_base64_to_drive(placas.get("fotoPlaca1"), "placa1")
        uploaded["fotoPlaca2"] = upload_base64_to_drive(placas.get("fotoPlaca2"), "placa2")
        uploaded["fotoPlaca3"] = upload_base64_to_drive(placas.get("fotoPlaca3"), "placa3")

        interior = fv.get("interiorCarroceria", {})
        uploaded["fotoInterior1"] = upload_base64_to_drive(interior.get("fotoInterior1"), "interior1")
        uploaded["fotoInterior2"] = upload_base64_to_drive(interior.get("fotoInterior2"), "interior2")

        uploaded["assinaturaMotorista"] = upload_base64_to_drive(fin.get("motoristaAssinatura"), "assinatura_motorista")
        uploaded["assinaturaVistoriador"] = upload_base64_to_drive(fin.get("vistoriadorAssinatura"), "assinatura_vistoriador")
        
        log.info("✅ [UPLOAD] Todas as imagens processadas")

    except Exception as e:
        log.exception("❌ [UPLOAD] Falha crítica: %s", e)
        raise

    # CONTEXTO PDF
    try:
        context = {
            "data": datetime.now().strftime("%d/%m/%Y"),
            "chegada": di.get("chegada", ""),
            "vistoria": di.get("vistoria", ""),
            "local_vistoria":di.get("localVistoria"),
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
    except Exception as e:
        log.exception("❌ [PDF] Erro ao criar contexto: %s", e)
        raise

    # VALIDAÇÃO ASSINATURAS
    try:
        validar_assinaturas(context)
    except Exception as e:
        log.exception("❌ [VALIDAR] Erro assinaturas: %s", e)
        raise

    # GERAR PDF
    try:
        pdf_path = gerar_pdf_vistoria(context)
        pdf_link = upload_file_to_drive(pdf_path, f"vistoria_{di.get('numeroOrdem','')}.pdf", "application/pdf")
        log.info("✅ [PDF] Gerado e enviado: %s", pdf_link)
    except Exception as e:
        log.exception("❌ [PDF] Falha na geração/envio: %s", e)
        raise

    # GOOGLE SHEETS - Mantendo a ordem EXATA que você tinha
    try:
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
            pdf_link,
            di.get("localVistoria")
        ]
        
        vistoria_queue = Queue(maxsize=100)
        sheet_lock = Lock()  # <--- CRIE ISSO AQUI 

        with sheet_lock:
            log.info("🔒 [SHEETS] Bloqueando planilha para escrita...")
            
            response = sheets_service.values().append(
                spreadsheetId=SHEET_ID,
                range=f"{SHEET_TAB}!A:ZZ",  # <--- FORÇA OLHAR A LINHA INTEIRA
                valueInputOption="RAW",
                insertDataOption="INSERT_ROWS", # <--- FORÇA EMPURRAR LINHAS PARA BAIXO
                body={"values": [linha]}
            ).execute()
            
            log.info("🔓 [SHEETS] Escrita concluída, liberando bloqueio.")

        updated_range = response["updates"]["updatedRange"]
        log.info("✅ [SHEETS] Linha gravada em %s", updated_range)

    except Exception as e:
        log.exception("❌ [SHEETS] Erro ao enviar para planilha: %s", e)
        raise
    invalidar_cache_pendencias()
    log.info("🏁 [PROCESS] Vistoria CONCLUÍDA | ID=%s", id_vistoria)
    return {"status": "ok", "id": id_vistoria, "pdf": pdf_link}

def salvar_backup_vistoria(payload: dict):
    try:
        di = payload.get("dadosIniciais", {})
        fv = payload.get("fotosVistoria", {})
        placa = (
            fv.get("placas", {}).get("placa1")
            or fv.get("placas", {}).get("placa2")
            or "SEM_PLACA"
        )
        placa = placa.replace(" ", "").upper()
        
        # Lógica original de data
        data_agendada = di.get("vistoria") or di.get("chegada") or datetime.now().strftime("%d/%m/%Y")
        try:
            data_fmt = datetime.strptime(data_agendada, "%d/%m/%Y")
        except ValueError:
            try:
                data_fmt = datetime.strptime(data_agendada, "%d/%m/%Y %H:%M")
            except:
                data_fmt = datetime.now()
        
        data_fmt = data_fmt.strftime("%Y-%m-%d")
        filename = f"{placa}_{data_fmt}.json"
        path = BACKUP_DIR / filename

        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        log.info("💾 [BACKUP] Salvo em: %s", path)

    except Exception as e:
        log.warning("⚠️ Falha ao salvar backup da vistoria: %s", e)

def worker():
    while True:
        payload, result_holder = vistoria_queue.get()
        STATUS["processing"] = True
        STATUS["current_id"] = payload.get("id")
        try:
            log.info("👷 [WORKER] Recebido payload da fila: %s", payload.get("id"))
            with app.app_context():
                salvar_backup_vistoria(payload)
                result_holder["response"] = processar_vistoria(payload)
                
                STATUS["processed"] += 1
                STATUS["last_success"] = datetime.utcnow()

        except Exception as e:
            log.exception("❌ [WORKER] Erro no processamento: %s", e)
            result_holder["error"] = str(e)
            STATUS["last_error"] = str(e)
        finally:
            STATUS["processing"] = False
            STATUS["current_id"] = None
            vistoria_queue.task_done()

Thread(target=worker, daemon=True).start()

# -------------------
# ENDPOINTS
# -------------------
@app.route("/api/status")
def status_endpoint(): # Renomeei levemente para não conflitar com var global, mas lógica igual
    return jsonify({
        "status": "online",
        "uptime_seconds": int((datetime.utcnow() - STATUS["started_at"]).total_seconds()),
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
    log.info("📞 GET / (Healthcheck)")
    return jsonify({"status": "API online"})

@app.get("/pendencias")
def pendencias():
    date_filter = request.args.get("data")

    force = request.args.get("force", "false").lower() == "true"

    data = get_agend_v2_columns(date_filter, force_refresh=force)

    if data is None:
        return jsonify({"status": "API online", "error": "Não foi possível acessar a planilha"}), 500

    return jsonify({
        "status": "API online",
        "pendentes": data,
        "total": len(data)
    })

@app.post("/vistoria")
def receive_vistoria():
    if not request.json:
        return jsonify({"error": "Payload vazio"}), 400

    result_holder = {}
    try:
        vistoria_queue.put((request.json, result_holder), timeout=5)
    except:
        return jsonify({"error": "Fila cheia, tente novamente"}), 503

    # AGUARDA PROCESSAMENTO (Lógica original de espera síncrona)
    while "response" not in result_holder and "error" not in result_holder:
        time.sleep(0.1)

    if "error" in result_holder:
        return jsonify({"error": result_holder["error"]}), 500

    return jsonify(result_holder["response"]), 200

@app.post("/cancelar")
def cancelar_vistoria():
    try:
        data = request.json
        log.info("🚫 [CANCEL] Payload: %s", data)

        id_vistoria = data.get("id")
        nome = data.get("nome")
        motivo = data.get("motivo")

        if not id_vistoria or not nome or not motivo:
            return jsonify({"error": "id, nome e motivo são obrigatórios"}), 400

        linha = achar_ou_criar_linha_por_id(id_vistoria)

        sheets_service.values().update(         #ENVIA PARA STATUS
            spreadsheetId=SHEET_ID,
            range=f"{SHEET_TAB}!B{linha}",
            valueInputOption="RAW",
            body={"values": [["Cancelada"]]}
        ).execute()

        sheets_service.values().update(         #ENVIA PARA OBSERVAÇÔES
            spreadsheetId=SHEET_ID,
            range=f"{SHEET_TAB}!AP{linha}",
            valueInputOption="RAW",
            body={"values": [[motivo]]}
        ).execute()

        sheets_service.values().update(         #ENVIA PARA NOME DO VISTORIADOR
            spreadsheetId=SHEET_ID,
            range=f"{SHEET_TAB}!AE{linha}",
            valueInputOption="RAW",
            body={"values": [[nome]]}
        ).execute()

        log.info("✅ [CANCEL] OK | ID=%s | linha=%d", id_vistoria, linha)
        invalidar_cache_pendencias()
        return jsonify({
            "status": "ok",
            "id": id_vistoria,
            "linha": linha
        }), 200

    except Exception as e:
        log.exception("❌ [CANCEL] Erro ao cancelar vistoria")
        return jsonify({"error": str(e)}), 500


@app.before_request
def log_request():
    if request.path != "/api/status": # Evita flood de log do status
        log.info("➡️ %s %s", request.method, request.path)

if __name__ == "__main__":
    log.info("🚀 SUBINDO API FLASK")
    HOST = os.getenv("API_HOST", "0.0.0.0")
    PORT = int(os.getenv("API_PORT", 5000))
    app.run(host=HOST, port=PORT)