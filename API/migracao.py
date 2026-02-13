import gspread
# REMOVA OU COMENTE ESSA LINHA:
# from oauth2client.service_account import ServiceAccountCredentials 

import pandas as pd
import psycopg2
import re
import sys
import os# <--- NÃO ESQUEÇA DISSO

# Pega o diretório onde este arquivo .py está (pasta API)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Junta com o nome do arquivo (agora ele acha mesmo rodando da raiz)
ARQUIVO_JSON_GOOGLE = os.path.join(BASE_DIR, "service-account.json")

ID_PLANILHA = "1OypeFbnDkBMWNYSqH36DJYtR8l4lapWwG9j44fdzTXw"
NOME_ABA = "Agend_V2"

# ... resto do código ...

# 🗄️ CONFIGURAÇÃO DO BANCO (Preencha aqui se não estiver preenchido)
DB_BUSCA = {
    "host": "192.168.10.10",
    "database": "PgPirahyHML",
    "user": "PEDROK",
    "password": "0912",
    "port": "5432"  
}

def limpar_pre_ordens(texto):
    if pd.isna(texto) or str(texto).strip() == '':
        return [None] * 5
    texto = str(texto).strip()
    partes = re.split(r'[ ,-]+', texto)
    ordens = [p.strip() for p in partes if p.strip()]
    while len(ordens) < 5:
        ordens.append(None)
    return ordens[:5]

def formatar_data(valor):
    if not valor: return None
    try:
        return pd.to_datetime(valor, dayfirst=True).strftime("%Y-%m-%d")
    except:
        return None

def formatar_hora(valor):
    if not valor: return None
    try:
        return str(valor).strip()[:5]
    except:
        return None

def migrar_do_sheets():
    print("🚀 INICIANDO MIGRAÇÃO DO GOOGLE SHEETS...", flush=True)
    
    conn = None
    try:
        print("☁️ Conectando ao Google Sheets...", flush=True)
        
        # --- 🔥 ALTERAÇÃO AQUI: JEITO NOVO E MAIS SEGURO ---
        # O gspread agora já sabe ler o service_account direto
        gc = gspread.service_account(filename=ARQUIVO_JSON_GOOGLE)
        
        # Abre a planilha
        sheet = gc.open_by_key(ID_PLANILHA).worksheet(NOME_ABA)
        
        # ... (O resto do código continua IDÊNTICO) ...
        print("📥 Baixando todos os dados (pode demorar um pouco)...")
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        
        
        print("📥 Baixando dados (aguarde)...", flush=True)
        dados_brutos = sheet.get_all_values()
        
        # Pula cabeçalho (linha 1)
        df = pd.DataFrame(dados_brutos[1:], columns=dados_brutos[0])
        print(f"📊 Total de linhas baixadas: {len(df)}", flush=True)

        conn = psycopg2.connect(**DB_BUSCA)
        cur = conn.cursor()

        sucessos = 0
        erros = 0

        print("💾 Gravando no banco...", flush=True)
        
        for index, row in df.iterrows():
            try:
                # Mapeamento CORRETO das Colunas (0-based)
                # A=0, B=1, C=2, D=3, E=4 (Ordens), F=5 (Transp) ... X=23, Y=24 (ID)
                
                # Se a linha estiver vazia na coluna A, pula
                placa = str(row.iloc[0]).strip().upper()
                if not placa: continue 

                data = formatar_data(row.iloc[1])
                hr_inicio = formatar_hora(row.iloc[2])
                hr_fim = formatar_hora(row.iloc[3])
                raw_ordens = row.iloc[4]
                
                # Coluna X (Local) = Índice 23
                # Coluna Y (ID)    = Índice 24
                # Verifica se a linha tem colunas suficientes antes de acessar
                if len(row) <= 24:
                    print(f"⚠️ Linha {index+2} incompleta (sem coluna Y). Pulando.")
                    erros += 1
                    continue

                local_raw = str(row.iloc[23]).strip().title()
                id_raw = row.iloc[24]

                if not id_raw or not str(id_raw).isdigit():
                    # Se não tiver ID, pula (ou poderia gerar um novo, mas melhor pular)
                    continue
                    
                id_antigo = int(id_raw)
                local_final = 'Filial' if 'Filial' in local_raw else 'Matriz'
                ordens = limpar_pre_ordens(raw_ordens)

                sql = """
                    INSERT INTO "vistoria"."VAGENDAMENTO" 
                    (id, placa, data, hr_inicio, hr_fim, local, 
                     pre_ordem1, pre_ordem2, pre_ordem3, pre_ordem4, pre_ordem5)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO NOTHING;
                """
                
                valores = (
                    id_antigo, placa, data, hr_inicio, hr_fim, local_final,
                    ordens[0], ordens[1], ordens[2], ordens[3], ordens[4]
                )

                cur.execute(sql, valores)
                sucessos += 1
                
                if sucessos % 50 == 0:
                    print(f"   ✅ Processados: {sucessos}...", end='\r')

            except Exception as e_linha:
                print(f"❌ Erro linha {index+2}: {e_linha}")
                erros += 1

        print("\n🔄 Sincronizando contador de IDs...")
        cur.execute("""
            SELECT setval(
                pg_get_serial_sequence('"vistoria"."VAGENDAMENTO"', 'id'), 
                COALESCE(MAX(id), 1)
            ) FROM "vistoria"."VAGENDAMENTO";
        """)
        
        conn.commit()
        print("-" * 40)
        print(f"✅ FINALIZADO! Importados: {sucessos} | Erros: {erros}")

    except Exception as e:
        print("\n❌ ERRO CRÍTICO NO SCRIPT:", e)
        if conn: conn.rollback()
    finally:
        if conn: conn.close()

if __name__ == "__main__":
    migrar_do_sheets()