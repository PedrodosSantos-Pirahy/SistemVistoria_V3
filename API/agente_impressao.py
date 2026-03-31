from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import subprocess
import tempfile

app = Flask(__name__)
# Permite que o Tablet (Angular) consiga falar com este PC
CORS(app)

print("----------------------------------------------------------")
print("🖨️  AGENTE DE IMPRESSÃO INICIADO NA PORTA 5005")
print("📡 Aguardando ordens dos Tablets...")
print("----------------------------------------------------------")

@app.route('/imprimir', methods=['POST'])
def imprimir_pdf():
    try:
        # 1. Recebe o ficheiro PDF e o nome da impressora do Tablet
        if 'arquivo' not in request.files:
            return jsonify({"error": "Nenhum arquivo recebido!"}), 400
            
        arquivo = request.files['arquivo']
        impressora = request.form.get('impressora', '')

        if not impressora:
            return jsonify({"error": "Nome da impressora não informado!"}), 400

        # 2. Salva o PDF temporariamente no Windows
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            arquivo.save(tmp.name)
            caminho_temporario = tmp.name

        # 3. Chama o SumatraPDF para imprimir
        caminho_sumatra = os.path.join(os.path.dirname(__file__), "SumatraPDF.exe")
        
        if not os.path.exists(caminho_sumatra):
            return jsonify({"error": "SumatraPDF.exe não encontrado na pasta!"}), 500

        # Manda para a impressora escolhida pelo utilizador!
        comando = [caminho_sumatra, "-print-to", impressora, "-silent", caminho_temporario]
        subprocess.run(comando, check=True)

        # 4. Limpa o lixo
        if os.path.exists(caminho_temporario):
            os.remove(caminho_temporario)

        return jsonify({"message": f"Impresso com sucesso na {impressora}!"}), 200

    except Exception as e:
        print(f"❌ Erro: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    # Roda na porta 5005 para não dar conflito com nada
    app.run(host='0.0.0.0', port=5001, debug=True)