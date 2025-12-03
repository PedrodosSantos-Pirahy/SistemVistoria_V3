from flask import Flask, request, jsonify
from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials
import base64

SHEET_ID = "SEU_ID_DA_PLANILHA"  # <-- troque pelo ID real
SHEET_TAB = "Protec!C2:AN"       # destino (C até AN)

app = Flask(__name__)

# Escopo para Sheets
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# Credenciais (service-account.json deve estar na pasta)
creds = Credentials.from_service_account_file("service-account.json", scopes=SCOPES)
sheet_service = build("sheets", "v4", credentials=creds).spreadsheets()


def extract_status(obj):
    """ Pega .status ou retorna vazio """
    return obj.get("status", "") if obj else ""


@app.post("/vistoria")
def receive_vistoria():
    data = request.get_json()

    try:
        di = data["dadosIniciais"]
        ii = data["inspecaoInterna"]
        pc = data["protecaoCarga"]
        dv = data["detalhesVeiculo"]
        fv = data["fotosVistoria"]
        fin = data["finalizacao"]

        row = [
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

            fv["placas"].get("placa1", ""),
            fv["placas"].get("fotoPlaca1", ""),
            fv["placas"].get("placa2", ""),
            fv["placas"].get("fotoPlaca2", ""),
            fv["placas"].get("placa3", ""),
            fv["placas"].get("fotoPlaca3", ""),

            fv["interiorCarroceria"].get("fotoInterior1", ""),
            fv["interiorCarroceria"].get("fotoInterior2", ""),

            fin.get("controleQualidadeNome", "")
        ]

        sheet_service.values().append(
            spreadsheetId=SHEET_ID,
            range=SHEET_TAB,
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": [row]}
        ).execute()

        return jsonify({"message": "vistoria registrada com sucesso", "status": "ok"})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True)
