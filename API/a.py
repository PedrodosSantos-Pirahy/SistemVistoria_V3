from dotenv import load_dotenv
from flask import Flask, request, jsonify, make_response, send_file
from flask_cors import CORS
import psycopg2
from psycopg2 import pool 
from psycopg2.extras import execute_batch # Adicione isso lá nos imports do topo do arquivo# <-- TEM QUE TER ESSA LINHA
from datetime import datetime
import traceback
import sys
import os
import base64
from pypdf import PdfWriter, PdfReader
import io
import platform
import subprocess
import tempfile


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

try:
    db_pool = pool.ThreadedConnectionPool(1, 20, **DB_BUSCA)
    if db_pool:
        print("✅ Pool de conexões criado com sucesso!")
except Exception as e:
    print(f"❌ ERRO CRÍTICO ao criar o pool de conexões: {e}")


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
       # 2. Filtros Dinâmicos
        where_parts = ["1=1"]
        params_query = []

        if local_filtro and local_filtro != 'Qualquer':
            where_parts.append("AND a.local = %s")
            params_query.append(local_filtro)

        if placa_filtro:
            placa_limpa = placa_filtro.replace('-', '')
            # 👇 CORREÇÃO: Adicionamos o 'AND ' aqui no começo!
            where_parts.append("AND REGEXP_REPLACE(UPPER(a.placa), '[^A-Z0-9]', '', 'g') LIKE %s")
            params_query.append(f"%{placa_limpa}%")

        if transp_filtro:
            # 👇 CORREÇÃO: Adicionamos o 'AND ' aqui no começo também!
            where_parts.append("AND UPPER(COALESCE(r.transportadora, '')) LIKE %s")
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
                
                -- BUSCA SEGURA DA TRANSPORTADORA (LIMIT 1)
                COALESCE(r.transportadora, 
                    (SELECT y2."TRP_NOME" 
                     FROM "UTRAPLACA" x2 
                     JOIN "UTRAPROPR" y2 ON x2."PLA_PROPR" = y2."TRP_CODIGO" 
                     WHERE REGEXP_REPLACE(UPPER(x2."PLA_PLACA"), '[^A-Z0-9]', '', 'g') = REGEXP_REPLACE(UPPER(a.placa), '[^A-Z0-9]', '', 'g') 
                     LIMIT 1), 
                'Aguardando...'),
                
                r.status,
                r.caminhao_liberado, 
                r.motorista, 
                r.vistoriador,
                CASE WHEN r.pdf_documento IS NOT NULL THEN a.id ELSE NULL END,
                r.observacoes

            FROM "vistoria"."VAGENDAMENTO" a
            INNER JOIN "vistoria"."VRESPOSTAS" r ON CAST(r.id_agend AS VARCHAR) = CAST(a.id AS VARCHAR)
            
            -- 🔥 AS LINHAS DO 'LEFT JOIN UTRAPLACA' FORAM DELETADAS DAQUI TAMBÉM! 🔥
            
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
        sql = """
            SELECT a.hr_inicio, a.hr_fim, a.id, COALESCE(a.derivado, FALSE) AS derivado
            FROM "vistoria"."VAGENDAMENTO" a
            WHERE (
                CAST(a.data AS DATE) = CAST(%s AS DATE)
                OR to_char(a.data, 'YYYY-MM-DD') = %s
            )
            AND UPPER(TRIM(a.local)) = UPPER(TRIM(%s))
            AND NOT EXISTS (
                SELECT 1
                FROM "vistoria"."VRESPOSTAS" r
                WHERE CAST(r.id_agend AS VARCHAR) = CAST(a.id AS VARCHAR)
                AND r.status = 'Cancelada'
            )
        """
        cur.execute(sql, (data_str, data_str, local_str))

        rows = cur.fetchall()

        ocupacoes = []
        for row in rows:
            inicio   = str(row[0])[:5] if row[0] else None
            fim      = str(row[1])[:5] if row[1] else None
            id_agend = str(row[2])
            derivado = bool(row[3])

            if inicio and fim:
                ocupacoes.append({"inicio": inicio, "fim": fim, "id": id_agend, "derivado": derivado})

        return jsonify(ocupacoes)

    except Exception as e:
        print(f"❌ Erro ao buscar ocupação: {e}")
        return jsonify([])
    finally:
        if conn: conn.close()

# --- MONITORAMENTO (COM ORDENAÇÃO UNIFICADA) ---
@app.get("/monitoramento")
def monitoramento_excel():
    conn = None
    cur = None
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('limit', 20, type=int)
        busca_raw = request.args.get('q', '').strip()
        local_filtro = request.args.get('local', '').strip()
        status_filtro = request.args.get('status', '').strip() 
        busca_erp = request.args.get('erp', '').strip()
        derivado_filtro = request.args.get('derivado', 'Todas').strip()
        criador_filtro = request.args.get('criador', '').strip()
        busca = busca_raw.upper()
        offset = (page - 1) * per_page

        # 🔥 CORREÇÃO 1: Usando o Pool global!
        conn = db_pool.getconn()
        cur = conn.cursor()

        where_parts = ["1=1"]
        params_query = []

        if local_filtro and local_filtro != 'Qualquer':
            where_parts.append("AND UPPER(TRIM(a.local)) = UPPER(TRIM(%s))")
            params_query.append(local_filtro)

        if status_filtro == 'AGUARDANDO':
            where_parts.append("AND (a.status_patio IN ('PENDENTE', 'ATRASADO') OR a.status_patio IS NULL)")
        elif status_filtro in ['VISTORIADO', 'CARREGANDO', 'CARREGADO', 'CANCELADO']:
            where_parts.append("AND a.status_patio = %s")
            params_query.append(status_filtro)

        if derivado_filtro == 'Sim':
            where_parts.append("AND a.derivado = TRUE")
        elif derivado_filtro == 'Nao':
            where_parts.append("AND (a.derivado = FALSE OR a.derivado IS NULL)")

        if criador_filtro:
            where_parts.append("AND UPPER(TRIM(a.criado_por)) = UPPER(TRIM(%s))")
            params_query.append(criador_filtro)

        # BUSCA UNIFICADA
        if busca:
            termo_like = f"%{busca}%"
            ids_via_erp = []
            placas_via_transp = [] # 🔥 NOVO: Array para guardar as placas da transportadora pesquisada

            # 1. Busca por Número (Nota Fiscal ou Embarque)
            if busca.isdigit():
                try:
                    sql_erp = """
                        SELECT DISTINCT a."PED_PRE_ORDEM"
                        FROM "APEDIDOS" a 
                        LEFT JOIN "AEMBARITE" b ON a."PED_NUMERO" = b."EMB_PEDIDO" AND a."PED_EMPRESA" = b."EMB_EMPRESA" 
                        LEFT JOIN "AMOVPRI" c ON c."MV_PEDIDO" = a."PED_NUMERO" 
                        WHERE a."PED_DT_PED" >= CURRENT_DATE - INTERVAL '12 months'
                          AND (CAST(b."EMB_NUMERO" AS VARCHAR) = %s 
                            OR CAST(c."MV_NOTA" AS VARCHAR) = %s)
                    """
                    cur.execute(sql_erp, (busca, busca))
                    ids_via_erp = [str(r[0]).strip() for r in cur.fetchall() if r[0]]
                except Exception as e:
                    print(f"⚠️ Erro silencioso na busca ERP (Notas): {e}")

            # 🔥 2. Busca por Texto (Nome da Transportadora)
            if not busca.isdigit():
                try:
                    sql_transp = """
                        SELECT REGEXP_REPLACE(UPPER(x."PLA_PLACA"), '[^A-Z0-9]', '', 'g')
                        FROM "UTRAPLACA" x
                        JOIN "UTRAPROPR" y ON x."PLA_PROPR" = y."TRP_CODIGO"
                        WHERE UPPER(y."TRP_NOME") LIKE %s
                    """
                    cur.execute(sql_transp, (termo_like,))
                    placas_via_transp = [str(r[0]).strip() for r in cur.fetchall() if r[0]]
                except Exception as e:
                    print(f"⚠️ Erro silencioso na busca ERP (Transportadora): {e}")

            # 3. Monta as condições dinâmicas
            condicoes_or = [
                "UPPER(a.placa) LIKE %s",
                "UPPER(COALESCE(r.motorista, '')) LIKE %s",
                "to_char(a.data, 'DD/MM/YYYY') LIKE %s",
                "UPPER(a.pre_ordem1) LIKE %s" 
            ]
            params_query.extend([termo_like] * 4) # Tirei r.transportadora daqui!

            # Injeta as Pré-Ordens achadas
            if ids_via_erp:
                in_clause = "('" + "', '".join(ids_via_erp) + "')"
                condicoes_or.append(f"(a.pre_ordem1 IN {in_clause} OR a.pre_ordem2 IN {in_clause} OR a.pre_ordem3 IN {in_clause} OR a.pre_ordem4 IN {in_clause} OR a.pre_ordem5 IN {in_clause})")
            
            # 🔥 Injeta as Placas achadas pela pesquisa de Transportadora
            if placas_via_transp:
                in_placas = "('" + "', '".join(placas_via_transp) + "')"
                condicoes_or.append(f"REGEXP_REPLACE(UPPER(a.placa), '[^A-Z0-9]', '', 'g') IN {in_placas}")
            
            where_parts.append(f"AND ({' OR '.join(condicoes_or)})")

        where_final = "WHERE " + " ".join(where_parts)

        # Contagem Paginada
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
                
                CONCAT_WS(', ', 
                    NULLIF(a.pre_ordem1,''), NULLIF(a.pre_ordem2,''), NULLIF(a.pre_ordem3,''),
                    NULLIF(a.pre_ordem4,''), NULLIF(a.pre_ordem5,'')
                ),
                
                r.transportadora, -- Vamos resolver no Python se for Nulo

                r.status,
                r.caminhao_liberado, r.motorista, r.vistoriador,
                CASE WHEN r.pdf_documento IS NOT NULL THEN r.id ELSE NULL END,
                CAST(EXTRACT(EPOCH FROM (a.hr_fim - a.hr_inicio))/60 AS INTEGER),
                a.local, a.pre_ordem1, a.pre_ordem2, a.pre_ordem3, a.pre_ordem4, a.pre_ordem5,

                a.data,
                a.hr_inicio,
                COALESCE(a.status_patio, 'PENDENTE'),
                COALESCE(a.criado_por, 'Desconhecido')

            FROM "vistoria"."VAGENDAMENTO" a
            LEFT JOIN "vistoria"."VRESPOSTAS" r ON CAST(r.id_agend AS VARCHAR) = CAST(a.id AS VARCHAR)
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

        # 🔥 CORREÇÃO 3: Pre-Cache do ERP (1 Consulta em vez de 40 no loop)
        placas_na_pagina = set()
        datas_na_pagina = set()
        todas_pos = set()
        
        for r in rows:
            if r[1]: placas_na_pagina.add(r[1].upper().replace("-", "").strip())
            if r[19]: datas_na_pagina.add(r[19].strftime('%d/%m/%Y'))
            pos_str = r[5] 
            if pos_str:
                for p in pos_str.replace('/',',').split(','):
                    if p.strip().isdigit():
                        todas_pos.add(p.strip())

        transp_cache = {}
        patio_cache = {}
        saida_cache = {}
        vtranstemp_cache = {}

        # IDs sem placa → busca transportadora em VTRANSTEMP (1 query)
        ids_sem_placa = [r[0] for r in rows if not r[1]]
        if ids_sem_placa:
            cur.execute("""
                SELECT "ID_AGEND", "TRANSPORTADORA"
                FROM "vistoria"."VTRANSTEMP"
                WHERE "ID_AGEND" IN %s
            """, (tuple(ids_sem_placa),))
            for id_ag, transp_temp in cur.fetchall():
                vtranstemp_cache[id_ag] = transp_temp

        if placas_na_pagina:
            # Puxa transportadoras em bloco
            cur.execute("""
                SELECT REGEXP_REPLACE(UPPER(x."PLA_PLACA"), '[^A-Z0-9]', '', 'g'), y."TRP_NOME"
                FROM "UTRAPLACA" x JOIN "UTRAPROPR" y ON x."PLA_PROPR" = y."TRP_CODIGO"
                WHERE REGEXP_REPLACE(UPPER(x."PLA_PLACA"), '[^A-Z0-9]', '', 'g') IN %s
            """, (tuple(placas_na_pagina),))
            for p, t in cur.fetchall():
                transp_cache[p] = t

        if placas_na_pagina and datas_na_pagina:
            # Puxa Doca em Bloco
            cur.execute("""
                SELECT a."PP_PLACA", a."PP_DATA_E", a."PP_HORA" FROM "APLACPEN" a
                LEFT JOIN "AOPERACAO" b ON a."PP_OPERACAO" = b."OPER_CODIGO" AND a."PP_EMPRESA" = b."OPER_EMPRESA"
                WHERE a."PP_PLACA" IN %s AND a."PP_DATA_E" IN %s AND b."OPER_DESCRICAO" = 'CARREGAMENTO'
            """, (tuple(placas_na_pagina), tuple(datas_na_pagina)))
            for rp_placa, rp_data, rp_hora in cur.fetchall():
                key = f"{rp_placa}_{rp_data}"
                if key not in patio_cache: patio_cache[key] = []
                patio_cache[key].append(rp_hora)
            
            # Puxa Saída em Bloco
            cur.execute("""
                SELECT 
                    b."MV_PLACA1", 
                    to_char(a."MV_DT_ENT_SAI", 'DD/MM/YYYY'), -- Formatação forçada!
                    a."MV_DTH_LANC"::TIME 
                FROM "AMOVPRI" a
                LEFT JOIN "AMOVTRA" b on b."MV_EMPRESA" = a."MV_EMPRESA" and b."MV_LOCAL" = a."MV_LOCAL" and b."MV_NOTA" = a."MV_NOTA"
                LEFT JOIN "AMOVITE" c on c."MV_EMPRESA" = a."MV_EMPRESA" and c."MV_LOCAL" = a."MV_LOCAL" and c."MV_NOTA" = a."MV_NOTA"
                LEFT JOIN "AOPERACAO" d ON c."MV_OPERACAO" = d."OPER_CODIGO" AND c."MV_EMPRESA" = d."OPER_EMPRESA"
                
                WHERE b."MV_PLACA1" IN %s
                  AND to_char(a."MV_DT_ENT_SAI", 'DD/MM/YYYY') IN %s
                  -- ⚠️ AVISO SÊNIOR: Se o seu número for uma Nota e não um Romaneio, 
                  -- você precisa alterar o 'ROM' abaixo ou permitir outras séries.
                  AND a."MV_SERIE" = 'ROM' 
                  AND d."OPER_DESCRICAO" = 'CARREGAMENTO'
            """, (tuple(placas_na_pagina), tuple(datas_na_pagina)))
            for rs_placa, rs_data, rs_hora in cur.fetchall():
                key = f"{rs_placa}_{rs_data}"
                if key not in saida_cache: saida_cache[key] = []
                saida_cache[key].append(rs_hora)

        agora = datetime.now()
        updates_status_pendentes = []
        resultado_temp = []
        
        for r in rows:
            pos_str = r[5] 
            pos_list = [p.strip() for p in pos_str.replace('/',',').split(',')] if pos_str else []

            id_agend = r[0]
            placa_limpa = r[1].upper().replace("-", "").strip() if r[1] else ""
            status_resposta = r[7] 
            data_agend = r[19]
            hr_inicio = r[20]
            status_salvo_banco = r[21] 
            
            # Define a transportadora: Usa a gravada ou o Cache Rápido
            transp = r[6] or transp_cache.get(placa_limpa) or vtranstemp_cache.get(id_agend) or 'Aguardando...'
            
            novo_status = status_salvo_banco
            data_erp = data_agend.strftime('%d/%m/%Y') if data_agend else ""
            cache_key = f"{placa_limpa}_{data_erp}"

            if status_salvo_banco not in ['CARREGADO', 'CANCELADO']:
                if status_resposta == 'Cancelada':
                    novo_status = 'CANCELADO'
                elif status_resposta == 'Concluida':
                    if status_salvo_banco in ['PENDENTE', 'ATRASADO']:
                        novo_status = 'VISTORIADO'
                    
                    if novo_status == 'VISTORIADO':
                        hora_agendamento = hr_inicio if hr_inicio else datetime.min.time()
                        # Consulta o Cache na memória em vez do Banco de Dados!
                        if cache_key in patio_cache:
                            horas_validas = [h for h in patio_cache[cache_key] if h >= hora_agendamento]
                            if horas_validas:
                                novo_status = 'CARREGANDO'

                    if novo_status in ['VISTORIADO', 'CARREGANDO']:
                        # Consulta o Cache de Saída na memória
                        if cache_key in saida_cache:
                            novo_status = 'CARREGADO'
                else:
                    if data_agend and hr_inicio:
                        dt_hr_agendamento = datetime.combine(data_agend, hr_inicio)
                        novo_status = 'ATRASADO' if agora > dt_hr_agendamento else 'PENDENTE'

                # 🔥 CORREÇÃO 4: Guarda os updates para fazer tudo de uma vez
                if novo_status != status_salvo_banco:
                    updates_status_pendentes.append((novo_status, id_agend))

            resultado_temp.append({
                "id": id_agend, "placa": r[1], "data": r[2], "h_inicio": r[3], "h_fim": r[4],
                "pre_ordem": pos_str, "transportadora": transp, 
                "vistoria_realizada": novo_status, 
                "liberado": r[8], "motorista": r[9], "vistoriador": r[10], 
                "pdf": r[11], "tem_pdf": r[11], "pos_ids": pos_list, 
                "duracao": r[12], "local": r[13],
                "pre_ordem1": r[14], "pre_ordem2": r[15], "pre_ordem3": r[16], "pre_ordem4": r[17], "pre_ordem5": r[18],
                "criado_por": r[22]
            })

        # Dispara todos os UPDATES do banco em 1 milissegundo
        if updates_status_pendentes:
            execute_batch(cur, 'UPDATE "vistoria"."VAGENDAMENTO" SET status_patio = %s WHERE id = %s', updates_status_pendentes)
            conn.commit()

        # BUSCA ÚNICA NO ERP (Reaproveitamos a conexão do Pool!)
        info_erp = {}
        if todas_pos:
            try:
                # Não abre uma conexão nova, usa o `cur` existente!
                sql_detalhes = f"""
                    SELECT CAST(a."PED_PRE_ORDEM" AS VARCHAR), a."PED_NUMERO", b."EMB_NUMERO", c."MV_NOTA" 
                    FROM "APEDIDOS" a 
                    LEFT JOIN "AEMBARITE" b ON a."PED_NUMERO" = b."EMB_PEDIDO" AND a."PED_EMPRESA" = b."EMB_EMPRESA" 
                    LEFT JOIN "AMOVPRI" c ON c."MV_PEDIDO" = a."PED_NUMERO" 
                    WHERE a."PED_PRE_ORDEM" IN %s
                """
                cur.execute(sql_detalhes, (tuple(todas_pos),))
                
                for row_erp in cur.fetchall():
                    po, ped, emb, nota = row_erp
                    if po not in info_erp: info_erp[po] = {'ped': set(), 'emb': set(), 'nf': set()}
                    if ped: info_erp[po]['ped'].add(str(ped))
                    if emb: info_erp[po]['emb'].add(str(emb))
                    if nota: info_erp[po]['nf'].add(str(nota))
            except Exception as e:
                print("Erro ERP:", e)

        # MONTAGEM FINAL
        final = []
        for item in resultado_temp:
            peds, embs, nfs = set(), set(), set()
            
            for po in item['pos_ids']:
                if po in info_erp:
                    peds.update(info_erp[po]['ped'])
                    embs.update(info_erp[po]['emb'])
                    nfs.update(info_erp[po]['nf'])
            
            item['pedido'] = " / ".join(peds) if peds else "-"
            item['embarque'] = " / ".join(embs) if embs else "-"
            item['nota'] = " / ".join(nfs) if nfs else "-"
            
            del item['pos_ids']
            final.append(item)

        return jsonify({ "data": final, "meta": { "page": page, "total_pages": total_pages, "total_items": total_items } })

    except Exception as e:
        print("❌ Erro Monitoramento:", e)
        return jsonify({"error": str(e)}), 500
    finally:
        # Tudo limpo de forma correta!
        if cur: cur.close()
        if conn: db_pool.putconn(conn)

# --- ROTA DE DETALHES ---
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
                r.chk_porta_altura, r.chk_abertura_total, r.chk_assoalho_liso, r.chk_peso_container,

                -- [41] Puxando se a carga é derivado (Retorna True ou False)
                a.derivado

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

        # Verifica se é derivado e se o PDF do ERP existe
        is_derivado = bool(row[41])
        tem_pdf_embarque = False
        data_iso = row[2].strftime('%Y-%m-%d') if row[2] else None # Formatamos para YYYY-MM-DD
        
        if not is_derivado and row[1] and row[2]:
            # Placa sem traço para o ERP (Ex: Mercosul ou Antiga)
            placa_limpa = str(row[1]).replace('-', '').upper().strip() 
            try:
                # Verifica sobre a ficha
                cur.execute('SELECT 1 FROM agr."AEMBFICHA" WHERE "FE_PLACA" = %s AND "FE_DATA" = %s AND "FE_PDF" IS NOT NULL LIMIT 1', (placa_limpa, row[2]))
                if cur.fetchone():
                    tem_pdf_embarque = True
            except Exception as e:
                print(f"⚠️ Aviso Silencioso - Erro ao buscar AEMBFICHA: {e}")
                
    

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
                -- 🔥 CORREÇÃO 1: A trava do status 'C' (Cancelado) subiu para o JOIN. 
                -- Assim ele não "mata" as pré-ordens que ainda não tem nota!
                LEFT JOIN "AMOVPRI" c ON c."MV_PEDIDO" = a."PED_NUMERO" AND c."MV_STATUS" != 'C'
                WHERE a."PED_PRE_ORDEM" IN %s
            """, (tuple(lista_pre_ordens),))
            
            temp_dict = {}
            for po, ped, emb, nota in cur.fetchall():
                # 🔥 CORREÇÃO 2: Se não tem pedido ou embarque ainda, vira um tracinho "-"
                po_str = str(po).strip() if po else "-"
                ped_str = str(ped).strip() if ped else "-"
                emb_str = str(emb).strip() if emb else "-"
                
                key = (po_str, ped_str, emb_str)
                if key not in temp_dict: temp_dict[key] = []
                if nota: temp_dict[key].append(str(nota).strip())

            processados_po = set()
            for (po, ped, emb), notas in temp_dict.items():
                processados_po.add(po)
                dados_emitidos.append({
                    "pre_ordem": po, 
                    "pedido": ped, 
                    "embarque": emb, 
                    "notas": " / ".join(notas) if notas else "-"
                })
                
            # 🔥 CORREÇÃO 3: Se a Pré-Ordem existe no agendamento mas AINDA NÃO FOI DIGITADA no ERP (APEDIDOS),
            # forçamos ela a aparecer na tela aguardando os próximos passos!
            for po in lista_pre_ordens:
                if po not in processados_po:
                    dados_emitidos.append({
                        "pre_ordem": po, 
                        "pedido": "-", 
                        "embarque": "-", 
                        "notas": "-"
                    })

            # 2. Busca Produtos e Paletes (Agrupados)
            cur.execute("""
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
            """, (tuple(lista_pre_ordens),))
            
            for prd_nome, qtd, unid, palete in cur.fetchall():
                unid_fmt = "FD" if str(unid).strip().upper() == 'FD' else str(unid).strip()
                # 🔥 A MÁGICA AQUI: O palete agora é concatenado direto no texto final!
                produtos_reais.append(f"{prd_nome.strip()} - {int(qtd)} {unid_fmt} ({palete})")

        # Se não achou produto no ERP, tenta usar o manual da vistoria (row[18])
        produto_final = " / ".join(produtos_reais) if produtos_reais else (row[18] or "-")
        dados_emitidos.sort(key=lambda x: x['pre_ordem'])

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
            "placas_extras": " / ".join(filter(None, [row[35], row[36]])),
            "is_derivado": is_derivado,
            "tem_pdf_embarque": tem_pdf_embarque,
            "data_iso": data_iso
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
        local = request.args.get('local') # <--- NOVO PARÂMETRO

        # Se faltar dados básicos, deixa passar (o frontend já valida antes)
        if not all([placa, data, ordem, local]):
            return jsonify({"duplicado": False})

        # Conecta no DB_BUSCA
        conn = psycopg2.connect(**DB_BUSCA)
        cur = conn.cursor()

        # Verifica duplicidade considerando PLACA + DATA + ORDEM + LOCAL
        sql = """
            SELECT 1 
            FROM "vistoria"."VAGENDAMENTO" a
            WHERE a.placa = %s 
            AND a.data = %s 
            AND a.pre_ordem1 = %s
            AND a.local = %s  -- <--- NOVA VALIDAÇÃO
            AND NOT EXISTS (
                SELECT 1 FROM "vistoria"."VRESPOSTAS" r 
                WHERE CAST(r.id_agend AS VARCHAR) = CAST(a.id AS VARCHAR) 
                AND r.status = 'Cancelada'
            )
            LIMIT 1
        """
        
        cur.execute(sql, (placa, data, ordem, local))
        existe = cur.fetchone()

        return jsonify({"duplicado": bool(existe)})

    except Exception as e:
        print(f"❌ Erro verificação duplicidade: {e}")
        return jsonify({"duplicado": False}), 200 
    finally:
        if conn: conn.close()

@app.route('/dashboard-carga', methods=['GET'])
def dashboard_carga():
    conn = None
    cur = None
    cur_erp = None # Adicionamos aqui para fechar no finally
    try:
        data_filtro = request.args.get('data', datetime.now().strftime('%Y-%m-%d'))
        local_filtro = request.args.get('local', 'Qualquer').strip()
        derivado_filtro = request.args.get('derivado', 'Todas').strip()
        
        conn = db_pool.getconn()
        cur = conn.cursor()
        cur_erp = conn.cursor()

        where_parts = [
            "a.data = %s", 
            "a.status_patio != 'CANCELADO'",
            """
            (TRIM(COALESCE(a.pre_ordem1, '')) != '' OR 
             TRIM(COALESCE(a.pre_ordem2, '')) != '' OR 
             TRIM(COALESCE(a.pre_ordem3, '')) != '' OR 
             TRIM(COALESCE(a.pre_ordem4, '')) != '' OR 
             TRIM(COALESCE(a.pre_ordem5, '')) != '')
            """
        ]
        params_query = [data_filtro]

        if local_filtro and local_filtro != 'Qualquer':
            where_parts.append("""
                (
                  (r.status = 'Concluida' AND UPPER(TRIM(COALESCE(NULLIF(r.local_filial, ''), a.local))) = UPPER(TRIM(%s)))
                  OR
                  ((r.status IS NULL OR r.status != 'Concluida') AND UPPER(TRIM(a.local)) = UPPER(TRIM(%s)))
                )
            """)
            params_query.extend([local_filtro, local_filtro])

        if derivado_filtro == 'Sim':
            where_parts.append("a.derivado = TRUE")
        elif derivado_filtro == 'Nao':
            where_parts.append("(a.derivado = FALSE OR a.derivado IS NULL)")

        where_clause = " AND ".join(where_parts)

        sql_agendamentos = f"""
            SELECT
                a.id, a.placa, a.hr_inicio,
                r.transportadora,
                a.pre_ordem1, a.pre_ordem2, a.pre_ordem3, a.pre_ordem4, a.pre_ordem5,
                r.status, COALESCE(a.status_patio, 'PENDENTE'), a.data,
                r.vistoria_fim,
                a.hr_fim, a.local,
                COALESCE(a.ficha_impressa, FALSE) as ficha_impressa,
                t."TRANSPORTADORA" as transp_agend
            FROM "vistoria"."VAGENDAMENTO" a
            LEFT JOIN "vistoria"."VRESPOSTAS" r ON CAST(r.id_agend AS VARCHAR) = CAST(a.id AS VARCHAR)
            LEFT JOIN "vistoria"."VTRANSTEMP" t ON t."ID_AGEND" = a.id
            WHERE {where_clause}
            ORDER BY a.hr_inicio ASC
        """
        cur.execute(sql_agendamentos, tuple(params_query))
        agendamentos_do_dia = cur.fetchall()

        # Listas para os Caches
        placas_hoje_limpas = [r[1].upper().replace("-", "").strip() for r in agendamentos_do_dia if r[1]]
        todas_pos_iniciais = set()
        for row in agendamentos_do_dia:
            for p in row[4:9]: 
                if p and str(p).strip(): todas_pos_iniciais.add(str(p).strip())

        patio_cache = {}
        saida_cache = {}
        mapa_embarques = {}
        transp_cache = {} # Novo cache

        if placas_hoje_limpas:
            data_erp = datetime.strptime(data_filtro, '%Y-%m-%d').strftime('%d/%m/%Y')
            placas_tuple = tuple(placas_hoje_limpas)
            
            # 🔥 CORREÇÃO 1.1: Busca das transportadoras feita APENAS UMA VEZ
            cur_erp.execute("""
                SELECT REGEXP_REPLACE(UPPER(x."PLA_PLACA"), '[^A-Z0-9]', '', 'g'), y."TRP_NOME"
                FROM "UTRAPLACA" x
                JOIN "UTRAPROPR" y ON x."PLA_PROPR" = y."TRP_CODIGO"
                WHERE REGEXP_REPLACE(UPPER(x."PLA_PLACA"), '[^A-Z0-9]', '', 'g') IN %s
            """, (placas_tuple,))
            for r_transp in cur_erp.fetchall():
                transp_cache[r_transp[0]] = r_transp[1]

            # CACHE 1: Quem bateu na Doca hoje?
            cur_erp.execute("""
                SELECT a."PP_PLACA", a."PP_HORA" 
                FROM "APLACPEN" a
                LEFT JOIN "AOPERACAO" b ON a."PP_OPERACAO" = b."OPER_CODIGO" AND a."PP_EMPRESA" = b."OPER_EMPRESA"
                WHERE a."PP_DATA_E" = %s AND b."OPER_DESCRICAO" = 'CARREGAMENTO' AND a."PP_PLACA" IN %s
            """, (data_erp, placas_tuple))
            for row_erp in cur_erp.fetchall(): 
                p_erp, h_erp = row_erp[0], row_erp[1]
                if p_erp not in patio_cache: patio_cache[p_erp] = []
                patio_cache[p_erp].append(h_erp)
            
            # CACHE 2: Quem emitiu Nota Fiscal de Saída hoje?
            cur_erp.execute("""
                SELECT b."MV_PLACA1", a."MV_DTH_LANC"::TIME
                FROM "AMOVPRI" a
                LEFT JOIN "AMOVTRA" b on b."MV_EMPRESA" = a."MV_EMPRESA" and b."MV_LOCAL" = a."MV_LOCAL" and b."MV_NOTA" = a."MV_NOTA"
                LEFT JOIN "AMOVITE" c on c."MV_EMPRESA" = a."MV_EMPRESA" and c."MV_LOCAL" = a."MV_LOCAL" and c."MV_NOTA" = a."MV_NOTA"
                LEFT JOIN "AOPERACAO" d ON c."MV_OPERACAO" = d."OPER_CODIGO" AND c."MV_EMPRESA" = d."OPER_EMPRESA"
                WHERE a."MV_DT_ENT_SAI" = %s AND a."MV_SERIE" = 'ROM' AND d."OPER_DESCRICAO" = 'CARREGAMENTO'
                AND b."MV_PLACA1" IN %s
            """, (data_erp, placas_tuple))
            for row_erp in cur_erp.fetchall():
                p_erp, h_saida = row_erp[0], row_erp[1]
                if p_erp not in saida_cache: saida_cache[p_erp] = []
                saida_cache[p_erp].append(h_saida)

        if todas_pos_iniciais:
            cur_erp.execute("""
                SELECT CAST(a."PED_PRE_ORDEM" AS VARCHAR), b."EMB_NUMERO"
                FROM "APEDIDOS" a
                JOIN "AEMBARITE" b ON a."PED_NUMERO" = b."EMB_PEDIDO" AND a."PED_EMPRESA" = b."EMB_EMPRESA"
                WHERE a."PED_PRE_ORDEM" IN %s AND b."EMB_NUMERO" IS NOT NULL
            """, (tuple(todas_pos_iniciais),))
            for po, emb in cur_erp.fetchall():
                if po not in mapa_embarques: mapa_embarques[po] = set()
                mapa_embarques[po].add(str(emb))

        todas_pre_ordens = set()
        fila_caminhoes = []
        caminhoes_concluidos = 0
        caminhoes_liberados = 0
        agendados_hoje = len(agendamentos_do_dia)
        agora = datetime.now()
        
        # 🔥 CORREÇÃO 2: Variável para acumular os updates
        updates_status_pendentes = []

        for row in agendamentos_do_dia:
            id_agend, placa, hr_inicio, transp_banco, p1, p2, p3, p4, p5, status_resp, status_patio, data_agend, vistoria_fim = row[:13]
            hr_fim, local_agend, ficha_impressa = row[13], row[14], row[15]
            transp_agend = row[16] if len(row) > 16 else None

            placa_limpa = placa.upper().replace("-", "").strip() if placa else ""

            # Prioridade: transportadora da vistoria > cache ERP pela placa > transportadora salva no agendamento
            transp = transp_banco or transp_cache.get(placa_limpa) or transp_agend or 'NÃO IDENTIFICADA'
            
            novo_status = status_patio
            hora_exibicao = str(hr_inicio)[:5] if hr_inicio else "--:--"
            texto_hora = "Agendado:"

            if status_patio not in ['CARREGADO', 'CANCELADO']:
                if status_resp == 'Cancelada':
                    novo_status = 'CANCELADO'
                elif status_resp == 'Concluida':
                    if status_patio in ['PENDENTE', 'ATRASADO']:
                        novo_status = 'VISTORIADO'
                    
                    if novo_status in ['VISTORIADO', 'CARREGANDO']:
                        if vistoria_fim:
                            hora_exibicao = vistoria_fim.strftime('%H:%M')
                            texto_hora = "Vistoriado:"

                        limite_doca = vistoria_fim.time() if vistoria_fim else hr_inicio
                        if placa_limpa in patio_cache and limite_doca:
                            horas_validas = [h for h in patio_cache[placa_limpa] if h >= limite_doca]
                            if horas_validas:
                                novo_status = 'CARREGANDO'
                                hora_exibicao = str(min(horas_validas))[:5] 
                                texto_hora = "Na Doca:"

                    if novo_status in ['VISTORIADO', 'CARREGANDO']:
                        limite_saida = vistoria_fim.time() if vistoria_fim else hr_inicio
                        if placa_limpa in saida_cache and limite_saida:
                            saidas_validas = [h for h in saida_cache[placa_limpa] if h >= limite_saida]
                            if saidas_validas:
                                novo_status = 'CARREGADO'
                else:
                    if data_agend and hr_inicio:
                        dt_hr = datetime.combine(data_agend, hr_inicio)
                        novo_status = 'ATRASADO' if agora > dt_hr else 'PENDENTE'
                        if novo_status == 'ATRASADO': texto_hora = "Atrasado:"

                # 🔥 CORREÇÃO 2.1: Acumulamos em vez de fazer Update um a um no disco
                if novo_status != status_patio:
                    updates_status_pendentes.append((novo_status, id_agend))

            if novo_status == 'CARREGADO':
                caminhoes_concluidos += 1
            elif novo_status in ['VISTORIADO', 'CARREGANDO']:
                caminhoes_liberados += 1
            
            if novo_status not in ['CARREGADO', 'CANCELADO']:
                ordens_limpas = [str(p).strip() for p in [p1, p2, p3, p4, p5] if p and str(p).strip()]
                for o in ordens_limpas: todas_pre_ordens.add(o)
                
                embarques_deste_caminhao = set()
                for o in ordens_limpas:
                    if o in mapa_embarques: embarques_deste_caminhao.update(mapa_embarques[o])
                        
                tem_emb = len(embarques_deste_caminhao) > 0 
                
                if tem_emb:
                    texto_documento = "Emb: " + " / ".join(sorted(embarques_deste_caminhao))
                elif ordens_limpas:
                    texto_documento = "P.O: " + " / ".join(ordens_limpas)
                else:
                    texto_documento = "Sem Ordem"
                
                fila_caminhoes.append({
                    "id": id_agend,
                    "placa": placa, 
                    "transportadora": transp, 
                    "hora": hora_exibicao,
                    "texto_hora": texto_hora, 
                    "status": novo_status,
                    "ordens_resumo": texto_documento,
                    "tem_embarque": tem_emb,
                    "data": data_agend.strftime('%d/%m/%Y') if data_agend else "",
                    "h_inicio": str(hr_inicio)[:5] if hr_inicio else "--:--",
                    "h_fim": str(hr_fim)[:5] if hr_fim else "--:--",
                    "local": local_agend or "Matriz",
                    "impresso": ficha_impressa
                })

        # 🔥 CORREÇÃO 2.2: Grava TODOS os status no banco numa viagem só!
        if updates_status_pendentes:
            execute_batch(cur, 'UPDATE "vistoria"."VAGENDAMENTO" SET status_patio = %s WHERE id = %s', updates_status_pendentes)
            conn.commit()

        # 4. BUSCA DOS PRODUTOS MANTIDA (Código não alterado, apenas indentado)
        resumo_produtos = []
        total_fardos = 0

        if todas_pre_ordens:
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
            cur.execute(sql_produtos, (tuple(todas_pre_ordens),))
            for rp in cur.fetchall():
                desc = rp[0].strip() if rp[0] else "PRODUTO SEM NOME"
                qtd = float(rp[1]) if rp[1] is not None else 0
                unidade = str(rp[2]).strip().upper() if rp[2] else ""
                palete = str(rp[3]).strip().upper() 

                if derivado_filtro == 'Sim' or unidade == 'TON':
                    palete = 'A GRANEL' 

                total_fardos += qtd
                
                qtd_paletes = None
                if palete in ['PBR', 'CHEP', 'CHEPC']:
                    divisor = None
                    desc_upper = desc.upper()
                    
                    if "6X5" in desc_upper: divisor = 36
                    elif "10X1" in desc_upper: divisor = 100
                    elif "5X2" in desc_upper: divisor = 104
                        
                    if divisor and (qtd % divisor == 0):
                        qtd_paletes = int(qtd / divisor)

                resumo_produtos.append({
                    "nome": desc,
                    "quantidade": int(qtd) if qtd % 1 == 0 else round(qtd, 2),
                    "qtd_paletes": qtd_paletes, 
                    "unidade": unidade, 
                    "palete": palete
                })

        def peso_fila(x):
            st = x['status']
            emb = x['tem_embarque']
            
            if st == 'CARREGANDO': return 1                 
            if st == 'VISTORIADO' and emb: return 2         
            if st == 'VISTORIADO' and not emb: return 3     
            if st == 'ATRASADO': return 4                   
            if st == 'PENDENTE': return 5                   
            return 6
            
        fila_caminhoes.sort(key=lambda x: (peso_fila(x), x['hora']))

        return jsonify({
            "stats": {
                "agendadosHoje": agendados_hoje,
                "caminhoesLiberados": caminhoes_liberados,
                "cargasConcluidas": caminhoes_concluidos,
                "totalFardos": int(total_fardos),
                "totalMix": len(resumo_produtos) 
            },
            "resumoProdutos": resumo_produtos,
            "filaCaminhoes": fila_caminhoes
        }), 200

    except Exception as e:
        print(f"❌ Erro no Dashboard de Carga: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if cur: cur.close()
        if cur_erp: cur_erp.close() # 🔥 Importante fechar o segundo cursor também
        if conn: db_pool.putconn(conn)


@app.route('/pdf-embarque', methods=['GET'])
def get_pdf_embarque_erp():
    # 1. Pegamos apenas a placa e a data
    placa = request.args.get('placa', '').replace('-', '').upper().strip()
    data = request.args.get('data', '') 
    
    conn = None
    try:
        conn = psycopg2.connect(**DB_BUSCA)
        cur = conn.cursor()
        
        cur.execute('SELECT "FE_PDF" FROM agr."AEMBFICHA" WHERE "FE_PLACA" = %s AND "FE_DATA" = %s', (placa, data))
        rows = cur.fetchall()
        
        if not rows:
            return jsonify({"error": "PDFs da Ordem de Embarque não encontrados"}), 404

        # 2. Se tiver apenas 1 PDF, extrai os bytes, senão usa o Grampeador (PdfWriter)
        if len(rows) == 1 and rows[0][0]:
            pdf_bytes = bytes(rows[0][0])
        else:
            writer = PdfWriter() 
            for row in rows:
                if row[0]: 
                    pdf_io = io.BytesIO(row[0]) 
                    writer.append(pdf_io)       

            output_pdf = io.BytesIO()
            writer.write(output_pdf) 
            writer.close()           
            pdf_bytes = output_pdf.getvalue()

        # 3. DEVOLVE O PDF PARA A TELA (Navegador do PC ou Celular resolve o resto!)
        response = make_response(pdf_bytes)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'inline; filename=Embarques_{placa}.pdf'
        return response

    except Exception as e:
        print(f"❌ Erro ao baixar PDFs Embarque (ERP): {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if conn: conn.close()

# ==============================================================
# 🖨️ ROTA 1: Lista as impressoras instaladas no Linux (CUPS)
# ==============================================================
@app.route('/impressoras', methods=['GET'])
def listar_impressoras():
    print("📞 [API] O Angular acabou de pedir a lista de impressoras!")
    try:
        # 🔥 CORREÇÃO: Caminho absoluto /usr/bin/lpstat
        resultado = subprocess.run(['/usr/bin/lpstat', '-e'], stdout=subprocess.PIPE, text=True)
        impressoras = [imp.strip() for imp in resultado.stdout.strip().split('\n') if imp.strip()]
        
        # 🔥 A BALA RASTREADORA: Forçamos uma impressora inventada na lista!
        impressoras.append("🖨️ Impressora_Teste_Conexao")
        
        print(f"✅ [API] Devolvendo para o Angular: {impressoras}")
        return jsonify(impressoras), 200
    except Exception as e:
        print(f"❌ [API] Erro interno ao rodar lpstat: {e}")
        return jsonify(["Erro_No_Linux"]), 200

# ==============================================================
# 🚀 ROTA 2: Recebe a ordem do Angular e manda imprimir no Linux
# ==============================================================
@app.route('/imprimir-direto', methods=['POST'])
def imprimir_direto():
    dados = request.json
    id_agend = dados.get('id')
    placa = dados.get('placa', '').replace('-', '').upper().strip()
    data = dados.get('data', '')
    impressora = dados.get('impressora', '')

    if not placa or not data or not impressora:
        return jsonify({"error": "Faltam dados (placa, data ou impressora)"}), 400

    conn = None
    try:
        conn = psycopg2.connect(**DB_BUSCA)
        cur = conn.cursor()
        
        # 1. Pega o PDF do ERP
        cur.execute('SELECT "FE_PDF" FROM agr."AEMBFICHA" WHERE "FE_PLACA" = %s AND "FE_DATA" = %s', (placa, data))
        rows = cur.fetchall()

        if not rows:
            return jsonify({"error": "Ficha não encontrada no ERP"}), 404

        # 2. Usa a nossa velha e confiável "Tesoura Digital" (A4 Perfeito)
        
        writer = PdfWriter()
        A4_W, A4_H = 595.28, 841.89

        for row in rows:
            if row[0]:
                reader = PdfReader(io.BytesIO(row[0]))
                for page in reader.pages:
                    orig_w = float(page.mediabox.width)
                    orig_h = float(page.mediabox.height)
                    scale = min(A4_W / orig_w, A4_H / orig_h)
                    page.scale_by(scale)
                    page.mediabox.lower_left = (0, 0)
                    page.mediabox.upper_right = (A4_W, A4_H)
                    page.cropbox.lower_left = (0, 0)
                    page.cropbox.upper_right = (A4_W, A4_H)
                    writer.add_page(page)

        # 3. Cria um Arquivo Temporário no Linux para a impressora poder ler
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            writer.write(tmp)
            caminho_pdf = tmp.name

        # 4. Manda o comando de impressão (Agora com /usr/bin/lp)
        subprocess.run(['/usr/bin/lp', '-d', impressora, caminho_pdf], check=True)

        # 5. Apaga o arquivo temporário para não lotar o servidor
        os.remove(caminho_pdf)

        # 6. Trava no banco que a ficha foi para a impressora
        sql_update = 'UPDATE "vistoria"."VAGENDAMENTO" SET ficha_impressa = TRUE WHERE id = %s'
        
        # 👇 CORREÇÃO: Passamos apenas o id_agend para preencher o %s
        cur.execute(sql_update, (id_agend,)) 
        conn.commit()

        return jsonify({"message": "✅ Ficha enviada para a impressora com sucesso!"}), 200

    except Exception as e:
        print(f"❌ Erro na impressão direta: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if conn: conn.close()

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5002, debug=True, use_reloader=False)