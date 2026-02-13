import bcrypt
import psycopg2

# ⚠️ SUAS CONFIGURAÇÕES DE BANCO
DB_CONFIG = {
    "host": "192.168.10.10",
    "database": "PgPirahy",
    "user": "PEDROK",
    "password": "0912",
    "port": "5432"  
}

def criar_usuario(nome, usuario, senha_plana, cargo, local, matricula):
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()

        # 1. Gerar o Hash Bcrypt
        salt = bcrypt.gensalt(rounds=12) 
        senha_hash = bcrypt.hashpw(senha_plana.encode('utf-8'), salt).decode('utf-8')

        print("-" * 30)
        print(f"👤 Criando: {nome} ({usuario})")
        print(f"🏢 Local: {local} | 🏷️ Cargo: {cargo}")
        print(f"🔑 Senha Pura: {senha_plana}")
        print("-" * 30)

        # 2. Inserir no Banco (Agora com local e matricula)
        sql = """
            INSERT INTO "vistoria"."VUSUARIO" 
            (nome, usuario, senha_hash, cargo, ativo, local, matricula, criado_em)
            VALUES (%s, %s, %s, %s, true, %s, %s, NOW())
        """
        
        # A ordem aqui tem que ser EXATAMENTE a mesma do VALUES acima
        cur.execute(sql, (nome, usuario, senha_hash, cargo, local, matricula))
        
        conn.commit()
        print("✅ Usuário criado com sucesso no banco!")

    except Exception as e:
        print("❌ Erro ao criar usuário:", e)
        if conn:
            conn.rollback() # Desfaz se der erro
    finally:
        if conn: conn.close()

# ==========================================
# 🚀 ÁREA DE CONFIGURAÇÃO (SÓ MEXA AQUI)
# ==========================================

if __name__ == "__main__":
    
    # --- EXEMPLO 1: Vistoriador da MATRIZ ---
    # criar_usuario(
    #     nome="João Vistoriador Matriz",
    #     usuario="joao.vis",
    #     senha_plana="123456",
    #     cargo="VIS",        # Sigla nova
    #     local="Matriz",     # Opções: 'Matriz' ou 'Filial'
    #     matricula="5728"    # Obrigatória
    # )

    # --- QUER CRIAR OUTRO? COMENTE O DE CIMA E DESCOMENTE UM ABAIXO ---

    # --- EXEMPLO 2: Vistoriador da FILIAL ---
    # criar_usuario(
    #     nome="Maria Vistoriadora Filial",
    #     usuario="maria.vis",
    #     senha_plana="123456",
    #     cargo="VIS",
    #     local="Filial",
    #     matricula="5728"
    # )

    # --- EXEMPLO 3: Expedição da FILIAL ---
    criar_usuario(
        nome="LILIAN TISCOSKI DA SILVA",
        usuario="LILIANT",
        senha_plana="5680",
        cargo="ADM",
        local="",
        matricula="5680"
    )
    
    # --- EXEMPLO 4: ADMIN GERAL ---
    # criar_usuario(
    #     nome="Super Admin",
    #     usuario="admin.master",
    #     senha_plana="admin123",
    #     cargo="ADM",
    #     local="Matriz", 
    #     matricula="5728"
    # )