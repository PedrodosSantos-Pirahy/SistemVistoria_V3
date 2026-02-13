from dotenv import load_dotenv
from flask import Flask, request, jsonify, make_response
from flask_cors import CORS
import psycopg2
from datetime import datetime, timedelta
import traceback
import sys
import os
import base64
import io
import bcrypt
from PIL import Image, ImageOps
from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML

# pasta_atual = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__)#, template_folder=pasta_atual)

# Configuração CORS
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)

# DB_CONFIG = {
#     "host": "192.168.10.10",
#     "database": "PgPirahyHML",
#     "user": "PEDROK",
#     "password": "0912",
#     "port": "5432"  
# }
load_dotenv()

DB_BUSCA = {
    "host": os.getenv("DB_HOST"),
    "database": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASS"),
    "port": os.getenv("DB_PORT")
}

# Log para avisar que o servidor iniciou
print("----------------------------------------------------------")
print("🚀 SERVIDOR PYTHON INICIADO NA PORTA 5000 (MODO UNIFICADO)")
print("📡 Aguardando conexões no DB_BUSCA...")
print("----------------------------------------------------------")

#-------------------------HELPERS /vistoria-------------------------
# Configuração de Upload
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def formatar_data_pdf(data_iso):
    """Converte 2026-02-03T10:00 para 03/02/2026"""
    if not data_iso: return ""
    try:
        if "T" in data_iso:
            return datetime.strptime(data_iso, "%Y-%m-%dT%H:%M").strftime("%d/%m/%Y %H:%M")
        return datetime.strptime(data_iso, "%Y-%m-%d").strftime("%d/%m/%Y")
    except:
        return data_iso

def compactar_imagem(file_storage, max_size_kb=200):
    """
    Lê um arquivo de imagem, converte para JPEG, redimensiona e comprime.
    """
    try:
        img = Image.open(file_storage)
        img = ImageOps.exif_transpose(img)
        
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
            
        max_dimension = 1280 
        if img.height > max_dimension or img.width > max_dimension:
            img.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
            
        quality = 85
        output_io = io.BytesIO()
        
        while quality > 10:
            output_io.seek(0)
            output_io.truncate()
            img.save(output_io, format='JPEG', quality=quality, optimize=True)
            
            size_kb = output_io.tell() / 1024
            if size_kb <= max_size_kb:
                break
            
            quality -= 10
            
        return output_io.getvalue()

    except Exception as e:
        print(f"⚠️ Erro ao compactar imagem: {e}")
        file_storage.seek(0)
        return file_storage.read()

#-------------------------HELPERS /pendencias-------------------------
def classificar_data_db(data_obj):
    if not data_obj: return "indefinida"
    hoje = datetime.now().date()
    data_comparar = data_obj.date() if isinstance(data_obj, datetime) else data_obj
    
    if data_comparar < hoje: return "Datas Anteriores"
    elif data_comparar == hoje: return "Data Atual"
    else: return "Datas Futuras"

def get_pendencias_db(filter_date=None):
    conn = None
    try:
        # 🔥 ALTERAÇÃO: Conecta no DB_BUSCA
        conn = psycopg2.connect(**DB_BUSCA)
        cur = conn.cursor()

        sql = """
            SELECT 
                a.id, a.placa, a.data, a.hr_inicio, a.local, 
                CONCAT_WS(', ', NULLIF(a.pre_ordem1,''), NULLIF(a.pre_ordem2,''), NULLIF(a.pre_ordem3,''), NULLIF(a.pre_ordem4,''), NULLIF(a.pre_ordem5,'')) as todas_ordens,
                COALESCE(y."TRP_NOME", 'Consultar Cadastro') as transportadora_oficial
            FROM "vistoria"."VAGENDAMENTO" a
            LEFT JOIN "UTRAPLACA" x ON REGEXP_REPLACE(UPPER(a.placa), '[^A-Z0-9]', '', 'g') = REGEXP_REPLACE(UPPER(x."PLA_PLACA"), '[^A-Z0-9]', '', 'g')
            LEFT JOIN "UTRAPROPR" y ON x."PLA_PROPR" = y."TRP_CODIGO"
            WHERE a.data >= CURRENT_DATE
            AND NOT EXISTS (
                SELECT 1 FROM "vistoria"."VRESPOSTAS" r 
                WHERE CAST(r.id_agend AS VARCHAR) = CAST(a.id AS VARCHAR)
                AND r.status IN ('Concluída', 'Concluida', 'Cancelada')
            )
            ORDER BY a.data ASC, a.hr_inicio ASC
        """
        
        cur.execute(sql)
        rows = cur.fetchall()
        
        pendencias = []
        agora = datetime.now()
        hoje = agora.date()

        for row in rows:
            db_id, db_placa, db_data, db_hora, db_local, db_ordens_concat, db_transp = row

            # Formata a data aqui (Ex: "12/02/2026")
            data_visivel = db_data.strftime("%d/%m/%Y") if db_data else ""
            hora_visivel = str(db_hora)[:5] if db_hora else "00:00"

            try:
                hora_obj = datetime.strptime(hora_visivel, "%H:%M").time()
                data_hora_agendamento = datetime.combine(db_data, hora_obj)
            except:
                data_hora_agendamento = datetime.combine(db_data, datetime.max.time())

            # --- LÓGICA DO STATUS ---
            status_temp = "Pendente"
            
            if db_data > hoje: 
                status_temp = data_visivel  # 🔥 AQUI A MUDANÇA: Usa a string formatada
            elif db_data == hoje:
                diferenca = (data_hora_agendamento - agora).total_seconds() / 60
                if diferenca < -20: status_temp = "Expirado"
                elif diferenca <= 0: status_temp = "Aguardando"
                elif diferenca <= 60: status_temp = "Em Breve"
                else: status_temp = "Em Breve"

            if filter_date and data_visivel != filter_date: continue

            pendencias.append({
                "id": str(db_id),
                "placa": db_placa or "SEM PLACA",
                "data": data_visivel,
                "categoria_data": classificar_data_db(db_data),
                "hora": hora_visivel,
                "local": db_local or "Matriz",
                "status": status_temp,
                "pre_ordem": db_ordens_concat or "",
                "transportadora": db_transp 
            })

        return pendencias

    except Exception as e:
        print("❌ [DB] Erro ao buscar pendências:", e)
        traceback.print_exc()
        return []
    finally:
        if conn: conn.close()

# Middleware para logar
@app.before_request
def log_request_info():
    if request.method != 'OPTIONS':
        print(f"\n🔔 [REQ] {request.method} {request.path}")
    
    if request.method == "OPTIONS":
        response = make_response()
        response.headers.add("Access-Control-Allow-Origin", "*")
        response.headers.add("Access-Control-Allow-Headers", "Content-Type, Authorization, Cache-Control, Pragma")
        response.headers.add("Access-Control-Allow-Methods", "POST, GET, OPTIONS, PUT, DELETE")
        return response

# --- ROTAS ---

@app.route('/consultar-placa/<placa>', methods=['GET'])
def consultar_placa(placa):
    conn = None
    try:
        # 🔥 ALTERAÇÃO: Conecta no DB_BUSCA
        conn = psycopg2.connect(**DB_BUSCA)
        cur = conn.cursor()

        placa_limpa = placa.upper().replace("-", "").strip()

        sql = """
            SELECT y."TRP_NOME"
            FROM "UTRAPLACA" x
            INNER JOIN "UTRAPROPR" y ON x."PLA_PROPR" = y."TRP_CODIGO"
            WHERE REGEXP_REPLACE(UPPER(x."PLA_PLACA"), '[^A-Z0-9]', '', 'g') = %s
            LIMIT 1
        """
        
        cur.execute(sql, (placa_limpa,))
        resultado = cur.fetchone()

        if resultado:
            return jsonify({"transportadora": resultado[0]}), 200
        else:
            return jsonify({"error": "Placa não encontrada"}), 404

    except Exception as e:
        print(f"❌ Erro ao consultar placa: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if conn: conn.close()

@app.route('/criar-agendamento', methods=['POST'])
def criar_agendamento():
    conn = None
    print("👉 Entrou na função 'criar_agendamento'")
    
    try:
        dados = request.json
        if not dados: return jsonify({"error": "Nenhum dado recebido"}), 400

        print("⏳ Processando datas...")
        formato_hora = "%H:%M"
        hr_inicio_str = str(dados['hora_inicio'])[:5] 
        dt_inicio = datetime.strptime(hr_inicio_str, formato_hora)
        duracao = int(dados['duracao_minutos'])
        dt_fim = dt_inicio + timedelta(minutes=duracao)
        str_hr_fim = dt_fim.strftime(formato_hora)

        lista_ordens = dados.get('pre_ordens', [])
        ordens_db = [None] * 5
        for i, ordem in enumerate(lista_ordens[:5]):
            ordens_db[i] = ordem

        # 🔥 ALTERAÇÃO: Conecta no DB_BUSCA
        print("🔌 Conectando ao DB_BUSCA...")
        conn = psycopg2.connect(**DB_BUSCA)
        cur = conn.cursor()

        sql = """
            INSERT INTO "vistoria"."VAGENDAMENTO" 
            (placa, data, hr_inicio, hr_fim, local, pre_ordem1, pre_ordem2, pre_ordem3, pre_ordem4, pre_ordem5)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id;
        """

        valores = (
            dados['placa'], dados['data_agendamento'], dados['hora_inicio'], str_hr_fim,
            dados.get('local', 'Matriz'), ordens_db[0], ordens_db[1], ordens_db[2], ordens_db[3], ordens_db[4]
        )

        cur.execute(sql, valores)
        novo_id = cur.fetchone()[0]
        conn.commit()

        print(f"🎉 SUCESSO! Agendamento criado ID: {novo_id}")
        return jsonify({"message": "Agendado com sucesso!", "id": novo_id}), 200

    except Exception as e:
        print("❌ ERRO CRÍTICO:", e)
        if conn: conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        if conn: conn.close()

@app.get("/pendencias")
def pendencias():
    date_filter = request.args.get("data")
    data = get_pendencias_db(date_filter)
    if data is None: data = []
    return jsonify({"status": "API online (DB)", "pendentes": data, "total": len(data)})

# --- ROTA PARA BUSCAR DADOS DE CARGA (UNIFICADA) ---
@app.route('/dados-carga/<placa>', methods=['GET'])
def get_dados_carga(placa):
    conn = None
    try:
        placa_limpa = placa.upper().replace("-", "").strip()
        
        # 🔥 ALTERAÇÃO: Conecta no DB_BUSCA
        conn = psycopg2.connect(**DB_BUSCA)
        cur = conn.cursor()

        # 1. Busca as Pré-Ordens na tabela de Agendamento
        sql = """
            SELECT 
                a.pre_ordem1, a.pre_ordem2, a.pre_ordem3, a.pre_ordem4, a.pre_ordem5,
                COALESCE(y."TRP_NOME", 'Transportadora não identificada') as transportadora
            FROM "vistoria"."VAGENDAMENTO" a
            LEFT JOIN "UTRAPLACA" x ON REGEXP_REPLACE(UPPER(a.placa), '[^A-Z0-9]', '', 'g') = REGEXP_REPLACE(UPPER(x."PLA_PLACA"), '[^A-Z0-9]', '', 'g')
            LEFT JOIN "UTRAPROPR" y ON x."PLA_PROPR" = y."TRP_CODIGO"
            WHERE REGEXP_REPLACE(UPPER(a.placa), '[^A-Z0-9]', '', 'g') = %s
            AND a.data >= CURRENT_DATE - INTERVAL '1 day'
            ORDER BY a.data DESC, a.hr_inicio DESC
            LIMIT 1
        """
        
        cur.execute(sql, (placa_limpa,))
        row = cur.fetchone()
        
        if not row:
            return jsonify({"encontrado": False}), 404

        lista_pre_ordens = []
        for i in range(0, 5):
            if row[i] and str(row[i]).strip():
                lista_pre_ordens.append(str(row[i]).strip())
        
        transportadora = row[5]
        produtos_formatados = [] # Vamos usar ESSA lista do começo ao fim

        # 2. Se tiver pré-ordem, busca os Produtos (Mesma conexão!)
        if lista_pre_ordens:
            pre_ordens_tuple = tuple(lista_pre_ordens)
            
            sql_produtos = """
                SELECT 
                    z."PRD_DESC_RES",
                    SUM(
                        (y."PED_QUANT" * CASE u."PRUN_UNID_TRIBUT"
                            WHEN 'UN' THEN 
                                CASE 
                                    WHEN t."PRT_COEFIC" IS NULL THEN 1.0
                                    ELSE (y."PED_PESO" / NULLIF(y."PED_QUANT", 0)) / NULLIF(t."PRT_COEFIC", 0)
                                END
                            ELSE 1.0
                        END)
                    ) as total_fd30, 
                    z."PRD_UNID"
                FROM "APEDIDOS" x
                JOIN "APED_ITEM" y ON y."PED_EMP_GRU_P" = x."PED_EMP_GRU" AND y."PED_NUMERO" = x."PED_NUMERO"
                JOIN "UPRODUTO" z ON z."PRD_CODIGO" = y."PED_PRODUTO"
                LEFT JOIN "UPROUNID" u ON z."PRD_UNID" = u."PRUN_CODIGO"
                LEFT JOIN "UPRODTAB" t ON z."PRD_COD_TAB" = t."PRT_CODIGO"
                WHERE x."PED_PRE_ORDEM" IN %s
                GROUP BY z."PRD_DESC_RES", z."PRD_UNID"
            """
            
            cur.execute(sql_produtos, (pre_ordens_tuple,))
            rows_prod = cur.fetchall()
            
            for rp in rows_prod:
                desc = rp[0].strip() if rp[0] else "PRODUTO SEM NOME"
                qtd = rp[1] if rp[1] is not None else 0
                unidade_banco = str(rp[2]).strip().upper() if rp[2] else "" 
                
                # Formatação da Quantidade
                if qtd % 1 == 0:
                    qtd_fmt = f"{int(qtd)}"
                else:
                    qtd_fmt = f"{qtd:.2f}"
                
                # Lógica da Unidade
                if unidade_banco == 'FD':
                    sufixo_unidade = "FD30"
                else:
                    sufixo_unidade = unidade_banco

                # 🔥 CORREÇÃO: Usar 'produtos_formatados' aqui
                produtos_formatados.append(f"{desc} - {qtd_fmt} {sufixo_unidade}")

        # Monta a string final com a lista correta
        produto_final = " / ".join(produtos_formatados) if produtos_formatados else "Aguardando definição..."
        ordens_final = ", ".join(lista_pre_ordens)

        return jsonify({
            "encontrado": True,
            "transportadora": transportadora,
            "produto": produto_final,
            "pre_ordem": ordens_final
        })

    except Exception as e:
        print(f"❌ Erro dados carga: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if conn: conn.close()


@app.route('/vistoria', methods=['POST'])
def receber_vistoria():
    conn = None
    try:
        form_data = request.form
        print(f"📦 [POST] Processando vistoria ID: {form_data.get('id')}")

        arquivos_binarios = {} 
        imagens_b64 = {}

        campos_arquivo = [
            'fotoPlaca1', 'fotoPlaca2', 'fotoPlaca3', 
            'fotoInterior1', 'fotoInterior2',
            'assinaturaMotorista', 'assinaturaVistoriador'
        ]

        print("📸 Processando e compactando imagens...")
        for campo in campos_arquivo:
            arquivo = request.files.get(campo)
            if arquivo and arquivo.filename:
                
                if "assinatura" in campo:
                    file_bytes = arquivo.read()
                    mime_type = "image/png"
                else:
                    file_bytes = compactar_imagem(arquivo, max_size_kb=200)
                    mime_type = "image/jpeg"
                
                if len(file_bytes) > 0:
                    arquivos_binarios[campo] = file_bytes
                    b64_str = base64.b64encode(file_bytes).decode('utf-8')
                    imagens_b64[campo] = f"data:{mime_type};base64,{b64_str}"
                    print(f"   ✅ Lido/Compactado: {campo} ({len(file_bytes)/1024:.1f} KB)")
                else:
                    arquivos_binarios[campo] = None
            else:
                arquivos_binarios[campo] = None

        # 3. Busca a placa principal
        placa_principal = "N/A"
        try:
            conn = psycopg2.connect(**DB_BUSCA)
            cur = conn.cursor()
            cur.execute('SELECT placa FROM "vistoria"."VAGENDAMENTO" WHERE id = %s', (form_data.get('id'),))
            res = cur.fetchone()
            if res: placa_principal = res[0]
            cur.close()
            conn.close()
        except:
            pass 

        # 4. GERAÇÃO DO PDF
        print("📄 Iniciando geração do PDF...")
        pdf_bytes = None
        try:
            # --- CORREÇÃO PLACAS (Remove None/Null/Vazio) ---
            raw_placas = [
                form_data.get('placa1'), 
                form_data.get('placa2'), 
                form_data.get('placa3')
            ]
            # Filtra apenas o que tem texto real
            lista_placas = [p.upper() for p in raw_placas if p and p.strip() and p.lower() not in ['null', 'undefined', 'none']]

            # --- CORREÇÃO PRODUTO (Limita caracteres) ---
            
            context_pdf = {
                "data": datetime.now().strftime("%d/%m/%Y"),
                "chegada": formatar_data_pdf(form_data.get('chegada')),
                "vistoria": formatar_data_pdf(form_data.get('vistoria')),
                "local_vistoria": form_data.get('localVistoria'),
                "ordem": form_data.get('numeroOrdem'),
                "transportadora": form_data.get('transportadora'),
                "operacao": form_data.get('operacao'),
                "produto": form_data.get('produto'),
                "tipo_veiculo": form_data.get('tipoVeiculo'),
                "ultimos_produtos": form_data.get('ultimosProdutos'),
                "placas": lista_placas,
                "limpeza": form_data.get('limpeza'),
                "danos": form_data.get('danos'),
                "umidade": form_data.get('umidade'),
                "residuos": form_data.get('residuos'),
                "odores": form_data.get('odores'),
                "bocas_graneleiras": form_data.get('bocasGraneleiras'),
                "lonas": form_data.get('lonas'),
                "chapas_mdf": form_data.get('chapasMdf'),
                "lonas_protecao": form_data.get('lonasProtecao'),
                "equipamentos": form_data.get('equipamentos'),
                "tampas_laterais": form_data.get('tampasLaterais'),
                "bau_altura_porta": form_data.get('alturaPorta'),
                "bau_largura_porta": form_data.get('larguraPorta'),
                "bau_assoalho": form_data.get('assoalhoLiso'),
                "container_peso": form_data.get('verificacaoPeso'),
                "observacoes": form_data.get('observacoes'),
                "status_final": form_data.get('caminhaoLiberado'),
                "assinaturas": {
                    "motorista": {
                        "nome": form_data.get('motoristaNome'),
                        "imagem": imagens_b64.get('assinaturaMotorista', '')
                    },
                    "vistoriador": {
                        "nome": form_data.get('vistoriadorNome'),
                        "imagem": imagens_b64.get('assinaturaVistoriador', '')
                    }
                },
                "imagens": imagens_b64 
            }

            pasta_do_script = os.path.dirname(os.path.abspath(__file__))
            env = Environment(loader=FileSystemLoader(pasta_do_script))
            template = env.get_template("vistoria_pdf.html")
            html_content = template.render(**context_pdf)
            pdf_bytes = HTML(string=html_content, base_url=pasta_do_script).write_pdf()
            print(f"   ✅ PDF Gerado com sucesso! ({len(pdf_bytes)/1024:.2f} KB)")

        except Exception as e_pdf:
            print("❌ Erro ao gerar PDF (Salvando sem PDF):", e_pdf)
            traceback.print_exc()

        # 5. Salva tudo no Banco
        print("💾 Salvando no Banco de Dados...")
        
        # 🔥 ALTERAÇÃO: Conecta no DB_BUSCA
        conn = psycopg2.connect(**DB_BUSCA)
        cur = conn.cursor()

        dados_db = {
            "id_agend": form_data.get('id'),
            "status": "Concluida",
            "data_chegada": form_data.get('chegada'),
            "vistoria_inicio": form_data.get('vistoria'),
            "vistoria_fim": form_data.get('fim'),
            "nr_ordem": form_data.get('numeroOrdem'),
            "transportadora": form_data.get('transportadora'),
            "operacao": form_data.get('operacao'),
            "produto": form_data.get('produto'),
            "ultimos_produtos_transportados": form_data.get('ultimosProdutos'),
            "tipo_veiculo": form_data.get('tipoVeiculo'),
            "chk_limpeza_insetos": form_data.get('limpeza'),
            "chk_danos_frestas": form_data.get('danos'),
            "chk_umidade_mofo": form_data.get('umidade'),
            "chk_residuos_carroceria": form_data.get('residuos'),
            "chk_outros_produtos_odores": form_data.get('odores'),
            "chk_bocas_graneleiras": form_data.get('bocasGraneleiras'),
            "chk_lonas_forracao": form_data.get('lonas'),
            "chk_chapas_mdf": form_data.get('chapasMdf'),
            "chk_lonas_integras": form_data.get('lonasProtecao'),
            "chk_cantoneiras_cintas": form_data.get('equipamentos'),
            "chk_tampas_vedacao": form_data.get('tampasLaterais'),
            "chk_porta_altura": form_data.get('alturaPorta'),
            "chk_abertura_total": form_data.get('larguraPorta'),
            "chk_assoalho_liso": form_data.get('assoalhoLiso'),
            "chk_peso_container": form_data.get('verificacaoPeso'),
            "motorista": form_data.get('motoristaNome'),
            "ass_motorista": arquivos_binarios.get('assinaturaMotorista'),
            "vistoriador": form_data.get('vistoriadorNome'),
            "ass_vistoriador": arquivos_binarios.get('assinaturaVistoriador'),
            "placa_1": form_data.get('placa1'), 
            "placa_2": form_data.get('placa2'), 
            "placa_3": form_data.get('placa3'),
            "foto_placa_1": arquivos_binarios.get('fotoPlaca1'),
            "foto_placa_2": arquivos_binarios.get('fotoPlaca2'),
            "foto_placa_3": arquivos_binarios.get('fotoPlaca3'),
            "foto_interior_carroceria": arquivos_binarios.get('fotoInterior1'),
            "foto_interior_carroceria2": arquivos_binarios.get('fotoInterior2'),
            "pdf_documento": pdf_bytes,
            "caminhao_liberado": form_data.get('caminhaoLiberado'),
            "observacoes": form_data.get('observacoes'),
            "local_filial": form_data.get('localVistoria')
        }

        colunas = list(dados_db.keys())
        valores = list(dados_db.values())
        placeholders = ["%s"] * len(valores)
        
        sql = f"""
            INSERT INTO "vistoria"."VRESPOSTAS" ({", ".join(colunas)}) 
            VALUES ({", ".join(placeholders)})
        """
        
        cur.execute(sql, valores)
        conn.commit()
        
        print("✅ Sucesso Total: Vistoria gravada no banco!")
        return jsonify({"message": "Sucesso", "pdf_ok": pdf_bytes is not None}), 200

    except Exception as e:
        print("❌ Erro CRÍTICO:", e)
        traceback.print_exc()
        if conn: conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        if conn: conn.close()

@app.route('/cancelar', methods=['POST'])
def cancelar_vistoria():
    conn = None
    try:
        data = request.json
        print(f"🚫 [CANCEL] Solicitado cancelamento para ID: {data.get('id')}")

        id_agendamento = data.get("id")
        nome_responsavel = data.get("nome")
        motivo = data.get("motivo")

        if not id_agendamento or not nome_responsavel or not motivo:
            return jsonify({"error": "Dados incompletos"}), 400

        # 🔥 ALTERAÇÃO: Conecta no DB_BUSCA
        conn = psycopg2.connect(**DB_BUSCA)
        cur = conn.cursor()

        sql_insert = """
            INSERT INTO "vistoria"."VRESPOSTAS" 
            (id_agend, status, observacoes, vistoriador, vistoria_fim)
            VALUES (%s, 'Cancelada', %s, %s, NOW())
        """
        
        obs_formatada = f"{motivo}"
        cur.execute(sql_insert, (id_agendamento, obs_formatada, nome_responsavel))

        conn.commit()
        print(f"✅ Agendamento {id_agendamento} marcado como Cancelado!")
        
        return jsonify({"status": "ok", "message": "Vistoria cancelada"}), 200

    except Exception as e:
        print("❌ Erro ao cancelar:", e)
        if conn: conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        if conn: conn.close()

@app.route('/login', methods=['POST'])
def login():
    conn = None
    try:
        dados = request.json
        usuario_input = dados.get('usuario')
        senha_input = dados.get('senha')

        if not usuario_input or not senha_input:
            return jsonify({"error": "Dados incompletos"}), 400

        # 🔥 ALTERAÇÃO: Conecta no DB_BUSCA
        conn = psycopg2.connect(**DB_BUSCA)
        cur = conn.cursor()

        sql = 'SELECT id, nome, senha_hash, cargo, local FROM "vistoria"."VUSUARIO" WHERE usuario = %s AND ativo = true'
        cur.execute(sql, (usuario_input,))
        res = cur.fetchone()

        if res:
            uid, nome, senha_hash_banco, cargo, local_usuario = res
            
            if bcrypt.checkpw(senha_input.encode('utf-8'), senha_hash_banco.encode('utf-8')):
                return jsonify({
                    "message": "Login realizado",
                    "user": {
                        "id": uid,
                        "nome": nome,
                        "usuario": usuario_input,
                        "cargo": cargo,
                        "local": local_usuario
                    }
                }), 200
            else:
                return jsonify({"error": "Senha incorreta"}), 401
        
        return jsonify({"error": "Usuário não encontrado"}), 404

    except Exception as e:
        print(f"Erro no login: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if conn: conn.close()

# Em agend.py

@app.route('/gerenciar-agendamento', methods=['POST'])
def gerenciar_agendamento():
    conn = None
    try:
        dados = request.json
        id_agend = dados.get('id')
        acao = dados.get('acao', 'editar')

        if not id_agend: return jsonify({"error": "ID não fornecido"}), 400

        conn = psycopg2.connect(**DB_BUSCA)
        cur = conn.cursor()

        # 1. Trava se já estiver concluída
        cur.execute('SELECT 1 FROM "vistoria"."VRESPOSTAS" WHERE CAST(id_agend AS VARCHAR) = %s AND status = %s', (str(id_agend), 'Concluida'))
        if cur.fetchone():
            return jsonify({"error": "Vistoria já concluída"}), 403

        if acao == 'cancelar':
            sql_cancelar = 'INSERT INTO "vistoria"."VRESPOSTAS" (id_agend, status, observacoes, vistoria_fim) VALUES (%s, \'Cancelada\', %s, NOW())'
            cur.execute(sql_cancelar, (id_agend, dados.get('motivo')))
        else:
            # 2. Validação de Lotação (Excluindo o próprio ID)
            nova_data = dados.get('data')
            nova_hora = dados.get('hora')
            novo_local = dados.get('local')
            duracao = int(dados.get('duracao', 30))

            cur.execute("""
                SELECT COUNT(*) FROM "vistoria"."VAGENDAMENTO" a
                LEFT JOIN "vistoria"."VRESPOSTAS" r ON CAST(r.id_agend AS VARCHAR) = CAST(a.id AS VARCHAR)
                WHERE a.data = %s AND a.hr_inicio = %s AND a.local = %s 
                AND a.id != %s 
                AND (r.status IS NULL OR r.status != 'Cancelada')
            """, (nova_data, nova_hora, novo_local, id_agend))
            
            total_concorrentes = cur.fetchone()[0]
            
            if total_concorrentes >= 3:
                return jsonify({"error": f"Horário das {nova_hora} está lotado ({total_concorrentes} agendamentos)."}), 400

            # 3. Processamento dos Dados
            ordens = [str(o).strip()[:6] for o in dados.get('pre_ordens', []) if str(o).strip()]
            ordens_db = (ordens + [None] * 5)[:5]
            
            # Recalcula hr_fim baseado na duração escolhida
            fmt = '%H:%M'
            dt_inicio = datetime.strptime(nova_hora, fmt)
            dt_fim = dt_inicio + timedelta(minutes=duracao)
            hora_fim = dt_fim.strftime(fmt)

            # 🔥 CORREÇÃO: Removemos 'duracao = %s' do SQL pois a coluna não existe
            sql_update = """
                UPDATE "vistoria"."VAGENDAMENTO" 
                SET placa = %s, data = %s, hr_inicio = %s, hr_fim = %s, local = %s,
                    pre_ordem1 = %s, pre_ordem2 = %s, pre_ordem3 = %s, pre_ordem4 = %s, pre_ordem5 = %s
                WHERE id = %s
            """
            cur.execute(sql_update, (
                dados.get('placa'), nova_data, nova_hora, hora_fim, 
                novo_local, *ordens_db, id_agend
            ))

        conn.commit()
        return jsonify({"message": "Sucesso"}), 200
    except Exception as e:
        if conn: conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        if conn: conn.close()

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)