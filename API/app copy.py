from flask import Flask, request, jsonify
from flask_cors import CORS
import logging
import tempfile
import base64
import re
import io
from datetime import datetime

#PDF
from flask import render_template
from weasyprint import HTML
import os
import uuid

from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials
from googleapiclient.http import MediaFileUpload
from googleapiclient.http import MediaIoBaseDownload

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
SERVICE_ACCOUNT_FILE = r"C:\DEV\Sistema Vistorias - Pirahy\SistemVistoria_V3\API\service-account.json"
SHEET_ID = "1OypeFbnDkBMWNYSqH36DJYtR8l4lapWwG9j44fdzTXw"
SHEET_TAB = "Protec"
AUDITORIA_TAB = "Auditoria"

#Comparar
#1OypeFbnDkBMWNYSqH36DJYtR8l4lapWwG9j44fdzTXw
#1OypeFbnDkBMWNYSqH36DJYtR8l4lapWwG9j44fdzTXw
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID", "1OypeFbnDkBMWNYSqH36DJYtR8l4lapWwG9j44fdzTXw")

# Pasta/Unidade destino no Drive (pode ser Shared Drive). A service account deve ter acesso.
DRIVE_FOLDER_ID = "0AKLd3H4beidVUk9PVA"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)

drive_service = build("drive", "v3", credentials=creds)
sheets_service = build("sheets", "v4", credentials=creds).spreadsheets()

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


def get_agend_v2_columns(filter_date=None):
    try:
        service = sheets_service

        range_name = "Agend_V2!A1:AZ"
 # ATENÇÃO AO NUMERO MAXIMO DO RANGE !!!!!!!!!!!!!!!!!!!!!
        result = service.values().get(
            spreadsheetId=SPREADSHEET_ID,
            range=range_name
        ).execute()

        values = result.get("values", [])
        if not values:
            return []

        hoje_str = filter_date or datetime.today().strftime("%d/%m/%Y")
        selected_data = []

        for row in values:
            date_value = row[1] if len(row) > 1 else ""
            status = row[10] if len(row) > 10 else ""   # coluna K
            placa = row[25] if len(row) > 25 else ""    # coluna Z
            hora  = row[0] if len(row) > 0 else ""   
            id_vistoria = row[24] if len(row) > 24 else ""   # exemplo: coluna A

            if date_value == hoje_str and status.strip().lower() != "concluida":
                selected_data.append({
                    "placa": placa,
                    "status": status,
                    "id": id_vistoria
                })

        return selected_data

    except Exception as e:
        log.exception("Erro Sheets: %s", e)
        return None

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
    obrigatorias = ["cq", "motorista", "vistoriador"]
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

    log.info("Buscando ID na Protec: %s", id_vistoria)

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




# -------------------
# ENDPOINTS
# -------------------
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
    try:
        data = request.json

        # --------------------
        # DADOS INICIAIS
        # --------------------
        di = data.get("dadosIniciais", {})
        ii = data.get("inspecaoInterna", {})
        pc = data.get("protecaoCarga", {})
        dv = data.get("detalhesVeiculo", {})
        fv = data.get("fotosVistoria", {})
        fin = data.get("finalizacao", {})

        #--------------------
        # PEGAR O ID
        #--------------------
        id_vistoria = data.get("id", "")
        log.info("ID RECEBIDO NO /vistoria: %s", data.get("id"))

        # --------------------
        # UPLOAD FOTOS / ASSINATURAS
        # --------------------
        uploaded = {}

        # Placas
        placas = fv.get("placas", {})
        uploaded["fotoPlaca1"] = upload_base64_to_drive(placas.get("fotoPlaca1"), "placa1")
        uploaded["fotoPlaca2"] = upload_base64_to_drive(placas.get("fotoPlaca2"), "placa2")
        uploaded["fotoPlaca3"] = upload_base64_to_drive(placas.get("fotoPlaca3"), "placa3")

        # Interior carroceria
        interior = fv.get("interiorCarroceria", {})
        uploaded["fotoInterior1"] = upload_base64_to_drive(interior.get("fotoInterior1"), "interior1")
        uploaded["fotoInterior2"] = upload_base64_to_drive(interior.get("fotoInterior2"), "interior2")

        # Assinaturas
        uploaded["assinaturaCQ"] = upload_base64_to_drive(fin.get("controleQualidadeAssinatura"), "assinatura_cq")
        uploaded["assinaturaMotorista"] = upload_base64_to_drive(fin.get("motoristaAssinatura"), "assinatura_motorista")
        uploaded["assinaturaVistoriador"] = upload_base64_to_drive(fin.get("vistoriadorAssinatura"), "assinatura_vistoriador")

        # --------------------
        # MONTAR CONTEXTO PARA PDF
        # --------------------
        context = {
            # Metadados
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

            # Placas
            "placas": [
                placas.get("placa1", ""),
                placas.get("placa2", ""),
                placas.get("placa3", "")
            ],

            # Resultados inspeção interna
            "limpeza": extract_status(ii.get("limpeza")),
            "danos": extract_status(ii.get("danos")),
            "umidade": extract_status(ii.get("umidade")),
            "residuos": extract_status(ii.get("residuos")),
            "odores": extract_status(ii.get("odores")),
            "bocas_graneleiras": extract_status(ii.get("bocasGraneleiras")),
            "lonas": extract_status(ii.get("lonas")),
            "chapas_mdf": extract_status(ii.get("chapasMdf")),

            # Proteção de carga
            "lonas_protecao": extract_status(pc.get("lonasProtecao")),
            "equipamentos": extract_status(pc.get("equipamentos")),
            "tampas_laterais": extract_status(pc.get("tampasLaterais")),

            # Condicionais
            "bau_altura_porta": extract_status(dv.get("caminhaoBau", {}).get("alturaPorta")),
            "bau_largura_porta": extract_status(dv.get("caminhaoBau", {}).get("larguraPorta")),
            "bau_assoalho": extract_status(dv.get("caminhaoBau", {}).get("assoalhoLiso")),
            "container_peso": extract_status(dv.get("container", {}).get("verificacaoPeso")),

            # Observações
            "observacoes": fin.get("observacoes", ""),

            # Assinaturas
            "assinaturas": {
                "cq": {
                    "nome": fin.get("controleQualidadeNome", ""),
                    "imagem": uploaded.get("assinaturaCQ", "")
                },
                "motorista": {
                    "nome": fin.get("motoristaNome", ""),
                    "imagem": uploaded.get("assinaturaMotorista", "")
                },
                "vistoriador": {
                    "nome": fin.get("vistoriadorNome", ""),
                    "imagem": uploaded.get("assinaturaVistoriador", "")
                }
            }
        }

        log.info("Contexto PDF: %s", context)

        # --------------------
        # VALIDAÇÃO OBRIGATÓRIA DE ASSINATURAS
        # --------------------
        validar_assinaturas(context)

        # --------------------
        # GERAR PDF
        # --------------------
        pdf_path = gerar_pdf_vistoria(context)
        log.info("PDF gerado: %s | Existe? %s", pdf_path, os.path.exists(pdf_path))

        pdf_link = upload_file_to_drive(pdf_path, f"vistoria_{di.get('numeroOrdem','')}.pdf", "application/pdf")

        # --------------------
        # SALVAR NO GOOGLE SHEETS
        # --------------------
        linha = [
            id_vistoria, 
            "CONCLUIDO",  # Colunas A e B vazias
            di.get("chegada", ""),
            di.get("vistoria", ""),
            di.get("fim", ""),
            di.get("numeroOrdem", ""),
            di.get("transportadora", ""),
            di.get("operacao", ""),
            di.get("produto", ""),
            di.get("ultimosProdutos", ""),
            di.get("tipoVeiculo", ""),

            # Inspeção interna
            extract_status(ii.get("limpeza")),
            extract_status(ii.get("danos")),
            extract_status(ii.get("umidade")),
            extract_status(ii.get("residuos")),
            extract_status(ii.get("odores")),
            extract_status(ii.get("bocasGraneleiras")),
            extract_status(ii.get("lonas")),
            extract_status(ii.get("chapasMdf")),

            # Proteção de carga
            extract_status(pc.get("lonasProtecao")),
            extract_status(pc.get("equipamentos")),
            extract_status(pc.get("tampasLaterais")),

            # Condicionais
            extract_status(dv.get("caminhaoBau", {}).get("alturaPorta")),
            extract_status(dv.get("caminhaoBau", {}).get("larguraPorta")),
            extract_status(dv.get("caminhaoBau", {}).get("assoalhoLiso")),
            extract_status(dv.get("container", {}).get("verificacaoPeso")),

            # Nomes e assinaturas
            fin.get("controleQualidadeNome", ""),
            uploaded.get("assinaturaCQ", ""),
            fin.get("motoristaNome", ""),
            uploaded.get("assinaturaMotorista", ""),
            fin.get("vistoriadorNome", ""),
            uploaded.get("assinaturaVistoriador", ""),

            # Placas e fotos
            placas.get("placa1", ""),
            uploaded.get("fotoPlaca1", ""),
            placas.get("placa2", ""),
            uploaded.get("fotoPlaca2", ""),
            placas.get("placa3", ""),
            uploaded.get("fotoPlaca3", ""),

            # Interior fotos
            uploaded.get("fotoInterior1", ""),
            uploaded.get("fotoInterior2", ""),

            # Final
            fin.get("caminhaoLiberado", ""),
            fin.get("observacoes", ""),
            pdf_link
        ]

        log.info("PDF link salvo no Sheets: %s", linha[-1])
        log.info("Total de colunas na linha: %d", len(linha))

        sheets_service.values().append(
            spreadsheetId=SHEET_ID,
            range=SHEET_TAB,
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": [linha]}
        ).execute()

        log.info("Linha inserida no Sheets com sucesso")

        return jsonify({"status": "ok", "pdf": pdf_link}), 200

    except ValueError as ve:
        log.error(f"Erro de validação: {ve}")
        return jsonify({"erro": str(ve)}), 400
    except Exception as e:
        log.exception("Erro ao processar vistoria")
        return jsonify({"error": str(e)}), 500

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
            body={"values": [["CANCELADO"]]}
        ).execute()

        sheets_service.values().update(
            spreadsheetId=SHEET_ID,
            range=f"{SHEET_TAB}!AR{linha}",  # MOTIVO
            valueInputOption="RAW",
            body={"values": [[motivo]]}
        ).execute()

        sheets_service.values().update(
            spreadsheetId=SHEET_ID,
            range=f"{SHEET_TAB}!AS{linha}",  # VISTORIADOR
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


# --------------------------------------------------------------------------
# RUN
# --------------------------------------------------------------------------
if __name__ == "__main__":
    log.info("Inicializando API...")
    app.run(host="192.168.53.193", port=5000, debug=True)