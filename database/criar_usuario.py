import sqlite3
from werkzeug.security import generate_password_hash
from datetime import datetime

# ===== CONFIGURAÇÃO =====
NOME = "Luiz Silva Andrade"
EMAIL = "luiz@gmail.com"
SENHA = "123"
SALDO_INICIAL = 4325.62
TIPO_CONTA = "corrente"

DB_PATH = "banco.sqlite"

# =======================

def main():
    db = sqlite3.connect(DB_PATH)
    cursor = db.cursor()

    # 1️⃣ Cria usuário
    senha_hash = generate_password_hash(SENHA)

    cursor.execute("""
        INSERT INTO usuarios (nome, email, senha, data_cadastro)
        VALUES (?, ?, ?, ?)
    """, (
        NOME,
        EMAIL,
        senha_hash,
        datetime.now()
    ))

    id_usuario = cursor.lastrowid

    # 2️⃣ Cria conta com saldo inicial
    cursor.execute("""
        INSERT INTO contas (idUsuario, tipo, saldoInicial, dataCriacao)
        VALUES (?, ?, ?, ?)
    """, (
        id_usuario,
        TIPO_CONTA,
        SALDO_INICIAL,
        datetime.now()
    ))

    db.commit()
    db.close()

    print("✅ Usuário criado com sucesso!")
    print(f"👤 Nome: {NOME}")
    print(f"📧 Email: {EMAIL}")
    print(f"💰 Saldo inicial: R$ {SALDO_INICIAL:,.2f}")

if __name__ == "__main__":
    main()