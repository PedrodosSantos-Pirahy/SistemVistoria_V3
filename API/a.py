from flask import Flask, request, jsonify
from flask_cors import CORS
import logging
from datetime import datetime
from pathlib import Path
import os
import json

# Google Sheets
from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials
from google_auth_httplib2 import AuthorizedHttp
import httplib2

# --------------------------------------------------------------------------
# CONFIGURAÇÃO DE LOGS (LIMPO E PADRONIZADO)
# --------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt='%H:%M:%S')
log = logging.getLogger("historico-api")

# 🤫 Silenciar bibliotecas externas
logging.getLogger("googleapiclient").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("oauth2client").setLevel(logging.WARNING)

log.info("=== 📜 HISTÓRICO API: DEBUG INICIAL ===")
log.info("Diretório atual (cwd): %s", os.getcwd())

# --------------------------------------------------------------------------
# Config Flask
# --------------------------------------------------------------------------
app = Flask(__name__)
CORS(app)

# --------------------------------------------------------------------------
# Config Google Sheets / Service Account
# --------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
SERVICE_ACCOUNT_PATH = BASE_DIR / "service-account.json"

log.info("SERVICE ACCOUNT: %s", SERVICE_ACCOUNT_PATH)

if not SERVICE_ACCOUNT_PATH.exists():
    log.critical("❌ Service account não encontrado!")
    raise RuntimeError(f"Service account não encontrado: {SERVICE_ACCOUNT_PATH}")

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

creds = Credentials.from_service_account_file(
    SERVICE_ACCOUNT_PATH,
    scopes=SCOPES
)

http = httplib2.Http(timeout=60)
authed_http = AuthorizedHttp(creds, http=http)

sheets_service = build(
    "sheets",
    "v4",
    http=authed_http,
    cache_discovery=False
).spreadsheets()

# --------------------------------------------------------------------------
# Configurações do Sheet
# --------------------------------------------------------------------------
SHEET_ID = os.getenv("SHEET_ID", "1OypeFbnDkBMWNYSqH36DJYtR8l4lapWwG9j44fdzTXw")
HISTORICO_TAB = "Agend_V2"

# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def validar_payload(payload: dict) -> bool:
    obrigatorios = ["ID", "Pré-Ordem", "Vistoriador", "Placa"]
    missing = [k for k in obrigatorios if k not in payload]
    if missing:
        log.warning("⚠️ [VALIDAR] Campos faltando: %s", missing)
    return len(missing) == 0


def sheets_append_row(values: list):
    """Insere uma linha no Google Sheets"""
    log.info("📝 [SHEETS] Inserindo nova linha...")
    body = {"values": [values]}
    result = sheets_service.values().append(
        spreadsheetId=SHEET_ID,
        range=f"{HISTORICO_TAB}!A2:AB5000",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body=body
    ).execute()
    updated_range = result["updates"]["updatedRange"]
    log.info("✅ [SHEETS] Linha inserida com sucesso: %s", updated_range)
    return updated_range


def sheets_read_rows():
    """Lê todas as linhas do histórico do Sheets"""
    log.info("🔄 [SHEETS] Lendo histórico completo...")
    result = sheets_service.values().get(
        spreadsheetId=SHEET_ID,
        range=f"{HISTORICO_TAB}!A2:AB5000"
    ).execute()
    values = result.get("values", [])
    log.info("✅ [SHEETS] Total de linhas lidas: %d", len(values))
    return values


def safe_get(r, idx):
    return r[idx] if len(r) > idx else ""


# --------------------------------------------------------------------------
# Endpoints
# --------------------------------------------------------------------------
@app.get("/")
def home():
    log.info("📞 GET / (Healthcheck)")
    return jsonify({"status": "API de Histórico online"})


@app.post("/historico")
def criar_historico():
    payload = request.json
    if not payload:
        log.warning("⚠️ [POST] Payload vazio recebido")
        return jsonify({"error": "Payload vazio"}), 400

    log.info("➕ [POST] Nova solicitação | ID: %s | Placa: %s", payload.get("ID"), payload.get("Placa"))

    if not validar_payload(payload):
        return jsonify({"error": "Campos obrigatórios ausentes"}), 400

    payload["data"] = payload.get("data") or datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    row = [
        payload["ID"],
        payload["Placa"],
        payload["Data"],
        payload["Hora Inicio"],
        payload["po"],
        payload["Transportadora"],
        payload["vr"],
        payload["cl"],
        payload["Vistoriador"],
        payload["PDF"]
    ]

    try:
        sheets_append_row(row)
    except Exception as e:
        log.exception("❌ [POST] Erro crítico ao salvar no Sheets")
        return jsonify({"error": str(e)}), 500

    log.info("✅ [POST] Histórico salvo com sucesso.")
    return jsonify({"status": "ok", "historico": payload}), 201


@app.get("/historico")
def listar_historico():
    filtro_id = request.args.get("id")
    log.info("🔍 [GET] Listando histórico | Filtro ID: %s", filtro_id if filtro_id else "TODOS")

    try:
        rows = sheets_read_rows()
    except Exception as e:
        log.exception("❌ [GET] Erro ao ler do Sheets")
        return jsonify({"error": str(e)}), 500

    historico = []

    for r in rows:
        # Ignora linhas que sejam títulos ou vazias (Mantido lógica original)
        if not r or r[0] == "Placa":
            continue

        item = {
            "ID": safe_get(r, 24),
            "Placa": safe_get(r, 0),
            "Data": safe_get(r, 1),
            "Hora Inicio": safe_get(r, 2),
            "Hora Fim": safe_get(r, 3),
            "po": safe_get(r, 4),
            "Transportadora": safe_get(r, 5),
            "vr": safe_get(r, 10),
            "cl": safe_get(r, 11),
            "Vistoriador": safe_get(r, 12),
            "PDF": safe_get(r, 27)
        }

        # Correção pequena: usei .get("ID") para garantir consistência com o objeto criado acima
        # Se sua planilha usa ID na coluna 24, a lógica está mantida.
        if filtro_id and item["ID"] != filtro_id:
            continue

        historico.append(item)

    log.info("✅ [GET] Retornando %d registros", len(historico))
    return jsonify({"status": "ok", "total": len(historico), "historico": historico})


# --------------------------------------------------------------------------
# Run
# --------------------------------------------------------------------------
if __name__ == "__main__":
    log.info("🚀 SUBINDO API DE HISTÓRICO (DEV)")
    # Host e Porta originais
    app.run(host="0.0.0.0", port=5002)