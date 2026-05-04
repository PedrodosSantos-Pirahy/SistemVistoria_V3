from dotenv import load_dotenv
from flask import Flask, request, jsonify, make_response
from flask_cors import CORS
import psycopg2
from datetime import datetime, timedelta
import traceback
import sys
import os
import threading
import uuid
import tempfile
import base64
import io
import bcrypt
from PIL import Image, ImageOps
from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML
from psycopg2 import pool

# pasta_atual = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__)#, template_folder=pasta_atual)

# Controle de jobs de exportação em background
_jobs = {}  # { job_id: { status, arquivo, nome_arquivo, erro } }

# Configuração CORS
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)

load_dotenv()

DB_BUSCA = {
    "host": os.getenv("DB_HOST"),
    "database": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASS"),
    "port": os.getenv("DB_PORT")
}
# LOGO ABAIXO DO DB_BUSCA, CRIE O POOL ASSIM:
try:
    db_pool = pool.ThreadedConnectionPool(1, 20, **DB_BUSCA)
    if db_pool:
        print("✅ Pool de conexões criado com sucesso!")
except Exception as e:
    print(f"❌ ERRO CRÍTICO ao criar o pool de conexões: {e}")

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
    cur = None
    try:
        # 🔥 1. AGORA USA O POOL (Conecta em 1 milissegundo)
        conn = db_pool.getconn()
        cur = conn.cursor()

        # 🔥 2. SQL LIMPO: Sem a subquery de Regex pesada! Trazemos a resposta instantaneamente.
        sql = """
            SELECT 
                a.id, a.placa, a.data, a.hr_inicio, a.local, 
                CONCAT_WS(', ', NULLIF(a.pre_ordem1,''), NULLIF(a.pre_ordem2,''), NULLIF(a.pre_ordem3,''), NULLIF(a.pre_ordem4,''), NULLIF(a.pre_ordem5,'')) as todas_ordens
            FROM "vistoria"."VAGENDAMENTO" a
            WHERE a.data >= CURRENT_DATE
            AND TRIM(COALESCE(a.placa, '')) != ''
            AND NOT EXISTS (
                SELECT 1 FROM "vistoria"."VRESPOSTAS" r
                WHERE CAST(r.id_agend AS VARCHAR) = CAST(a.id AS VARCHAR)
                AND r.status IN ('Concluída', 'Concluida', 'Cancelada')
            )
            ORDER BY a.data ASC, a.hr_inicio ASC
        """
        
        cur.execute(sql)
        rows = cur.fetchall()
        
        # 🔥 3. CACHE DE TRANSPORTADORAS (A mágica da velocidade)
        # Pega todas as placas da tela e faz UMA ÚNICA pergunta ao banco.
        placas_pendentes = set()
        for row in rows:
            if row[1]: placas_pendentes.add(row[1].upper().replace("-", "").strip())

        transp_cache = {}
        if placas_pendentes:
            cur_transp = conn.cursor()
            cur_transp.execute("""
                SELECT REGEXP_REPLACE(UPPER(x."PLA_PLACA"), '[^A-Z0-9]', '', 'g'), y."TRP_NOME"
                FROM "UTRAPLACA" x
                JOIN "UTRAPROPR" y ON x."PLA_PROPR" = y."TRP_CODIGO"
                WHERE REGEXP_REPLACE(UPPER(x."PLA_PLACA"), '[^A-Z0-9]', '', 'g') IN %s
            """, (tuple(placas_pendentes),))
            
            for p, t in cur_transp.fetchall():
                transp_cache[p] = t
            cur_transp.close()

        pendencias = []
        agora = datetime.now()
        hoje = agora.date()

        for row in rows:
            db_id, db_placa, db_data, db_hora, db_local, db_ordens_concat = row

            # Pega a transportadora do cache rápido que acabamos de montar
            placa_limpa = db_placa.upper().replace("-", "").strip() if db_placa else ""
            db_transp = transp_cache.get(placa_limpa, 'Consultar Cadastro')

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
                status_temp = data_visivel  
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
        if cur: cur.close()
        if conn: db_pool.putconn(conn) # 🔥 Devolve a conexão pro Pool!

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
    cur = None
    try:
        # 🔥 CORREÇÃO: Alugando o carro na Hertz (Pool)
        conn = db_pool.getconn()
        cur = conn.cursor()

        placa_limpa = placa.upper().replace("-", "").strip()

        # Usando LEFT JOIN para não bloquear caminhões sem transportadora
        sql = """
            SELECT COALESCE(y."TRP_NOME", 'TRANSPORTADORA NÃO VINCULADA NO ERP')
            FROM "UTRAPLACA" x
            LEFT JOIN "UTRAPROPR" y ON x."PLA_PROPR" = y."TRP_CODIGO"
            WHERE REGEXP_REPLACE(UPPER(x."PLA_PLACA"), '[^A-Z0-9]', '', 'g') = %s
            LIMIT 1
        """
        
        cur.execute(sql, (placa_limpa,))
        resultado = cur.fetchone()

        if resultado:
            return jsonify({"transportadora": resultado[0]}), 200
        else:
            return jsonify({"error": "Placa não encontrada no ERP"}), 404

    except Exception as e:
        print(f"❌ Erro ao consultar placa: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if cur: cur.close()
        # 🔥 Devolvendo o carro na Hertz (Pool) corretamente!
        if conn: db_pool.putconn(conn)

@app.route('/transportadoras', methods=['GET'])
def listar_transportadoras():
    busca = request.args.get('q', '').strip().upper()
    conn = None
    cur = None
    try:
        conn = db_pool.getconn()
        cur = conn.cursor()
        cur.execute("""
            SELECT "TRP_CODIGO", "TRP_NOME"
            FROM "UTRAPROPR"
            WHERE UPPER("TRP_NOME") LIKE %s
            ORDER BY "TRP_NOME" ASC
            LIMIT 20
        """, (f'%{busca}%',))
        rows = cur.fetchall()
        return jsonify([{"codigo": r[0], "nome": r[1]} for r in rows])
    except Exception as e:
        print(f"Erro ao listar transportadoras: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if cur: cur.close()
        if conn: db_pool.putconn(conn)

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

        print("🔌 Conectando ao DB_BUSCA...")
        conn = psycopg2.connect(**DB_BUSCA)
        cur = conn.cursor()

        # 🔥 LÓGICA DO DERIVADO (O Garçom Inteligente)
        is_derivado = False
        ordens_validas = [str(o).strip() for o in lista_ordens[:5] if str(o).strip()]
        
        if ordens_validas:
            # Pede para a despensa (ERP) as unidades dos produtos
            sql_unidades = """
                SELECT z."PRD_UNID"
                FROM "APEDIDOS" x
                JOIN "APED_ITEM" y ON y."PED_EMP_GRU_P" = x."PED_EMP_GRU" AND y."PED_NUMERO" = x."PED_NUMERO"
                JOIN "UPRODUTO" z ON z."PRD_CODIGO" = y."PED_PRODUTO"
                WHERE x."PED_PRE_ORDEM" IN %s
            """
            cur.execute(sql_unidades, (tuple(ordens_validas),))
            unidades_encontradas = cur.fetchall()
            
            for unid in unidades_encontradas:
                unidade_texto = str(unid[0]).strip().upper() if unid[0] else ""
                if unidade_texto == 'TON': 
                    is_derivado = True
                    break 

        # Verifica se o slot já está ocupado antes de inserir
        cur.execute("""
            SELECT COUNT(*) FROM "vistoria"."VAGENDAMENTO"
            WHERE data = %s AND hr_inicio = %s AND local = %s
            AND COALESCE(derivado, FALSE) = %s
            AND NOT EXISTS (
                SELECT 1 FROM "vistoria"."VRESPOSTAS" r
                WHERE CAST(r.id_agend AS VARCHAR) = CAST("VAGENDAMENTO".id AS VARCHAR)
                AND r.status IN ('Cancelada', 'Cancelado')
            )
        """, (dados['data_agendamento'], dados['hora_inicio'], dados.get('local', 'Matriz'), is_derivado))
        if cur.fetchone()[0] > 0:
            return jsonify({"error": "SLOT_OCUPADO"}), 409

        sql = """
            INSERT INTO "vistoria"."VAGENDAMENTO"
            (placa, data, hr_inicio, hr_fim, local, pre_ordem1, pre_ordem2, pre_ordem3, pre_ordem4, pre_ordem5, criado_em, derivado, criado_por)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), %s, %s)
            RETURNING id;
        """
        valores = (
            dados.get('placa', '').strip(), dados['data_agendamento'], dados['hora_inicio'], str_hr_fim,
            dados.get('local', 'Matriz'), ordens_db[0], ordens_db[1], ordens_db[2], ordens_db[3], ordens_db[4],
            is_derivado, dados.get('criado_por', 'Sistema')
        )

        cur.execute(sql, valores)
        novo_id = cur.fetchone()[0]

        # Se não tem placa, guarda transportadora em VTRANSTEMP para exibição no monitoramento
        if not dados.get('placa', '').strip():
            transportadora_val = dados.get('transportadora', '') or ''
            if transportadora_val:
                cur.execute("""
                    INSERT INTO "vistoria"."VTRANSTEMP" ("ID_AGEND", "TRANSPORTADORA")
                    VALUES (%s, %s)
                """, (novo_id, transportadora_val))

        conn.commit()

        print(f"🎉 SUCESSO! Agendamento {novo_id} criado! (Derivado: {is_derivado})")
        
        # 👇 CORREÇÃO: O GARÇOM VOLTANDO COM A RESPOSTA (JSON)
        return jsonify({"message": "Agendado com sucesso!", "id": novo_id}), 200

    except Exception as e:
        import traceback
        print("ERRO CRIAR-AGENDAMENTO:", str(e))
        traceback.print_exc()
        if conn: conn.rollback()
        if 'uq_agend_slot' in str(e) or ('unique' in str(e).lower() and 'vagendamento' in str(e).lower()):
            return jsonify({"error": "SLOT_OCUPADO"}), 409
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
        # ... (código anterior)
        # 2. Se tiver pré-ordem, busca os Produtos (Mesma conexão!)
        # 2. Se tiver pré-ordem, busca os Produtos (Mesma conexão!)
        if lista_pre_ordens:
            pre_ordens_tuple = tuple(lista_pre_ordens)
            
            # 🔥 SQL ATUALIZADO: Trazendo a soma de produtos e o TIPO DE PALETE!
            sql_produtos = """
                    SELECT 
                            z."PRD_DESC_RES", 
                            SUM(y."PED_QUANT") as quantidade_total, 
                            z."PRD_UNID",
                            CASE 
                                -- Se for MINI ou BAT (ou nulo), prioriza o valor de PLT_DESC_TIPO
                                WHEN COALESCE(s."PLT_DESC_TIPO", 'BAT') IN ('MINI', 'BAT') THEN COALESCE(s."PLT_DESC_TIPO", 'BAT')
                                -- Se não for um dos acima, verifica a regra do CHEP na tabela de pessoas
                                WHEN u."PES_TP_PALET" IN ('CHEP', 'CHEPc') THEN u."PES_TP_PALET"
                                -- Caso contrário, retorna o valor padrão
                                ELSE COALESCE(s."PLT_DESC_TIPO", 'BAT')
                            END AS tipo_palete_final
                        FROM "APEDIDOS" x
                        JOIN "APED_ITEM" y ON y."PED_EMP_GRU_P" = x."PED_EMP_GRU" AND y."PED_NUMERO" = x."PED_NUMERO"
                        JOIN "UPRODUTO" z ON z."PRD_CODIGO" = y."PED_PRODUTO"
                        LEFT JOIN "APALETS" s ON y."PED_PALETS" = s."PLT_CODIGO"
                        LEFT JOIN "UPESSOAS" u ON x."PED_PESSOA" = u."PES_CODIGO" AND u."PES_EMPRESA" = x."PED_EMPRESA"
                        WHERE x."PED_PRE_ORDEM" IN %s
                        -- O GROUP BY leva o CASE inteiro!
                        GROUP BY 
                            z."PRD_DESC_RES", 
                            z."PRD_UNID", 
                            CASE 
                                WHEN COALESCE(s."PLT_DESC_TIPO", 'BAT') IN ('MINI', 'BAT') THEN COALESCE(s."PLT_DESC_TIPO", 'BAT')
                                WHEN u."PES_TP_PALET" IN ('CHEP', 'CHEPc') THEN u."PES_TP_PALET"
                                ELSE COALESCE(s."PLT_DESC_TIPO", 'BAT')
                            END
                        ORDER BY quantidade_total DESC;
            """
            cur.execute(sql_produtos, (pre_ordens_tuple,))
            rows_prod = cur.fetchall()
            
            for rp in rows_prod:
                desc = rp[0].strip() if rp[0] else "PRODUTO SEM NOME"
                qtd = rp[1] if rp[1] is not None else 0
                unidade_banco = str(rp[2]).strip().upper() if rp[2] else "" 
                tipo_palete = str(rp[3]).strip() # Ex: PBR, CHEP, BAT
                
                # Formatação da Quantidade
                if qtd % 1 == 0:
                    qtd_fmt = f"{int(qtd)}"
                else:
                    qtd_fmt = f"{qtd:.2f}"

                # Monta a string limpa para o Frontend (Ex: "ARROZ BRANCO - 150 FD (PBR)")
                produtos_formatados.append(f"{desc} - {qtd_fmt} {unidade_banco} ({tipo_palete})")
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

            # 👇 --- LÓGICA BLINDADA PARA DATA DE REVISÃO (D+1) --- 👇
            # 1. Define um valor padrão (Amanhã) para garantir que nunca fique vazio
            data_cabecalho = (datetime.now() + timedelta(days=1)).strftime("%d/%m/%Y")
            data_base_str = "Início" # Inicializa variável para evitar erro no print

            try:
                # 2. Tenta pegar a data real
                data_base_str = form_data.get('vistoria') or form_data.get('chegada')
                
                if data_base_str:
                    # 3. Limpeza Extrema: Remove 'T', pega só a primeira parte antes do espaço
                    # Transforma "2026-02-18T13:00" ou "18/02/2026 13:00" em apenas a data
                    data_limpa = data_base_str.replace('T', ' ').split(' ')[0].strip()
                    
                    # 4. Tenta converter os dois formatos possíveis
                    if '/' in data_limpa:
                        dt_obj = datetime.strptime(data_limpa, "%d/%m/%Y")
                    else:
                        dt_obj = datetime.strptime(data_limpa, "%Y-%m-%d")

                    # 5. Aplica a regra D+1
                    dt_revisao = dt_obj + timedelta(days=1)
                    data_cabecalho = dt_revisao.strftime("%d/%m/%Y")

            except Exception as e:
                # Se der qualquer erro, apenas avisa no log e usa a data padrão (Amanhã)
                print(f"⚠️ Aviso: Não foi possível calcular D+1 da data '{data_base_str}'. Usando data padrão. Erro: {e}")
            # 👆 -------------------------------------------------------- 👆
            
            context_pdf = {
                "data": datetime.now().strftime("%d/%m/%Y"),
                "chegada": formatar_data_pdf(form_data.get('chegada')),
                "vistoria": formatar_data_pdf(form_data.get('vistoria')),
                "fim": formatar_data_pdf(form_data.get('fim')),
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
            "data_chegada": form_data.get('chegada') or None,
            "vistoria_inicio": form_data.get('vistoria') or None,
            "vistoria_fim": form_data.get('fim') or None,
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

# No arquivo: agend.py
@app.route('/gerenciar-agendamento', methods=['POST'])
def gerenciar_agendamento():
    conn = None
    try:
        dados = request.json
        id_agend = dados.get('id')
        acao = dados.get('acao', 'editar')
        
        # Campos de Auditoria
        justificativa = dados.get('justificativa')
        usuario_responsavel = dados.get('responsavel_edicao')

        if not id_agend: return jsonify({"error": "ID não fornecido"}), 400

        # 🔥 CORREÇÃO: A CONEXÃO TEM QUE SER A PRIMEIRA COISA
        conn = psycopg2.connect(**DB_BUSCA)
        cur = conn.cursor()

        # 1. VERIFICA SE JÁ ESTÁ CONCLUÍDA
        cur.execute('SELECT 1 FROM "vistoria"."VRESPOSTAS" WHERE CAST(id_agend AS VARCHAR) = %s AND status = %s', (str(id_agend), 'Concluida'))
        is_concluida = cur.fetchone()

        # Se concluída e sem justificativa -> BLOQUEIA
        if is_concluida and not justificativa:
            return jsonify({"error": "Vistoria concluída. Requer justificativa TI."}), 403

        # 2. BUSCA DADOS ANTIGOS (SÓ SE FOR GRAVAR LOG)
        # Se não tiver justificativa (edição normal de pendente), não precisa buscar o antigo para comparar
        alteracoes_texto = []
        
        if justificativa:
            cur.execute("""
                SELECT placa, data, hr_inicio, local, 
                       pre_ordem1, pre_ordem2, pre_ordem3, pre_ordem4, pre_ordem5
                FROM "vistoria"."VAGENDAMENTO" WHERE id = %s
            """, (id_agend,))
            antigo = cur.fetchone()
            
            if antigo:
                antigo_dict = {
                    'placa': antigo[0],
                    'data': str(antigo[1]), 
                    'hora': str(antigo[2])[:5], 
                    'local': antigo[3],
                    'pre_ordens': [p for p in antigo[4:] if p] 
                }

                # Comparações
                nova_placa = dados.get('placa')
                if nova_placa != antigo_dict['placa']:
                    alteracoes_texto.append(f"Placa: {antigo_dict['placa']} -> {nova_placa}")

                nova_data = dados.get('data')
                if nova_data != antigo_dict['data']:
                    alteracoes_texto.append(f"Data: {antigo_dict['data']} -> {nova_data}")

                nova_hora = dados.get('hora')
                if nova_hora != antigo_dict['hora']:
                    alteracoes_texto.append(f"Hora: {antigo_dict['hora']} -> {nova_hora}")
                    
                novo_local = dados.get('local')
                if novo_local != antigo_dict['local']:
                    alteracoes_texto.append(f"Local: {antigo_dict['local']} -> {novo_local}")

                novas_ordens = [str(o).strip()[:6] for o in dados.get('pre_ordens', []) if str(o).strip()]
                antigas_ordens_str = ",".join(sorted(antigo_dict['pre_ordens']))
                novas_ordens_str = ",".join(sorted(novas_ordens))
                
                if antigas_ordens_str != novas_ordens_str:
                     alteracoes_texto.append(f"Ordens: [{antigas_ordens_str}] -> [{novas_ordens_str}]")

                if not alteracoes_texto:
                    alteracoes_texto.append("Nenhuma alteração de dados detectada (apenas salvou)")

            # 3. GRAVA NA TABELA 'VAUDITORIA'
            texto_mudancas = " | ".join(alteracoes_texto)
            texto_mudancas_safe = (texto_mudancas[:245] + '...') if len(texto_mudancas) > 249 else texto_mudancas
            
            sql_audit = """
                INSERT INTO "vistoria"."VAUDITORIA" 
                ("ID_agend", usuario, motivo, "alteração", dataehorario) 
                VALUES (%s, %s, %s, %s, NOW())
            """
            cur.execute(sql_audit, (id_agend, usuario_responsavel, justificativa, texto_mudancas_safe))
            print(f"📝 Log gravado: {usuario_responsavel}")

        # 4. SEGUE A EDIÇÃO NORMALMENTE
        if acao == 'cancelar':
            # 🛑 TRAVA NOVA: Se já estiver concluída, proíbe cancelar
            if is_concluida:
                return jsonify({"error": "Operação Bloqueada: Não é permitido cancelar uma vistoria já concluída."}), 403

            sql_cancelar = 'INSERT INTO "vistoria"."VRESPOSTAS" (id_agend, status, observacoes, vistoria_fim) VALUES (%s, \'Cancelada\', %s, NOW())'
            cur.execute(sql_cancelar, (id_agend, dados.get('motivo')))
        else:
             # Prepara dados para update
             nova_placa = dados.get('placa')
             nova_data = dados.get('data')
             nova_hora = dados.get('hora')
             novo_local = dados.get('local')
             novas_ordens = [str(o).strip()[:6] for o in dados.get('pre_ordens', []) if str(o).strip()]
             
             duracao = int(dados.get('duracao', 30))
             ordens_db = (novas_ordens + [None] * 5)[:5]
             
             dt_inicio = datetime.strptime(nova_hora, '%H:%M')
             dt_fim = dt_inicio + timedelta(minutes=duracao)
             hora_fim = dt_fim.strftime('%H:%M')

             sql_update = """
                UPDATE "vistoria"."VAGENDAMENTO" 
                SET placa = %s, data = %s, hr_inicio = %s, hr_fim = %s, local = %s,
                    pre_ordem1 = %s, pre_ordem2 = %s, pre_ordem3 = %s, pre_ordem4 = %s, pre_ordem5 = %s
                WHERE id = %s
             """
             cur.execute(sql_update, (
                nova_placa, nova_data, nova_hora, hora_fim,
                novo_local, *ordens_db, id_agend
             ))

             # Se placa foi informada, limpa o registro temporário de transportadora
             if nova_placa and nova_placa.strip():
                 cur.execute("""
                     DELETE FROM "vistoria"."VTRANSTEMP" WHERE "ID_AGEND" = %s
                 """, (id_agend,))

        conn.commit()
        return jsonify({"message": "Sucesso"}), 200

    except Exception as e:
        if conn: conn.rollback()
        print("❌ Erro:", e)
        # traceback.print_exc() # Descomente se quiser ver o erro detalhado no terminal
        return jsonify({"error": str(e)}), 500
    finally:
        if conn: conn.close()

import csv # Adicione isto lá no topo do ficheiro se não tiver, ou o Python já carrega nativamente!

# --- ROTA: INICIAR EXPORTAÇÃO EM BACKGROUND ---
@app.route('/exportar-relatorio', methods=['GET'])
def exportar_relatorio():
    params = {
        'inicio':         request.args.get('inicio', ''),
        'fim':            request.args.get('fim', ''),
        'status':         request.args.get('status', 'Todas'),
        'local':          request.args.get('local', 'Qualquer'),
        'derivado':       request.args.get('derivado', 'Todas'),
        'transportadora': request.args.get('transportadora', '').strip().upper(),
        'formato':        request.args.get('formato', 'excel'),
    }
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {'status': 'processando', 'arquivo': None, 'nome': None, 'erro': None}
    threading.Thread(target=_gerar_relatorio, args=(job_id, params), daemon=True).start()
    return jsonify({'job_id': job_id})


@app.route('/status-relatorio/<job_id>', methods=['GET'])
def status_relatorio(job_id):
    job = _jobs.get(job_id)
    if not job:
        return jsonify({'status': 'nao_encontrado'}), 404
    return jsonify({'status': job['status'], 'erro': job.get('erro')})


@app.route('/download-relatorio/<job_id>', methods=['GET'])
def download_relatorio(job_id):
    print(f"📥 [DOWNLOAD] job_id={job_id} | jobs disponíveis: {list(_jobs.keys())}")
    job = _jobs.get(job_id)
    if not job:
        print(f"❌ [DOWNLOAD] job_id={job_id} NÃO encontrado em _jobs")
        return jsonify({'error': 'Job não encontrado'}), 404
    print(f"📋 [DOWNLOAD] status={job['status']} | arquivo={job.get('arquivo')} | nome={job.get('nome')}")
    if job['status'] != 'pronto' or not job['arquivo']:
        return jsonify({'error': f"Arquivo não disponível (status={job['status']})"}), 404
    caminho = job['arquivo']
    nome = job['nome']
    try:
        import os.path
        if not os.path.exists(caminho):
            print(f"❌ [DOWNLOAD] Arquivo não existe no disco: {caminho}")
            return jsonify({'error': f'Arquivo não existe: {caminho}'}), 500
        with open(caminho, 'rb') as f:
            dados = f.read()
        print(f"✅ [DOWNLOAD] Arquivo lido: {len(dados)} bytes | nome={nome}")
        if nome.endswith('.html'):
            resp = make_response(dados)
            resp.headers['Content-Type'] = 'text/html; charset=utf-8'
        else:
            resp = make_response(dados)
            resp.headers['Content-Type'] = 'text/csv; charset=utf-8-sig'
            resp.headers['Content-Disposition'] = f'attachment; filename="{nome}"'
        try:
            os.remove(caminho)
        except Exception:
            pass
        del _jobs[job_id]
        return resp
    except Exception as e:
        traceback.print_exc()
        print(f"❌ [DOWNLOAD] Exceção: {e}")
        return jsonify({'error': str(e)}), 500


def _gerar_relatorio(job_id, p):
    data_inicio   = p['inicio']
    data_fim      = p['fim']
    status        = p['status']
    local         = p['local']
    derivado      = p['derivado']
    transportadora = p['transportadora']
    formato       = p['formato']
    print(f"🔄 [RELATORIO] Iniciando geração | job_id={job_id} | formato={formato} | {data_inicio} → {data_fim} | local={local} | status={status}")

    # Tradução bonita do Filtro "Derivado" para o cabeçalho do PDF
    texto_tipo_filtro = "Geral (Ambas)"
    if derivado == 'Sim':
        texto_tipo_filtro = "Derivados (A Granel)"
    elif derivado == 'Nao':
        texto_tipo_filtro = "Fardos"

    conn = None
    try:
        conn = psycopg2.connect(**DB_BUSCA)
        cur = conn.cursor()

        # ==========================================
        # 1. MONTANDO OS FILTROS DA BUSCA
        # ==========================================
        where_parts = ["a.data BETWEEN %s AND %s"]
        params_query = [data_inicio, data_fim]

        if status != 'Todas':
            if status == 'AGUARDANDO':
                where_parts.append("(a.status_patio IN ('PENDENTE', 'ATRASADO') OR a.status_patio IS NULL)")
            else:
                where_parts.append("a.status_patio = %s")
                params_query.append(status)

        if local != 'Qualquer':
            where_parts.append("UPPER(TRIM(a.local)) = UPPER(TRIM(%s))")
            params_query.append(local)

        if derivado == 'Sim':
            where_parts.append("a.derivado = TRUE")
        elif derivado == 'Nao':
            where_parts.append("(a.derivado = FALSE OR a.derivado IS NULL)")

        if transportadora:
            where_parts.append("""
                UPPER(COALESCE(r.transportadora, 
                    (SELECT y2."TRP_NOME" FROM "UTRAPLACA" x2 
                     JOIN "UTRAPROPR" y2 ON x2."PLA_PROPR" = y2."TRP_CODIGO" 
                     WHERE REGEXP_REPLACE(UPPER(x2."PLA_PLACA"), '[^A-Z0-9]', '', 'g') = REGEXP_REPLACE(UPPER(a.placa), '[^A-Z0-9]', '', 'g') 
                     LIMIT 1)
                )) LIKE %s
            """)
            params_query.append(f"%{transportadora}%")

        where_final = " AND ".join(where_parts)

        # ==========================================
        # 2. A SUPER QUERY (Traz 35 colunas de dados)
        # ==========================================
        sql = f"""
            SELECT 
                a.placa, 
                to_char(a.data, 'DD/MM/YYYY'), 
                to_char(a.hr_inicio, 'HH24:MI'),
                to_char(a.hr_fim, 'HH24:MI'),
                a.local,
                CASE WHEN a.derivado = TRUE THEN 'Derivados (A Granel)' ELSE 'Fardos' END,
                COALESCE(a.status_patio, 'PENDENTE'),
                COALESCE(a.criado_por, 'Sistema'),
                
                CONCAT_WS(' - ', NULLIF(a.pre_ordem1,''), NULLIF(a.pre_ordem2,''), NULLIF(a.pre_ordem3,''), NULLIF(a.pre_ordem4,''), NULLIF(a.pre_ordem5,'')),
                
                COALESCE(r.transportadora, 
                    (SELECT y2."TRP_NOME" FROM "UTRAPLACA" x2 
                     JOIN "UTRAPROPR" y2 ON x2."PLA_PROPR" = y2."TRP_CODIGO" 
                     WHERE REGEXP_REPLACE(UPPER(x2."PLA_PLACA"), '[^A-Z0-9]', '', 'g') = REGEXP_REPLACE(UPPER(a.placa), '[^A-Z0-9]', '', 'g') 
                     LIMIT 1), 
                'NÃO INFORMADA'),
                
                r.motorista,
                r.vistoriador,
                to_char(r.data_chegada, 'DD/MM/YYYY HH24:MI'),
                to_char(r.vistoria_inicio, 'DD/MM/YYYY HH24:MI'),
                to_char(r.vistoria_fim, 'DD/MM/YYYY HH24:MI'),
                
                -- Campos do Carregamento 
                CAST(f."FE_INICIO_CAR" AS VARCHAR),
                CAST(f."FE_FIM_CAR" AS VARCHAR),

                r.caminhao_liberado,
                r.tipo_veiculo,
                r.produto,
                r.observacoes,

                -- Respostas do Checklist
                r.chk_limpeza_insetos,
                r.chk_danos_frestas,
                r.chk_umidade_mofo,
                r.chk_residuos_carroceria,
                r.chk_outros_produtos_odores,
                r.chk_bocas_graneleiras,
                r.chk_lonas_forracao,
                r.chk_chapas_mdf,
                r.chk_lonas_integras,
                r.chk_cantoneiras_cintas,
                r.chk_tampas_vedacao,

                -- Respostas Específicas
                r.chk_porta_altura,
                r.chk_abertura_total,
                r.chk_assoalho_liso,
                r.chk_peso_container

            FROM "vistoria"."VAGENDAMENTO" a
            LEFT JOIN "vistoria"."VRESPOSTAS" r ON CAST(r.id_agend AS VARCHAR) = CAST(a.id AS VARCHAR)
            
            -- Busca do Carregamento
            LEFT JOIN LATERAL (
                SELECT "FE_INICIO_CAR", "FE_FIM_CAR"
                FROM agr."AEMBFICHA" emb
                WHERE emb."FE_PLACA" = REGEXP_REPLACE(UPPER(a.placa), '[^A-Z0-9]', '', 'g')
                  AND emb."FE_DATA" = a.data
                  -- Garante que o carregamento iniciou DEPOIS (ou ao mesmo tempo) do fim da vistoria
                  AND (r.vistoria_fim IS NULL OR CAST(emb."FE_HR_INC" AS TIME) >= CAST(r.vistoria_fim AS TIME))
                ORDER BY emb."FE_HR_INC" ASC
                LIMIT 1
            ) f ON true
            
            WHERE {where_final}
            ORDER BY a.data ASC, a.hr_inicio ASC
        """
        cur.execute(sql, tuple(params_query))
        rows = cur.fetchall()

        # ==============================================================
        # 🟢 OPÇÃO 1: EXCEL (Com todas as colunas + produtos do ERP)
        # ==============================================================
        if formato == 'excel':
            # Buscar produtos do ERP para todas as pré-ordens do resultado
            todas_pos_excel = set()
            for row in rows:
                if row[8]:
                    for p in str(row[8]).replace(' - ', ',').replace('/', ',').split(','):
                        if p.strip().isdigit():
                            todas_pos_excel.add(p.strip())

            # Mapa: pre_ordem -> lista de strings simples de produto
            produtos_erp_excel = {}
            if todas_pos_excel:
                try:
                    cur_erp2 = conn.cursor()
                    cur_erp2.execute("""
                        SELECT
                            CAST(x."PED_PRE_ORDEM" AS VARCHAR),
                            z."PRD_DESC_RES",
                            SUM(y."PED_QUANT"),
                            z."PRD_UNID"
                        FROM "APEDIDOS" x
                        JOIN "APED_ITEM" y ON y."PED_EMP_GRU_P" = x."PED_EMP_GRU" AND y."PED_NUMERO" = x."PED_NUMERO"
                        JOIN "UPRODUTO" z ON z."PRD_CODIGO" = y."PED_PRODUTO"
                        WHERE x."PED_PRE_ORDEM" IN %s
                        GROUP BY x."PED_PRE_ORDEM", z."PRD_DESC_RES", z."PRD_UNID"
                        ORDER BY SUM(y."PED_QUANT") DESC
                    """, (tuple(todas_pos_excel),))
                    for po, nome, qtd, unid in cur_erp2.fetchall():
                        po_str = str(po).strip()
                        qtd_num = float(qtd) if qtd else 0
                        qtd_fmt = str(int(qtd_num)) if qtd_num % 1 == 0 else f"{qtd_num:.2f}"
                        nome_limpo = nome.strip().replace('\n', ' ').replace('\r', '') if nome else ''
                        linha_prod = f"{nome_limpo} {qtd_fmt} {str(unid).strip()}" if nome_limpo else ''
                        if po_str not in produtos_erp_excel:
                            produtos_erp_excel[po_str] = []
                        if linha_prod:
                            produtos_erp_excel[po_str].append(linha_prod)
                except Exception as e:
                    import traceback
                    print("⚠️ Erro ERP Excel:", e)
                    traceback.print_exc()

            output = io.StringIO()
            writer = csv.writer(output, delimiter=';', dialect='excel')

            cabecalho = [
                'Placa', 'Data Agendada', 'Hora Início Agend.', 'Hora Fim Agend.', 'Unidade', 'Tipo Carga',
                'Status no Pátio', 'Criado Por', 'Pré-Ordens', 'Transportadora', 'Motorista', 'Vistoriador',
                'Chegada Motorista', 'Início Vistoria', 'Fim Vistoria', 'Início Carregamento (ERP)', 'Fim Carregamento (ERP)',
                'Caminhão Liberado?', 'Tipo Veículo', 'Produtos (ERP)', 'Observações da Vistoria',
                'Limpeza/Insetos', 'Danos/Frestas', 'Umidade/Mofo', 'Resíduos', 'Odores', 'Bocas Graneleiras',
                'Lonas/Forração', 'Chapas MDF', 'Lonas Íntegras', 'Cantoneiras/Cintas', 'Tampas/Vedação',
                'Altura Porta 2,30m', 'Abertura Total', 'Assoalho Liso', 'Peso/Tara Container'
            ]
            writer.writerow(cabecalho)

            for row in rows:
                # Monta string de produtos ERP para esta linha (um por linha na célula)
                pre_ordens_str = str(row[8]) if row[8] else ''
                todos_prods = []
                for p in pre_ordens_str.replace(' - ', ',').replace('/', ',').split(','):
                    p_clean = p.strip()
                    if p_clean in produtos_erp_excel:
                        todos_prods.extend(produtos_erp_excel[p_clean])
                produto_erp_str = ' | '.join(todos_prods) if todos_prods else '-'

                linha = list(row)
                linha[19] = produto_erp_str  # col 19 = r.produto, substituido por ERP
                linha_limpa = [str(item).replace('\n', ' ').replace('\r', '') if item is not None else '-' for item in linha]
                writer.writerow(linha_limpa)

            nome_arquivo = f"Relatorio_Patio_{data_inicio}_a_{data_fim}.csv"
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.csv', prefix='rel_')
            tmp.write(output.getvalue().encode('utf-8-sig'))
            tmp.close()
            _jobs[job_id] = {'status': 'pronto', 'arquivo': tmp.name, 'nome': nome_arquivo, 'erro': None}

        # ==============================================================
        # 🔴 OPÇÃO 2: PDF (Visual Executivo com Quantidades e Paletes)
        # ==============================================================
        elif formato == 'pdf':
            
            # 1. Descobrir todas as pré-ordens desse relatório
            todas_pos = set()
            for row in rows:
                if row[8]: 
                    for p in str(row[8]).replace(' - ', ',').replace('/', ',').split(','):
                        if p.strip().isdigit():
                            todas_pos.add(p.strip())
            
            # 2. Busca no ERP (Pedidos, Embarques, Produtos, Quantidades e Paletes)
            info_erp = {}
            if todas_pos:
                try:
                    cur_erp = conn.cursor()
                    
                    # --- BUSCA PEDIDOS E EMBARQUES ---
                    cur_erp.execute("""
                        SELECT CAST(a."PED_PRE_ORDEM" AS VARCHAR), a."PED_NUMERO", b."EMB_NUMERO"
                        FROM "APEDIDOS" a 
                        LEFT JOIN "AEMBARITE" b ON a."PED_NUMERO" = b."EMB_PEDIDO" AND a."PED_EMPRESA" = b."EMB_EMPRESA" 
                        WHERE a."PED_PRE_ORDEM" IN %s
                    """, (tuple(todas_pos),))
                    
                    for po, ped, emb in cur_erp.fetchall():
                        po_str = str(po).strip()
                        if po_str not in info_erp: info_erp[po_str] = {'ped': set(), 'emb': set(), 'produtos': set()}
                        if ped: info_erp[po_str]['ped'].add(str(ped))
                        if emb: info_erp[po_str]['emb'].add(str(emb))
                    
                    # --- BUSCA PRODUTOS COM SOMA DE QUANTIDADES E TIPO DE PALETE ---
                    sql_produtos_pdf = """
                    SELECT
                            CAST(x."PED_PRE_ORDEM" AS VARCHAR),
                            z."PRD_DESC_RES",
                            SUM(y."PED_QUANT") as quantidade_total,
                            z."PRD_UNID",
                            CASE
                                WHEN COALESCE(s."PLT_DESC_TIPO", 'BAT') IN ('MINI', 'BAT') THEN COALESCE(s."PLT_DESC_TIPO", 'BAT')
                                WHEN u."PES_TP_PALET" IN ('CHEP', 'CHEPc') THEN u."PES_TP_PALET"
                                ELSE COALESCE(s."PLT_DESC_TIPO", 'BAT')
                            END AS tipo_palete_final
                        FROM "APEDIDOS" x
                        JOIN "APED_ITEM" y ON y."PED_EMP_GRU_P" = x."PED_EMP_GRU" AND y."PED_NUMERO" = x."PED_NUMERO"
                        JOIN "UPRODUTO" z ON z."PRD_CODIGO" = y."PED_PRODUTO"
                        LEFT JOIN "APALETS" s ON y."PED_PALETS" = s."PLT_CODIGO"
                        LEFT JOIN "UPESSOAS" u ON x."PED_PESSOA" = u."PES_CODIGO" AND u."PES_EMPRESA" = x."PED_EMPRESA"
                        WHERE x."PED_PRE_ORDEM" IN %s
                        GROUP BY
                            x."PED_PRE_ORDEM",
                            z."PRD_DESC_RES",
                            z."PRD_UNID",
                            CASE
                                WHEN COALESCE(s."PLT_DESC_TIPO", 'BAT') IN ('MINI', 'BAT') THEN COALESCE(s."PLT_DESC_TIPO", 'BAT')
                                WHEN u."PES_TP_PALET" IN ('CHEP', 'CHEPc') THEN u."PES_TP_PALET"
                                ELSE COALESCE(s."PLT_DESC_TIPO", 'BAT')
                            END
                        ORDER BY quantidade_total DESC;
                    """
                    cur_erp.execute(sql_produtos_pdf, (tuple(todas_pos),))

                    for po, prd_nome, qtd, unid, palete in cur_erp.fetchall():
                        po_str = str(po).strip()
                        if po_str in info_erp and prd_nome:
                            # Converte os dados do banco
                            qtd_num = float(qtd) if qtd is not None else 0
                            unidade = str(unid).strip().upper() if unid else ""
                            tipo_palete = str(palete).strip().upper()
                            
                            # Regra do Granel (Herdada do seu Dashboard)
                            if derivado == 'Sim' or unidade == 'TON':
                                tipo_palete = 'A GRANEL'
                                
                            # Matemática de Paletes
                            qtd_paletes_str = ""
                            if tipo_palete in ['PBR', 'CHEP', 'CHEPC']:
                                divisor = None
                                desc_upper = prd_nome.upper()
                                if "6X5" in desc_upper: divisor = 36
                                elif "10X1" in desc_upper: divisor = 100
                                elif "5X2" in desc_upper: divisor = 104
                                    
                                if divisor and (qtd_num % divisor == 0):
                                    qtd_paletes_str = f" ({int(qtd_num / divisor)} PLTs)"
                                    
                            # Formatação Bonita (Ex: 150 FD | 1200.50 KG)
                            qtd_fmt = f"{int(qtd_num)}" if qtd_num % 1 == 0 else f"{qtd_num:.2f}"
                            unid_fmt = "FD" if unidade == 'FD' else unidade
                            
                            # Monta a string final: "ARROZ BRANCO - 150 FD [PBR] (5 PLTs)"
                            linha_produto = f"{prd_nome.strip()} - {qtd_fmt} {unid_fmt} <b>[{tipo_palete}]</b> <span style='color:#718096; font-size:8px;'>{qtd_paletes_str}</span>"
                            
                            info_erp[po_str]['produtos'].add(linha_produto)
                            
                except Exception as e:
                    print("⚠️ Erro ao buscar dados ERP para o PDF:", e)

            # 3. Monta o HTML do PDF Executivo
            html = f"""
            <html>
            <head>
                <meta charset="utf-8">
                <title>Relatório de Pátio</title>
                <style>
                    body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; padding: 20px; color: #2d3748; }}
                    .header {{ border-bottom: 3px solid #6b2b1f; padding-bottom: 10px; margin-bottom: 20px; }}
                    h2 {{ color: #6b2b1f; margin: 0; font-size: 22px; text-transform: uppercase; letter-spacing: 1px; }}
                    
                    .filtros {{ background: #f7fafc; padding: 12px 15px; border-radius: 8px; font-size: 11px; margin-bottom: 20px; border: 1px solid #e2e8f0; color: #4a5568; line-height: 1.5; }}
                    .filtros strong {{ color: #1a202c; }}
                    
                    table {{ width: 100%; border-collapse: collapse; font-size: 10px; }}
                    th, td {{ border-bottom: 1px solid #e2e8f0; padding: 8px 6px; text-align: left; vertical-align: top; }}
                    th {{ background-color: #edf2f7; color: #4a5568; text-transform: uppercase; font-weight: bold; font-size: 9px; letter-spacing: 0.5px; }}
                    tr:nth-child(even) {{ background-color: #f8fafc; }}
                    
                    /* Design das Badges de Status */
                    .status {{ font-weight: bold; font-size: 9px; padding: 4px 6px; border-radius: 4px; display: inline-block; text-transform: uppercase; border: 1px solid rgba(0,0,0,0.1); }}
                    .bg-pendente {{ background: #fefcbf; color: #975a16; }}
                    .bg-vistoriado {{ background: #ebf8ff; color: #2b6cb0; }}
                    .bg-carregando {{ background: #feebc8; color: #c05621; }}
                    .bg-carregado {{ background: #f0fff4; color: #2f855a; }}
                    .bg-cancelado {{ background: #fff5f5; color: #c53030; }}
                    
                    /* Design dos Produtos */
                    .produtos-lista div {{ border-bottom: 1px dashed #cbd5e0; padding-bottom: 4px; margin-bottom: 4px; color: #2d3748; font-weight: 500; font-size: 9.5px; }}
                    .produtos-lista div:last-child {{ border-bottom: none; margin-bottom: 0; padding-bottom: 0; }}
                    .bold-dark {{ color: #1a202c; font-weight: bold; }}
                </style>
            </head>
            <body onload="window.print();">
                <div class="header">
                    <h2>Relatório Gerencial de Operação</h2>
                </div>
                
                <div class="filtros">
                    <strong>Período:</strong> {data_inicio} até {data_fim} &nbsp;|&nbsp; 
                    <strong>Status:</strong> {status} &nbsp;|&nbsp; 
                    <strong>Unidade:</strong> {local} &nbsp;|&nbsp; 
                    <strong>Tipo:</strong> {texto_tipo_filtro} &nbsp;|&nbsp;
                    <strong>Transportadora:</strong> {transportadora or 'Todas'} <br>
                    <strong>Total de Veículos no Relatório:</strong> {len(rows)}
                </div>
                
                <table>
                    <thead>
                        <tr>
                            <th style="width: 5%;">Hora</th>
                            <th style="width: 8%;">Placa</th>
                            <th style="width: 15%;">Transportadora</th>
                            <th style="width: 8%;">Pré-Ordem</th>
                            <th style="width: 8%;">Pedido</th>
                            <th style="width: 8%;">Embarque</th>
                            <th style="width: 10%;">Status</th>
                            <th style="width: 38%;">Produtos (SKU) - Qtd [Palete]</th>
                        </tr>
                    </thead>
                    <tbody>
            """
            
            # 4. Preenche as linhas cruzando o banco local com o ERP
            for row in rows:
                placa = row[0]
                hora_inicio = row[2] or "--:--"
                status_patio = row[6] or "PENDENTE"
                pre_ordens = str(row[8]) if row[8] else ""
                transportadora = row[9] or "NÃO INFORMADA"
                
                peds, embs, prods = set(), set(), set()
                
                if pre_ordens:
                    for p in pre_ordens.replace(' - ', ',').replace('/', ',').split(','):
                        p_clean = p.strip()
                        if p_clean in info_erp:
                            peds.update(info_erp[p_clean]['ped'])
                            embs.update(info_erp[p_clean]['emb'])
                            prods.update(info_erp[p_clean]['produtos'])

                ped_str = "<br>".join(peds) if peds else "-"
                emb_str = "<br>".join(embs) if embs else "-"
                po_str = "<br>".join([p.strip() for p in pre_ordens.replace(' - ', ',').replace('/', ',').split(',')]) if pre_ordens else "-"
                
                if prods:
                    html_produtos = "<div class='produtos-lista'>" + "".join([f"<div>• {prd}</div>" for prd in prods]) + "</div>"
                else:
                    html_produtos = "<span style='color: #a0aec0;'>Aguardando ERP...</span>"
                
                cor_status = "bg-pendente"
                if status_patio == 'VISTORIADO': cor_status = "bg-vistoriado"
                elif status_patio == 'CARREGANDO': cor_status = "bg-carregando"
                elif status_patio == 'CARREGADO': cor_status = "bg-carregado"
                elif status_patio == 'CANCELADO': cor_status = "bg-cancelado"
                
                html += f"""
                    <tr>
                        <td class="bold-dark">{hora_inicio}</td>
                        <td class="bold-dark">{placa}</td>
                        <td>{transportadora}</td>
                        <td style="color: #2b6cb0; font-weight: bold;">{po_str}</td>
                        <td>{ped_str}</td>
                        <td>{emb_str}</td>
                        <td><span class='status {cor_status}'>{status_patio}</span></td>
                        <td>{html_produtos}</td>
                    </tr>
                """
            
            html += """
                    </tbody>
                </table>
            </body>
            </html>
            """
            nome_arquivo = f"Relatorio_Patio_{data_inicio}_a_{data_fim}.html"
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.html', prefix='rel_')
            tmp.write(html.encode('utf-8'))
            tmp.close()
            _jobs[job_id] = {'status': 'pronto', 'arquivo': tmp.name, 'nome': nome_arquivo, 'erro': None}

    except Exception as e:
        traceback.print_exc()
        print(f"❌ Erro ao exportar relatório: {e}")
        _jobs[job_id] = {'status': 'erro', 'arquivo': None, 'nome': None, 'erro': str(e)}
    finally:
        if conn: conn.close()


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)