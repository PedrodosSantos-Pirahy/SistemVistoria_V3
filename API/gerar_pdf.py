import psycopg2
from psycopg2.extras import RealDictCursor
import base64
from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML
from datetime import datetime
import os

# ⚙️ CONFIGURAÇÃO DO BANCO
DB_CONFIG = {
    "host": "192.168.10.10",
    "database": "PgPirahy",
    "user": "PEDROK",
    "password": "0912",
    "port": "5432"  
}

TEMPLATE_HTML = "vistoria_pdf.html"

def formatar_data(dt):
    if not dt: return "-"
    if isinstance(dt, str): return dt
    return dt.strftime("%d/%m/%Y")

def formatar_hora(dt):
    if not dt: return "-"
    if isinstance(dt, str): return dt
    # Se vier como timedelta (comum no postgres para horas), converte string
    return str(dt)[:5] 

def imagem_para_base64(blob):
    if not blob: return None
    try:
        b64 = base64.b64encode(blob).decode('utf-8')
        return f"data:image/png;base64,{b64}"
    except:
        return None

def gerar_pdf_por_id_resposta(id_resposta):
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor(cursor_factory=RealDictCursor)

        print(f"🔍 Buscando Vistoria ID {id_resposta}...")

        sql = """
            SELECT 
                -- Dados do Agendamento (Usamos apenas a DATA base e LOCAL)
                a.placa, a.data, 
                a.pre_ordem1, a.pre_ordem2, a.pre_ordem3,
                a.local as local_agendamento,
                
                -- Dados da Resposta (VRESPOSTAS) - HORÁRIOS REAIS AQUI
                r.id as id_res,
                r.data_chegada,   -- Hora que o caminhão chegou
                r.vistoria_inicio,    -- Hora que começou a vistoria
                r.vistoria_fim,       -- Hora que terminou
                
                r.transportadora, r.status, r.caminhao_liberado, 
                r.vistoriador, r.motorista, r.observacoes,
                r.tipo_veiculo, r.produto, r.ultimos_produtos_transportados,
                
                -- Checklist
                r.chk_limpeza_insetos, r.chk_danos_frestas, r.chk_umidade_mofo,
                r.chk_residuos_carroceria, r.chk_outros_produtos_odores,
                r.chk_bocas_graneleiras, r.chk_lonas_forracao, r.chk_chapas_mdf,
                r.chk_lonas_integras, r.chk_cantoneiras_cintas, r.chk_tampas_vedacao,
                
                -- Específicos
                r.chk_porta_altura, r.chk_abertura_total, r.chk_assoalho_liso, r.chk_peso_container,
                
                -- Placas extras e Assinaturas
                r.placa_2, r.placa_3,
                r.ass_motorista, r.ass_vistoriador

            FROM "vistoria"."VRESPOSTAS" r
            LEFT JOIN "vistoria"."VAGENDAMENTO" a ON CAST(r.id_agend AS VARCHAR) = CAST(a.id AS VARCHAR)
            WHERE r.id = %s
        """
        
        cur.execute(sql, (id_resposta,))
        row = cur.fetchone()

        if not row:
            print("❌ Nenhuma vistoria encontrada com esse ID na tabela VRESPOSTAS.")
            return

        # ------------------------------------------------
        # TRATAMENTO DE DADOS
        # ------------------------------------------------
        
        # Placas
        lista_placas = []
        if row.get('placa'): lista_placas.append(row['placa'])
        if row.get('placa_2'): lista_placas.append(row['placa_2'])
        if row.get('placa_3'): lista_placas.append(row['placa_3'])

        # Ordens
        ordens = [str(x) for x in [row.get('pre_ordem1'), row.get('pre_ordem2'), row.get('pre_ordem3')] if x]
        str_ordem = ", ".join(ordens)

        # 🔥 CORREÇÃO DOS HORÁRIOS AQUI
        # Estamos pegando r.hr_chegada, r.hr_inicio, r.hr_fim
        hora_chegada_real = formatar_hora(row.get('data_chegada'))
        hora_inicio_real = formatar_hora(row.get('vistoria_inicio'))
        hora_fim_real = formatar_hora(row.get('vistoria_fim'))

        contexto = {
            "local_vistoria": row.get('local_agendamento', "Matriz"),
            "data": formatar_data(row['data']),
            
            # 🔥 Usando horário real da tabela de respostas
            "chegada":row['data_chegada'],
            "vistoria":row['vistoria_inicio'],
            "final":row['vistoria_fim'],
            
            "ordem": str_ordem,
            "transportadora": row['transportadora'],
            "placas": lista_placas,
            "operacao": 'Carga',
            "produto": row['produto'],
            "tipo_veiculo": row['tipo_veiculo'],
            "ultimos_produtos": row['ultimos_produtos_transportados'],
            
            # Checklist
            "limpeza": row['chk_limpeza_insetos'],
            "danos": row['chk_danos_frestas'],
            "umidade": row['chk_umidade_mofo'],
            "residuos": row['chk_residuos_carroceria'],
            "odores": row['chk_outros_produtos_odores'],
            "bocas_graneleiras": row['chk_bocas_graneleiras'],
            "lonas": row['chk_lonas_forracao'],
            "chapas_mdf": row['chk_chapas_mdf'],
            "lonas_protecao": row['chk_lonas_integras'],
            "equipamentos": row['chk_cantoneiras_cintas'],
            "tampas_laterais": row['chk_tampas_vedacao'],
            
            # Específicos
            "bau_altura_porta": row['chk_porta_altura'],
            "bau_largura_porta": row['chk_abertura_total'],
            "bau_assoalho": row['chk_assoalho_liso'],
            "container_peso": row['chk_peso_container'],
            
            "observacoes": row['observacoes'] or "Sem observações.",
            "status_final": row['caminhao_liberado'], 
            
            "assinaturas": {
                "motorista": {
                    "nome": row['motorista'],
                    "imagem": imagem_para_base64(row['ass_motorista'])
                },
                "vistoriador": {
                    "nome": row['vistoriador'],
                    "imagem": imagem_para_base64(row['ass_vistoriador'])
                }
            }
        }

        print("📄 Renderizando HTML...")
        env = Environment(loader=FileSystemLoader('.'))
        template = env.get_template(TEMPLATE_HTML)
        html_content = template.render(contexto)

        print("🖨️ Gerando PDF...")
        pdf_bytes = HTML(string=html_content, base_url='.').write_pdf()

        print("💾 Salvando no banco (Coluna pdf_documento)...")
        update_sql = 'UPDATE "vistoria"."VRESPOSTAS" SET pdf_documento = %s WHERE id = %s'
        cur.execute(update_sql, (pdf_bytes, id_resposta))
        conn.commit()

        print(f"✅ SUCESSO! PDF atualizado no ID {id_resposta}.")

    except Exception as e:
        print(f"❌ Erro no SQL ou Processamento: {e}")
        if conn: conn.rollback()
    finally:
        if conn: conn.close()

if __name__ == "__main__":
    gerar_pdf_por_id_resposta(31)