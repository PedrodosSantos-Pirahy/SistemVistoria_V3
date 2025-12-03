# ---------- ENVIAR PARA APP/WEB ---------- 
# http://127.0.0.1:5000/pendencias
from flask import Flask, jsonify, request
import os
from datetime import datetime

from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID", "1OypeFbnDkBMWNYSqH36DJYtR8l4lapWwG9j44fdzTXw")


# ---- autenticação OAuth segura ----
def get_credentials():
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)

        with open("token.json", "w") as token:
            token.write(creds.to_json())

    return creds


# ---- função Sheets com filtro por data ----
def get_agend_v2_columns(filter_date=None):
    try:
        creds = get_credentials()
        service = build("sheets", "v4", credentials=creds)

        range_name = "Agend_V2!A2:Z200"
        result = service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID, range=range_name
        ).execute()

        values = result.get("values", [])
        if not values:
            return []

        hoje_str = filter_date or datetime.today().strftime("%d/%m/%Y")
        selected_data = []

        for row in values:
            date_value = row[1] if len(row) > 1 else ""
            status = row[10] if len(row) > 10 else ""  # coluna K
            placa = row[25] if len(row) > 25 else ""   # coluna Z

            if date_value == hoje_str and status.strip().lower() != "concluida":
                selected_data.append(placa)

        return selected_data

    except Exception as e:
        print("Erro ao acessar o Google Sheets:", e)
        return None


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


@app.get("/")
def home():
    return jsonify({"status": "API online"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
