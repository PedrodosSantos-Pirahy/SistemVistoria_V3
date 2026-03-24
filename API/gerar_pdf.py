import bcrypt
import psycopg2


DB_CONFIG = {
    "host": "192.168.10.10",
    "database": "PgPirahyHML",
    "user": "PEDROK",
    "password": "0912",
    "port": "5432"  
}

def criar_usuario(secao, descricao):
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()

        sql = """
            INSERT INTO qualidade."controle-secao" 
            (secao, criado_em, descricao, ativo)
            VALUES (%s, NOW(), %s, true)
        """

        cur.execute(sql, (secao, descricao))
        
        conn.commit()
        print("✅ Seção criada com sucesso no banco!")

    except Exception as e:
        print("❌ Erro ao criar seção:", e)
        if conn:
            conn.rollback() 
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    criar_usuario(
        secao="Beneficiamento Arroz Branco",
        descricao=""
    )
    
