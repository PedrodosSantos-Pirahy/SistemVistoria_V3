import os
from datetime import datetime
from weasyprint import HTML
from jinja2 import Environment, FileSystemLoader

# ---------------------------
# CONFIGURAÇÃO DE DIRETÓRIOS
# ---------------------------
# Pega o diretório onde este script está localizado
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

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
    "produto": "KNORR CARNE DE PANELA 81 FD30 / KNORR GALINHA CAIPIRA 108 FD30 / P.FINO BRANCO 6X5 - 1260 FD30 / P.FINO INTEGRAL 10X1 - 10.00 FD30",
    "ultimos_produtos": "Areia, Pedra, Tijolo",
    "tipo_veiculo": "Baú",
    "status_final": "APROVADO",
    "placas": ["ABC-1234", "DEF-5678", ""],
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
        "motorista": {"nome": "João Motorista", "imagem": ""},
        "vistoriador": {"nome": "Carlos Vistoriador", "imagem": ""}
    }
}

# ---------------------------
# GERAR PDF USANDO TEMPLATE vistoria_pdf.html
# ---------------------------
try:
    # Configura o Jinja2 para ler o template na mesma pasta do script
    env = Environment(loader=FileSystemLoader(BASE_DIR))
    
    # Carrega o arquivo HTML (deve estar na mesma pasta)
    template = env.get_template("vistoria_pdf.html")
    
    # Renderiza o HTML com os dados do contexto
    html_rendered = template.render(context)

    # Define o nome e o caminho do arquivo de saída
    nome_arquivo = f"vistoria_teste_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    caminho_saida = os.path.join(BASE_DIR, nome_arquivo)

    # Gera o PDF
    print("Gerando PDF...")
    HTML(string=html_rendered, base_url=BASE_DIR).write_pdf(caminho_saida)

    print("-" * 30)
    print(f"✅ SUCESSO! PDF gerado em:")
    print(f"📂 {caminho_saida}")
    print("-" * 30)

except Exception as e:
    print(f"❌ Erro ao gerar o PDF: {e}")