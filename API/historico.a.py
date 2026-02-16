from dotenv import load_dotenv
from flask import Flask, request, jsonify, make_response, send_file
from flask_cors import CORS
import psycopg2
from datetime import datetime
import traceback
import sys
import os
import base64
import io

app = Flask(__name__)

# Configuração CORS (Permite acesso do Angular)
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)

# 🗄️ CONFIGURAÇÃO DO BANCO (Mesma do agend.py)
load_dotenv()

DB_BUSCA = {
    "host": os.getenv("DB_HOST"),
    "database": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASS"),
    "port": os.getenv("DB_PORT")
}


print("----------------------------------------------------------")
print("📜 API DE HISTÓRICO INICIADA NA PORTA 5002 (MODO UNIFICADO)")
print("📡 Aguardando conexões no DB_BUSCA...")
print("----------------------------------------------------------")

# Middleware para Logs e CORS
@app.before_request
def log_request_info():
    if request.method != 'OPTIONS':
        print(f"\n🔔 [REQ] {request.method} {request.path}")
    
    if request.method == "OPTIONS":
        response = make_response()
        response.headers.add("Access-Control-Allow-Origin", "*")
        response.headers.add("Access-Control-Allow-Headers", "Content-Type, Authorization, Cache-Control, Pragma")
        response.headers.add("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        return response

# --- ROTA PRINCIPAL DE HISTÓRICO (PAGINADA) ---
# Substitua SOMENTE a função get_historico no seu arquivo

# Substitua SOMENTE esta função no historico.a.py

@app.get("/historico")
def get_historico():
    conn = None
    try:
        # 1. Parâmetros
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('limit', 20, type=int)
        placa_filtro = request.args.get('placa', '').strip().upper()
        transp_filtro = request.args.get('transportadora', '').strip().upper()
        local_filtro = request.args.get('local', '').strip()

        offset = (page - 1) * per_page

        conn = psycopg2.connect(**DB_BUSCA)
        cur = conn.cursor()

        # 2. Filtros Dinâmicos
        where_parts = ["1=1"]
        params_query = []

        if local_filtro and local_filtro != 'Qualquer':
            where_parts.append("AND a.local = %s")
            params_query.append(local_filtro)

        if placa_filtro:
            placa_limpa = placa_filtro.replace('-', '')
            where_parts.append("REGEXP_REPLACE(UPPER(a.placa), '[^A-Z0-9]', '', 'g') LIKE %s")
            params_query.append(f"%{placa_limpa}%")

        if transp_filtro:
            where_parts.append("UPPER(COALESCE(r.transportadora, '')) LIKE %s")
            params_query.append(f"%{transp_filtro}%")

        where_final = "WHERE " + " ".join(where_parts)

        # 3. Contagem
        cur.execute(f"""
            SELECT COUNT(*) 
            FROM "vistoria"."VAGENDAMENTO" a
            INNER JOIN "vistoria"."VRESPOSTAS" r ON CAST(r.id_agend AS VARCHAR) = CAST(a.id AS VARCHAR)
            {where_final}
        """, tuple(params_query))
        total_items = cur.fetchone()[0]
        total_pages = (total_items + per_page - 1) // per_page

        # 4. QUERY DE DADOS
        sql_dados = f"""
            SELECT
                a.id, 
                a.placa, 
                to_char(r.vistoria_fim, 'DD/MM/YYYY'), 
                to_char(r.vistoria_inicio, 'HH24:MI'),
                to_char(r.vistoria_fim, 'HH24:MI'),
                
                COALESCE(r.nr_ordem, CONCAT_WS(', ', 
                    NULLIF(a.pre_ordem1,''), NULLIF(a.pre_ordem2,''), NULLIF(a.pre_ordem3,''),
                    NULLIF(a.pre_ordem4,''), NULLIF(a.pre_ordem5,'')
                )),
                
                COALESCE(r.transportadora, y."TRP_NOME", 'Aguardando...'),
                r.status,
                r.caminhao_liberado, 
                r.motorista, 
                r.vistoriador,
                
                -- 🔥 CORREÇÃO CIRÚRGICA AQUI:
                -- Se existe PDF (r.pdf_documento), retornamos a.id (ID DO AGENDAMENTO).
                -- Motivo: A rota /pdf/<id> busca por "WHERE id_agend = ...".
                -- Então precisamos passar o ID do Agendamento (39) para ela achar a Vistoria certa (31).
                CASE WHEN r.pdf_documento IS NOT NULL THEN a.id ELSE NULL END,
                
                r.observacoes

            FROM "vistoria"."VAGENDAMENTO" a
            INNER JOIN "vistoria"."VRESPOSTAS" r ON CAST(r.id_agend AS VARCHAR) = CAST(a.id AS VARCHAR)
            LEFT JOIN "UTRAPLACA" x ON REGEXP_REPLACE(UPPER(a.placa), '[^A-Z0-9]', '', 'g') = REGEXP_REPLACE(UPPER(x."PLA_PLACA"), '[^A-Z0-9]', '', 'g')
            LEFT JOIN "UTRAPROPR" y ON x."PLA_PROPR" = y."TRP_CODIGO"
            
            {where_final}
            
            ORDER BY r.vistoria_fim DESC
            LIMIT %s OFFSET %s
        """
        
        params_dados = list(params_query)
        params_dados.extend([per_page, offset])
        
        cur.execute(sql_dados, tuple(params_dados))
        rows = cur.fetchall()

        # 5. Mapeamento
        final = []
        for r in rows:
            final.append({
                "id": r[0], "placa": r[1], "data": r[2], "hora": f"{r[3]} - {r[4]}",
                "po": r[5], "transportadora": r[6], "status": r[7], "liberado": r[8],
                "motorista": r[9], "vistoriador": r[10], 
                "pdf": r[11], # Agora contém o ID do Agendamento (correto para a rota atual)
                "observacoes": r[12]
            })

        return jsonify({ 
            "data": final, 
            "meta": { "page": page, "total_pages": total_pages, "total_items": total_items } 
        })

    except Exception as e:
        print("❌ Erro Historico:", e)
        return jsonify({"error": str(e)}), 500
    finally:
        if conn: conn.close()

# --- ROTA PARA BAIXAR O PDF ---
@app.route('/pdf/<id_agendamento>', methods=['GET'])
def get_pdf(id_agendamento):
    conn = None
    try:
        # 🔥 ALTERAÇÃO: Conecta no DB_BUSCA
        conn = psycopg2.connect(**DB_BUSCA)
        cur = conn.cursor()
        
        cur.execute('SELECT pdf_documento FROM "vistoria"."VRESPOSTAS" WHERE CAST(id_agend AS VARCHAR) = %s', (id_agendamento,))
        row = cur.fetchone()
        
        if row and row[0]:
            pdf_bytes = row[0]
            
            response = make_response(bytes(pdf_bytes))
            response.headers['Content-Type'] = 'application/pdf'
            response.headers['Content-Disposition'] = f'inline; filename=vistoria_{id_agendamento}.pdf'
            return response
        else:
            return jsonify({"error": "PDF não encontrado"}), 404

    except Exception as e:
        print(f"❌ Erro ao baixar PDF {id_agendamento}: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if conn: conn.close()

# --- AGENDAMENTOS DIA ---
# Em historico.a.py

# No ficheiro historico.a.py
@app.route('/agendamentos-dia', methods=['GET'])
def get_agendamentos_dia():
    data_str = request.args.get('data') 
    local_str = request.args.get('local')

    if not data_str or not local_str:
        return jsonify([])

    conn = None
    try:
        conn = psycopg2.connect(**DB_BUSCA)
        cur = conn.cursor()
        
        # SQL com 3 parâmetros (%s) para garantir que a data e o local batam sempre
        # No arquivo historico.a.py
        sql = """
            SELECT a.hr_inicio, a.hr_fim, a.id
            FROM "vistoria"."VAGENDAMENTO" a
            WHERE (
                CAST(a.data AS DATE) = CAST(%s AS DATE) 
                OR to_char(a.data, 'YYYY-MM-DD') = %s
            )
            -- ✅ CORRIGIDO: TRIM remove espaços extras que podem vir do banco
            AND UPPER(TRIM(a.local)) = UPPER(TRIM(%s)) 
            AND NOT EXISTS (
                SELECT 1 
                FROM "vistoria"."VRESPOSTAS" r 
                WHERE CAST(r.id_agend AS VARCHAR) = CAST(a.id AS VARCHAR) 
                AND r.status = 'Cancelada'
            )
        """
        # Passando os 3 parâmetros corretamente
        cur.execute(sql, (data_str, data_str, local_str))
                

        rows = cur.fetchall()
        
        ocupacoes = []
        for row in rows:
            # O row[0] e row[1] são hr_inicio e hr_fim
            inicio = str(row[0])[:5] if row[0] else None
            fim = str(row[1])[:5] if row[1] else None
            id_agend = str(row[2])
            
            if inicio and fim:
                ocupacoes.append({"inicio": inicio, "fim": fim, "id": id_agend})

        return jsonify(ocupacoes)

    except Exception as e:
        print(f"❌ Erro ao buscar ocupação: {e}")
        return jsonify([])
    finally:
        if conn: conn.close()

# --- MONITORAMENTO (COM ORDENAÇÃO UNIFICADA) ---
# Substitua APENAS a função monitoramento_excel

@app.get("/monitoramento")
def monitoramento_excel():
    conn = None
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('limit', 20, type=int)
        busca_raw = request.args.get('q', '').strip()
        local_filtro = request.args.get('local', '').strip()
        status_filtro = request.args.get('status', '').strip() # 👈 NOVO PARÂMETRO
        
        busca = busca_raw.upper()
        offset = (page - 1) * per_page

        conn = psycopg2.connect(**DB_BUSCA)
        cur = conn.cursor()

        where_parts = ["1=1"]
        params_query = []

        # Filtro de Local
        if local_filtro and local_filtro != 'Qualquer':
            where_parts.append("AND a.local = %s")
            params_query.append(local_filtro)

        # 👈 NOVO: Filtro de Status (Com ou Sem Resposta)
        if status_filtro == 'Pendentes':
            where_parts.append("AND r.status IS NULL")
        elif status_filtro == 'Realizadas':
            where_parts.append("AND r.status IS NOT NULL")
            
        if busca:
            termo = f"%{busca}%"
            condicoes = [
                "UPPER(a.placa) LIKE %s",
                "UPPER(COALESCE(r.transportadora, '')) LIKE %s",
                "UPPER(COALESCE(r.motorista, '')) LIKE %s",
                "to_char(a.data, 'DD/MM/YYYY') LIKE %s",
                "UPPER(a.pre_ordem1) LIKE %s"
            ]
            params_query.extend([termo] * 5)
            where_parts.append(f"AND ({' OR '.join(condicoes)})")

        where_final = "WHERE " + " ".join(where_parts)

        # Contagem
        cur.execute(f"""
            SELECT COUNT(*) 
            FROM "vistoria"."VAGENDAMENTO" a
            LEFT JOIN "vistoria"."VRESPOSTAS" r ON CAST(r.id_agend AS VARCHAR) = CAST(a.id AS VARCHAR)
            {where_final}
        """, tuple(params_query))
        total_items = cur.fetchone()[0]
        total_pages = (total_items + per_page - 1) // per_page

        sql_dados = f"""
            SELECT
                a.id, 
                a.placa, 
                to_char(COALESCE(r.vistoria_inicio, CAST(a.data AS TIMESTAMP)), 'DD/MM/YYYY'), 
                COALESCE(to_char(r.vistoria_inicio, 'HH24:MI'), to_char(a.hr_inicio, 'HH24:MI')),
                COALESCE(to_char(r.vistoria_fim, 'HH24:MI'), to_char(a.hr_fim, 'HH24:MI')),
                
                -- [5] 🔥 CORREÇÃO AQUI: PRÉ-ORDEM DIRETO DO AGENDAMENTO
                -- Antes: COALESCE(r.nr_ordem, ...) -> Priorizava a resposta antiga
                -- Agora: CONCAT_WS(...) -> Pega sempre o que está editado no Agendamento
                CONCAT_WS(', ', 
                    NULLIF(a.pre_ordem1,''), NULLIF(a.pre_ordem2,''), NULLIF(a.pre_ordem3,''),
                    NULLIF(a.pre_ordem4,''), NULLIF(a.pre_ordem5,'')
                ),
                
                COALESCE(r.transportadora, y."TRP_NOME", 'Aguardando...'),
                CASE WHEN r.status = 'Concluida' THEN 'SIM' WHEN r.status = 'Cancelada' THEN 'CANCELADO' ELSE 'NÃO' END,
                r.caminhao_liberado, r.motorista, r.vistoriador,
                
                -- [11] PDF ID (ID da Vistoria)
                CASE WHEN r.pdf_documento IS NOT NULL THEN r.id ELSE NULL END,

                -- [12] Duração
                CAST(EXTRACT(EPOCH FROM (a.hr_fim - a.hr_inicio))/60 AS INTEGER),
                
                -- [13-18] Campos Edição
                a.local,
                a.pre_ordem1,
                a.pre_ordem2,
                a.pre_ordem3,
                a.pre_ordem4,
                a.pre_ordem5

            FROM "vistoria"."VAGENDAMENTO" a
            LEFT JOIN "vistoria"."VRESPOSTAS" r ON CAST(r.id_agend AS VARCHAR) = CAST(a.id AS VARCHAR)
            LEFT JOIN "UTRAPLACA" x ON REGEXP_REPLACE(UPPER(a.placa), '[^A-Z0-9]', '', 'g') = REGEXP_REPLACE(UPPER(x."PLA_PLACA"), '[^A-Z0-9]', '', 'g')
            LEFT JOIN "UTRAPROPR" y ON x."PLA_PROPR" = y."TRP_CODIGO"
            
            {where_final}
            
            ORDER BY 
                COALESCE(r.vistoria_inicio, CAST(a.data AS TIMESTAMP) + a.hr_inicio) DESC,
                COALESCE(r.vistoria_fim, CAST(a.data AS TIMESTAMP) + a.hr_fim) DESC
            
            LIMIT %s OFFSET %s
        """
        
        params_dados = list(params_query)
        params_dados.extend([per_page, offset])
        cur.execute(sql_dados, tuple(params_dados))
        rows = cur.fetchall()

        # COLETA DE IDS PARA O ERP (OTIMIZADO)
        todas_pos = set()
        resultado_temp = []
        
        for r in rows:
            # O índice r[5] agora contém os dados atualizados do Agendamento.
            # O código abaixo vai usar esses dados novos para buscar no ERP.
            pos_str = r[5] 
            pos_list = []
            if pos_str:
                # Separa por vírgula se houver mais de uma
                for p in pos_str.replace('/',',').split(','):
                    if p.strip().isdigit():
                        todas_pos.add(p.strip())
                        pos_list.append(p.strip())

            resultado_temp.append({
                "id": r[0], "placa": r[1], "data": r[2], "h_inicio": r[3], "h_fim": r[4],
                "pre_ordem": r[5], "transportadora": r[6], "vistoria_realizada": r[7],
                "liberado": r[8], "motorista": r[9], "vistoriador": r[10], 
                "pdf": r[11],
                "tem_pdf": r[11], # Mantém compatibilidade
                
                "pos_ids": pos_list, # Lista de IDs para cruzar com o ERP abaixo

                "duracao": r[12], "local": r[13],
                "pre_ordem1": r[14], "pre_ordem2": r[15], "pre_ordem3": r[16], "pre_ordem4": r[17], "pre_ordem5": r[18]
            })

        # BUSCA ÚNICA NO ERP (SEM LOOP DE API)
        info_erp = {}
        if todas_pos:
            try:
                conn_erp = psycopg2.connect(**DB_BUSCA)
                cur_erp = conn_erp.cursor()
                # Busca tudo de uma vez usando IN (...)
                sql_detalhes = f"""
                    SELECT CAST(a."PED_PRE_ORDEM" AS VARCHAR), a."PED_NUMERO", b."EMB_NUMERO", c."MV_NOTA" 
                    FROM "APEDIDOS" a 
                    LEFT JOIN "AEMBARITE" b ON a."PED_NUMERO" = b."EMB_PEDIDO" AND a."PED_EMPRESA" = b."EMB_EMPRESA" 
                    LEFT JOIN "AMOVPRI" c ON c."MV_PEDIDO" = a."PED_NUMERO" 
                    WHERE a."PED_PRE_ORDEM" IN %s
                """
                cur_erp.execute(sql_detalhes, (tuple(todas_pos),))
                
                for row_erp in cur_erp.fetchall():
                    po, ped, emb, nota = row_erp
                    if po not in info_erp: info_erp[po] = {'ped': set(), 'emb': set(), 'nf': set()}
                    if ped: info_erp[po]['ped'].add(str(ped))
                    if emb: info_erp[po]['emb'].add(str(emb))
                    if nota: info_erp[po]['nf'].add(str(nota))
                conn_erp.close()
            except Exception as e:
                print("Erro ERP:", e)

        # MONTAGEM FINAL
        final = []
        for item in resultado_temp:
            peds, embs, nfs = set(), set(), set()
            
            # Cruza os IDs do agendamento com o cache do ERP
            for po in item['pos_ids']:
                if po in info_erp:
                    peds.update(info_erp[po]['ped'])
                    embs.update(info_erp[po]['emb'])
                    nfs.update(info_erp[po]['nf'])
            
            item['pedido'] = " / ".join(peds) if peds else "-"
            item['embarque'] = " / ".join(embs) if embs else "-"
            item['nota'] = " / ".join(nfs) if nfs else "-"
            
            del item['pos_ids'] # Remove auxiliar
            final.append(item)

        return jsonify({ "data": final, "meta": { "page": page, "total_pages": total_pages, "total_items": total_items } })

    except Exception as e:
        print("❌ Erro Monitoramento:", e)
        return jsonify({"error": str(e)}), 500
    finally:
        if conn: conn.close()
# --- ROTA DE DETALHES ---
# Substitua SOMENTE a função get_detalhes_vistoria

@app.route('/detalhes/<id_agendamento>', methods=['GET'])
def get_detalhes_vistoria(id_agendamento):
    conn = None
    try:
        conn = psycopg2.connect(**DB_BUSCA)
        cur = conn.cursor()

        # 🔥 QUERY AJUSTADA:
        # 1. Busca pelo ID do Agendamento (a.id)
        # 2. Ordena por vistoria_fim DESC para pegar a última resposta válida
        
        sql_base = """
            SELECT 
                a.id, a.placa, a.data, a.hr_inicio, a.local,
                
                -- [5-9] PRÉ-ORDENS DO AGENDAMENTO (ORIGEM A)
                a.pre_ordem1, a.pre_ordem2, a.pre_ordem3, a.pre_ordem4, a.pre_ordem5,
                
                -- [10] Status da Resposta
                r.status,
                
                -- [11-18] Dados Gerais da Resposta
                to_char(r.vistoria_fim, 'DD/MM/YYYY HH24:MI'), -- 11
                r.vistoriador, r.motorista, r.observacoes, r.caminhao_liberado,
                r.ultimos_produtos_transportados, r.tipo_veiculo, r.produto,
                
                -- [19-29] Checklist
                r.chk_limpeza_insetos, r.chk_danos_frestas, r.chk_umidade_mofo,
                r.chk_residuos_carroceria, r.chk_outros_produtos_odores,
                r.chk_bocas_graneleiras, r.chk_lonas_forracao, r.chk_chapas_mdf,
                r.chk_lonas_integras, r.chk_cantoneiras_cintas, r.chk_tampas_vedacao,
                
                -- [30-34] Fotos (Booleanos)
                (r.foto_placa_1 IS NOT NULL), (r.foto_placa_2 IS NOT NULL), (r.foto_placa_3 IS NOT NULL),
                (r.foto_interior_carroceria IS NOT NULL), (r.foto_interior_carroceria2 IS NOT NULL),
                
                -- [35-36] Placas Extras
                r.placa_2, r.placa_3,
                
                -- [37-40] Específicos
                r.chk_porta_altura, r.chk_abertura_total, r.chk_assoalho_liso, r.chk_peso_container

            FROM "vistoria"."VAGENDAMENTO" a
            LEFT JOIN "vistoria"."VRESPOSTAS" r ON CAST(r.id_agend AS VARCHAR) = CAST(a.id AS VARCHAR)
            WHERE CAST(a.id AS VARCHAR) = %s
            
            -- 🔥 GARANTE QUE PEGA A VISTORIA MAIS RECENTE/VÁLIDA
            ORDER BY r.vistoria_fim DESC NULLS LAST
            LIMIT 1
        """
        
        cur.execute(sql_base, (id_agendamento,))
        row = cur.fetchone()
        
        if not row:
            return jsonify({"encontrado": False, "mensagem": "Agendamento não encontrado"}), 404

        # --- PROCESSAMENTO DAS PRÉ-ORDENS (VINDAS DO AGENDAMENTO) ---
        lista_pre_ordens = []
        # Índices 5, 6, 7, 8, 9 correspondem a pre_ordem1...5 do SELECT acima
        for i in range(5, 10): 
            if row[i] and str(row[i]).strip():
                lista_pre_ordens.append(str(row[i]).strip())

        # --- BUSCA DADOS FISCAIS NO ERP ---
        dados_emitidos = []
        produtos_reais = []
        
        if lista_pre_ordens:
            # 1. Busca Pedidos e Notas
            cur.execute("""
                SELECT a."PED_PRE_ORDEM", a."PED_NUMERO", b."EMB_NUMERO", c."MV_NOTA"
                FROM "APEDIDOS" a
                LEFT JOIN "AEMBARITE" b ON a."PED_NUMERO" = b."EMB_PEDIDO" AND a."PED_EMPRESA" = b."EMB_EMPRESA"
                LEFT JOIN "AMOVPRI" c ON c."MV_PEDIDO" = a."PED_NUMERO"
                WHERE a."PED_PRE_ORDEM" IN %s
            """, (tuple(lista_pre_ordens),))
            
            temp_dict = {}
            for po, ped, emb, nota in cur.fetchall():
                # Chave única para agrupar notas do mesmo pedido/embarque
                key = (str(po), str(ped), str(emb))
                if key not in temp_dict: temp_dict[key] = []
                if nota: temp_dict[key].append(str(nota))

            for (po, ped, emb), notas in temp_dict.items():
                dados_emitidos.append({
                    "pre_ordem": po, 
                    "pedido": ped, 
                    "embarque": emb, 
                    "notas": " / ".join(notas) if notas else "-"
                })

            # 2. Busca Produtos (Agrupados)
            cur.execute("""
                SELECT z."PRD_DESC_RES", SUM(y."PED_QUANT"), z."PRD_UNID"
                FROM "APEDIDOS" x
                JOIN "APED_ITEM" y ON y."PED_EMP_GRU_P" = x."PED_EMP_GRU" AND y."PED_NUMERO" = x."PED_NUMERO"
                JOIN "UPRODUTO" z ON z."PRD_CODIGO" = y."PED_PRODUTO"
                WHERE x."PED_PRE_ORDEM" IN %s
                GROUP BY z."PRD_DESC_RES", z."PRD_UNID"
            """, (tuple(lista_pre_ordens),))
            
            for prd_nome, qtd, unid in cur.fetchall():
                unid_fmt = "FD30" if str(unid).strip().upper() == 'FD' else str(unid).strip()
                produtos_reais.append(f"{prd_nome.strip()} - {int(qtd)} {unid_fmt}")

        # Se não achou produto no ERP, tenta usar o manual da vistoria (row[18])
        produto_final = " / ".join(produtos_reais) if produtos_reais else (row[18] or "-")

        # --- RETORNO JSON ---
        return jsonify({
            "encontrado": True,
            "status": row[10] or "Pendente",
            "data_finalizacao": row[11],
            "responsavel": row[12],
            "motorista": row[13],
            "observacoes": row[14],
            "caminhao_liberado": row[15],
            "produto_real": produto_final,
            
            # Array de dados fiscais
            "dados_emitidos": dados_emitidos,
            
            # Checklist
            "checklist": {
                "Limpeza/Insetos": row[19], 
                "Danos/Frestas": row[20], 
                "Umidade/Mofo": row[21],
                "Resíduos": row[22], 
                "Odores": row[23], 
                "Bocas Graneleiras": row[24],
                "Lonas/Forração": row[25], 
                "Chapas MDF": row[26], 
                "Lonas Integras": row[27],
                "Cantoneiras/Cintas": row[28], 
                "Tampas/Vedação": row[29]
            },
            
            # Específicos
            "especificos": {
                "Altura Porta 2,30m": row[37], 
                "Abertura Total": row[38],
                "Assoalho Liso": row[39], 
                "Peso/Tara Container": row[40]
            },
            
            # Fotos (True/False para o front saber se deve pedir a imagem)
            "fotos": {
                "placa1": row[30], "placa2": row[31], "placa3": row[32],
                "interior1": row[33], "interior2": row[34]
            },
            "tipo_veiculo": row[17],
            "placas_extras": " / ".join(filter(None, [row[35], row[36]]))
        })

    except Exception as e:
        print(f"❌ Erro Detalhes: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if conn: conn.close()

        
# --- ROTA PARA SERVIR AS FOTOS DO BANCO ---
@app.route('/foto/<id_agendamento>/<tipo>', methods=['GET'])
def get_foto_banco(id_agendamento, tipo):
    conn = None
    try:
        mapa_colunas = {
            'placa1': 'foto_placa_1',
            'placa2': 'foto_placa_2',
            'placa3': 'foto_placa_3',
            'interior1': 'foto_interior_carroceria',
            'interior2': 'foto_interior_carroceria2',
            'ass_motorista': 'ass_motorista',
            'ass_vistoriador': 'ass_vistoriador'
        }
        
        coluna = mapa_colunas.get(tipo)
        if not coluna:
            return jsonify({"error": "Tipo de foto inválido"}), 400

        conn = psycopg2.connect(**DB_BUSCA)
        cur = conn.cursor()
        
        sql = f'SELECT {coluna} FROM "vistoria"."VRESPOSTAS" WHERE CAST(id_agend AS VARCHAR) = %s'
        cur.execute(sql, (id_agendamento,))
        row = cur.fetchone()
        
        # Verifica se existe e se tem tamanho maior que 0
        if row and row[0] and len(row[0]) > 0:
            imagem_bytes = row[0]
            mime = 'image/png' if 'assinatura' in coluna else 'image/jpeg'
            
            # 🔥 CRIA A RESPOSTA COM CABEÇALHOS QUE MATAM O CACHE
            response = make_response(send_file(io.BytesIO(imagem_bytes), mimetype=mime))
            response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
            return response
        else:
            return jsonify({"error": "Imagem vazia ou não encontrada"}), 404

    except Exception as e:
        print(f"❌ Erro ao buscar foto {tipo}: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if conn: conn.close()

        
@app.route('/verificar-duplicidade', methods=['GET'])
def verificar_duplicidade():
    conn = None
    try:
        placa = request.args.get('placa')
        data = request.args.get('data')
        ordem = request.args.get('ordem') # Primeira ordem

        # Se faltar dados básicos, deixa passar (o frontend já valida antes)
        if not all([placa, data, ordem]):
            return jsonify({"duplicado": False})

        # 🔥 ALTERAÇÃO: Conecta no DB_BUSCA
        conn = psycopg2.connect(**DB_BUSCA)
        cur = conn.cursor()

        # Verifica duplicidade IGNORANDO A HORA (a.hr_inicio)
        # Regra: Mesma Placa + Mesmo Dia + Mesma Ordem Principal
        sql = """
            SELECT 1 
            FROM "vistoria"."VAGENDAMENTO" a
            WHERE a.placa = %s 
            AND a.data = %s 
            AND a.pre_ordem1 = %s
            AND NOT EXISTS (
                SELECT 1 FROM "vistoria"."VRESPOSTAS" r 
                WHERE CAST(r.id_agend AS VARCHAR) = CAST(a.id AS VARCHAR) 
                AND r.status = 'Cancelada'
            )
            LIMIT 1
        """
        
        cur.execute(sql, (placa, data, ordem))
        existe = cur.fetchone()

        return jsonify({"duplicado": bool(existe)})

    except Exception as e:
        print(f"❌ Erro verificação duplicidade: {e}")
        return jsonify({"duplicado": False}), 200 
    finally:
        if conn: conn.close()

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5002, debug=True, use_reloader=False)