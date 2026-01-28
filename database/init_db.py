import sqlite3

# Cria / abre o banco
conn = sqlite3.connect("banco.sqlite")

# Ativa chaves estrangeiras (ESSENCIAL no SQLite)
conn.execute("PRAGMA foreign_keys = ON;")

cursor = conn.cursor()

sql = """
CREATE TABLE IF NOT EXISTS usuarios (
    idUsuario INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    senha TEXT NOT NULL,
    data_cadastro DATETIME NOT NULL
);

CREATE TABLE IF NOT EXISTS grupos (
    idGrupo INTEGER NOT NULL UNIQUE,
    nome TEXT NOT NULL,
    descricao TEXT NOT NULL,
    PRIMARY KEY(idGrupo)
);

CREATE TABLE IF NOT EXISTS contas (
    idConta INTEGER PRIMARY KEY AUTOINCREMENT,
    idUsuario INTEGER NOT NULL,
    idGrupo INTEGER,
    tipo TEXT NOT NULL,
    saldoInicial REAL NOT NULL,
    dataCriacao DATETIME NOT NULL,
    FOREIGN KEY (idUsuario) REFERENCES usuarios(idUsuario),
    FOREIGN KEY (idGrupo) REFERENCES grupos(idGrupo)
);

CREATE TABLE IF NOT EXISTS cartoesCredito (
    idCartao INTEGER PRIMARY KEY AUTOINCREMENT,
    idUsuario INTEGER NOT NULL,
    nome TEXT NOT NULL,
    limite REAL NOT NULL,
    bandeira TEXT NOT NULL,
    numero_cartao TEXT NOT NULL,
    cvv TEXT NOT NULL,
    validadeMes INTEGER NOT NULL,
    validadeAno INTEGER NOT NULL,

    FOREIGN KEY (idUsuario) REFERENCES usuarios(idUsuario)
);

CREATE TABLE IF NOT EXISTS faturas (
    idFatura INTEGER NOT NULL UNIQUE,
    idCartao INTEGER NOT NULL,
    mesReferencia INTEGER NOT NULL,
    anoReferencia INTEGER NOT NULL,
    dataFechamento DATE NOT NULL,
    dataVencimento DATE NOT NULL,
    valorTotal REAL NOT NULL,
    statusPagamento TEXT NOT NULL,
    PRIMARY KEY(idFatura),
    FOREIGN KEY (idCartao) REFERENCES cartoesCredito(idCartao)
);

CREATE TABLE IF NOT EXISTS lancamentos (
    idLancamento INTEGER NOT NULL UNIQUE,
    idConta INTEGER NOT NULL,
    idUsuario INTEGER NOT NULL,
    idGrupo INTEGER NOT NULL,
    idFatura INTEGER NOT NULL,
    valor REAL NOT NULL,
    tipo TEXT NOT NULL,
    descricao TEXT,
    dataLancamento DATETIME NOT NULL,
    PRIMARY KEY(idLancamento),
    FOREIGN KEY (idUsuario) REFERENCES usuarios(idUsuario),
    FOREIGN KEY (idConta) REFERENCES contas(idConta),
    FOREIGN KEY (idGrupo) REFERENCES grupos(idGrupo),
    FOREIGN KEY (idFatura) REFERENCES faturas(idFatura)
);

CREATE TABLE IF NOT EXISTS transferencias (
    idTransferencia INTEGER PRIMARY KEY AUTOINCREMENT,
    idContaOrigem INTEGER NOT NULL,
    idContaDestino INTEGER NOT NULL,
    valor REAL NOT NULL,
    dataTransferencia DATETIME NOT NULL,

    idLancamentoOrigem INTEGER,
    idLancamentoDestino INTEGER,

    FOREIGN KEY (idContaOrigem) REFERENCES contas(idConta),
    FOREIGN KEY (idContaDestino) REFERENCES contas(idConta),
    FOREIGN KEY (idLancamentoOrigem) REFERENCES lancamentos(idLancamento),
    FOREIGN KEY (idLancamentoDestino) REFERENCES lancamentos(idLancamento)
);
"""

cursor.executescript(sql)

conn.commit()
conn.close()

print("✅ Banco de dados criado com sucesso!")