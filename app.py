from flask import Flask, render_template, request, redirect, session, flash
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta, date
import random

app = Flask(__name__)
app.secret_key = "atlasbank_secret"


def get_db():
    return sqlite3.connect("database/banco.sqlite", check_same_thread=False)


def formatar_brl(valor: float) -> str:
    return (
        f"{valor:,.2f}"
        .replace(",", "X")
        .replace(".", ",")
        .replace("X", ".")
    )


def obter_id_conta(cursor, idUsuario: int):
    cursor.execute("""
        SELECT idConta
        FROM contas
        WHERE idUsuario = ?
        LIMIT 1
    """, (idUsuario,))
    row = cursor.fetchone()
    return row[0] if row else None


def calcular_saldo_conta(cursor, idConta: int) -> float:
    cursor.execute("""
        SELECT
            c.saldoInicial
            + IFNULL((
                SELECT SUM(t.valor)
                FROM transferencias t
                WHERE t.idContaDestino = c.idConta
            ), 0)
            - IFNULL((
                SELECT SUM(t.valor)
                FROM transferencias t
                WHERE t.idContaOrigem = c.idConta
            ), 0)
        AS saldo
        FROM contas c
        WHERE c.idConta = ?
        LIMIT 1
    """, (idConta,))
    row = cursor.fetchone()
    return float(row[0]) if row and row[0] is not None else 0.0


def buscar_cartoes_8cols(cursor, idUsuario: int):
    """
    Retorna SEMPRE 8 colunas, na ordem:
    (idCartao, nome, limite, bandeira, validadeMes, validadeAno, numero_cartao, cvv)
    """
    cursor.execute("""
        SELECT
            idCartao,
            nome,
            limite,
            bandeira,
            validadeMes,
            validadeAno,
            numero_cartao,
            cvv
        FROM cartoesCredito
        WHERE idUsuario = ?
        ORDER BY idCartao DESC
    """, (idUsuario,))
    return cursor.fetchall()


def carregar_faturas_e_lancamentos(cursor, idCartao: int):
    faturas = []
    lancamentos = []
    if idCartao:
        cursor.execute("""
            SELECT
                idFatura,
                mesReferencia,
                anoReferencia,
                valorTotal
            FROM faturas
            WHERE idCartao = ?
            ORDER BY anoReferencia DESC, mesReferencia DESC
        """, (idCartao,))
        faturas = cursor.fetchall()

        cursor.execute("""
            SELECT
                l.descricao,
                l.valor,
                l.dataLancamento,
                f.mesReferencia,
                f.anoReferencia
            FROM lancamentos l
            JOIN faturas f ON f.idFatura = l.idFatura
            WHERE f.idCartao = ?
            ORDER BY f.anoReferencia DESC, f.mesReferencia DESC, l.dataLancamento DESC
        """, (idCartao,))
        lancamentos = cursor.fetchall()

    return faturas, lancamentos


def add_months(dt: datetime, months: int) -> datetime:
    """Soma meses mantendo dia válido (ex.: 31 -> ajusta pro último dia do mês)."""
    y = dt.year + (dt.month - 1 + months) // 12
    m = (dt.month - 1 + months) % 12 + 1
    d = min(dt.day, [31,
                     29 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 28,
                     31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1])
    return dt.replace(year=y, month=m, day=d)


def get_or_create_fatura(cursor, idCartao: int, mes_ref: int, ano_ref: int) -> int:
    cursor.execute("""
        SELECT idFatura
        FROM faturas
        WHERE idCartao = ?
          AND mesReferencia = ?
          AND anoReferencia = ?
        LIMIT 1
    """, (idCartao, mes_ref, ano_ref))
    row = cursor.fetchone()
    if row:
        return row[0]

    data_fechamento = datetime(ano_ref, mes_ref, 25)
    if mes_ref == 12:
        data_vencimento = datetime(ano_ref + 1, 1, 10)
    else:
        data_vencimento = datetime(ano_ref, mes_ref + 1, 10)

    cursor.execute("""
        INSERT INTO faturas (
            idCartao,
            mesReferencia,
            anoReferencia,
            dataFechamento,
            dataVencimento,
            valorTotal,
            statusPagamento
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        idCartao,
        mes_ref,
        ano_ref,
        data_fechamento,
        data_vencimento,
        0.0,
        "ABERTA"
    ))
    return cursor.lastrowid


@app.route("/", methods=["GET"])
def login():
    return render_template("login.html")


@app.route("/login", methods=["POST"])
def login_post():
    email = request.form["email"]
    senha = request.form["senha"]

    db = get_db()
    cursor = db.cursor()

    cursor.execute(
        "SELECT idUsuario, nome, senha FROM usuarios WHERE email = ?",
        (email,)
    )
    user = cursor.fetchone()

    if user and check_password_hash(user[2], senha):
        session["idUsuario"] = user[0]
        session["nome"] = user[1]
        return redirect("/dashboard")

    return render_template(
        "login.html",
        erro="Usuário ou senha não encontrados. Tente novamente."
    )


@app.route("/cadastro", methods=["GET"])
def cadastro():
    return render_template("cadastro.html")


@app.route("/cadastro", methods=["POST"])
def cadastro_post():
    nome = request.form["nome"]
    email = request.form["email"]
    senha = request.form["senha"]

    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT idUsuario FROM usuarios WHERE email = ?", (email,))
    if cursor.fetchone():
        return render_template("cadastro.html", erro="Este e-mail já está cadastrado.")

    senha_hash = generate_password_hash(senha)

    cursor.execute("""
        INSERT INTO usuarios (nome, email, senha, data_cadastro)
        VALUES (?, ?, ?, ?)
    """, (nome, email, senha_hash, datetime.now()))
    id_usuario = cursor.lastrowid

    cursor.execute("""
        INSERT INTO contas (idUsuario, tipo, saldoInicial, dataCriacao)
        VALUES (?, ?, ?, ?)
    """, (id_usuario, "corrente", 0.0, datetime.now()))

    db.commit()

    flash("Cadastro aprovado! Faça login para continuar.", "success")
    return redirect("/")


@app.route("/dashboard")
def dashboard():
    if "idUsuario" not in session:
        return redirect("/")

    db = get_db()
    cursor = db.cursor()

    idConta = obter_id_conta(cursor, session["idUsuario"])
    if not idConta:
        return redirect("/")

    saldo = calcular_saldo_conta(cursor, idConta)
    saldo_formatado = formatar_brl(saldo)

    cursor.execute("""
        SELECT
            t.idTransferencia,
            CASE
                WHEN t.idContaOrigem = ? THEN 'Pix enviado'
                ELSE 'Pix recebido'
            END AS descricao,
            CASE
                WHEN t.idContaOrigem = ? THEN 'DEBITO'
                ELSE 'CREDITO'
            END AS tipo,
            t.valor,
            t.dataTransferencia
        FROM transferencias t
        WHERE t.idContaOrigem = ?
           OR t.idContaDestino = ?
        ORDER BY t.dataTransferencia DESC
        LIMIT 5
    """, (idConta, idConta, idConta, idConta))

    extrato = cursor.fetchall()

    return render_template(
        "dashboard.html",
        nome=session["nome"].split()[0],
        saldo=saldo_formatado,
        extrato=extrato
    )


@app.route("/dados-bancarios")
def dados_bancarios():
    if "idUsuario" not in session:
        return redirect("/")

    db = get_db()
    cursor = db.cursor()

    cursor.execute("""
        SELECT 
            u.nome,
            u.email,
            u.data_cadastro,
            g.nome AS grupo
        FROM usuarios u
        LEFT JOIN contas c ON c.idUsuario = u.idUsuario
        LEFT JOIN grupos g ON g.idGrupo = c.idGrupo
        WHERE u.idUsuario = ?
        LIMIT 1
    """, (session["idUsuario"],))

    dados = cursor.fetchone()

    return render_template(
        "dados_bancarios.html",
        nome=dados[0],
        email=dados[1],
        data_cadastro=str(dados[2]).split(".")[0],
        grupo=dados[3] if dados[3] else "Silver"
    )


@app.route("/pix", methods=["GET", "POST"])
def pix():
    if "idUsuario" not in session:
        return redirect("/")

    if request.method == "POST":
        chave = request.form["chave"].strip().lower()

        db = get_db()
        cursor = db.cursor()

        cursor.execute("""
            SELECT idUsuario, email
            FROM usuarios
            WHERE email = ?
        """, (chave,))
        destinatario = cursor.fetchone()

        if not destinatario:
            return render_template("pix.html", erro="Chave Pix não encontrada.")

        if destinatario[0] == session["idUsuario"]:
            return render_template("pix.html", erro="Não é possível enviar Pix para a própria conta.")

        session["pix_chave"] = chave
        return redirect("/pix-confirm")

    return render_template("pix.html")


@app.route("/pix-confirm", methods=["GET"])
def pix_confirm():
    if "idUsuario" not in session or "pix_chave" not in session:
        return redirect("/pix")

    db = get_db()
    cursor = db.cursor()

    cursor.execute("""
        SELECT u.idUsuario, u.nome, u.email
        FROM usuarios u
        WHERE u.email = ?
        LIMIT 1
    """, (session["pix_chave"],))
    row = cursor.fetchone()
    if not row:
        return redirect("/pix")

    destinatario = {"id": row[0], "nome": row[1], "email": row[2]}

    idContaOrigem = obter_id_conta(cursor, session["idUsuario"])
    if not idContaOrigem:
        return redirect("/dashboard")

    saldo_atual = calcular_saldo_conta(cursor, idContaOrigem)
    saldo_formatado = formatar_brl(saldo_atual)

    return render_template(
        "pix_confirm.html",
        destinatario=destinatario,
        saldo=saldo_formatado
    )


@app.route("/pix-send", methods=["POST"])
def pix_send():
    if "idUsuario" not in session or "pix_chave" not in session:
        return redirect("/pix")

    try:
        valor = float(request.form["valor"])
    except:
        valor = 0.0

    db = get_db()
    cursor = db.cursor()

    idContaOrigem = obter_id_conta(cursor, session["idUsuario"])
    if not idContaOrigem:
        return redirect("/dashboard")

    cursor.execute("""
        SELECT u.idUsuario, u.nome, u.email, c.idConta
        FROM usuarios u
        JOIN contas c ON c.idUsuario = u.idUsuario
        WHERE u.email = ?
        LIMIT 1
    """, (session["pix_chave"],))
    row = cursor.fetchone()
    if not row:
        return redirect("/pix")

    destinatario = {"id": row[0], "nome": row[1], "email": row[2]}
    idContaDestino = row[3]

    saldo_atual = calcular_saldo_conta(cursor, idContaOrigem)
    saldo_formatado = formatar_brl(saldo_atual)

    if valor <= 0:
        return render_template("pix_confirm.html", destinatario=destinatario, saldo=saldo_formatado,
                               erro="Informe um valor válido para o Pix.")

    if destinatario["id"] == session["idUsuario"]:
        return render_template("pix_confirm.html", destinatario=destinatario, saldo=saldo_formatado,
                               erro="Você não pode enviar Pix para si mesmo.")

    if saldo_atual < valor:
        return render_template("pix_confirm.html", destinatario=destinatario, saldo=saldo_formatado,
                               erro="Saldo insuficiente para realizar o Pix.")

    agora = datetime.now()

    cursor.execute("""
        INSERT INTO transferencias (
            idContaOrigem,
            idContaDestino,
            valor,
            dataTransferencia,
            idLancamentoOrigem,
            idLancamentoDestino
        )
        VALUES (?, ?, ?, ?, NULL, NULL)
    """, (idContaOrigem, idContaDestino, valor, agora))

    db.commit()
    session.pop("pix_chave", None)
    return redirect("/pix-sent")


@app.route("/pix-sent")
def pix_sent():
    if "idUsuario" not in session:
        return redirect("/")
    return render_template("pix_sent.html")


@app.route("/extrato/<int:idTransferencia>")
def extrato(idTransferencia):
    if "idUsuario" not in session:
        return redirect("/")

    db = get_db()
    cursor = db.cursor()

    idContaUser = obter_id_conta(cursor, session["idUsuario"])
    if not idContaUser:
        return redirect("/dashboard")

    cursor.execute("""
        SELECT
            t.valor,
            t.dataTransferencia,
            uo.nome  AS nome_origem,
            uo.email AS email_origem,
            ud.nome  AS nome_destino,
            ud.email AS email_destino
        FROM transferencias t
        JOIN contas co ON co.idConta = t.idContaOrigem
        JOIN usuarios uo ON uo.idUsuario = co.idUsuario
        JOIN contas cd ON cd.idConta = t.idContaDestino
        JOIN usuarios ud ON ud.idUsuario = cd.idUsuario
        WHERE t.idTransferencia = ?
          AND (t.idContaOrigem = ? OR t.idContaDestino = ?)
        LIMIT 1
    """, (idTransferencia, idContaUser, idContaUser))

    tx = cursor.fetchone()
    if not tx:
        return redirect("/dashboard")

    return render_template(
        "extrato.html",
        metodo="Pix",
        valor=formatar_brl(float(tx[0])),
        data=str(tx[1]).split(".")[0],
        origem_nome=tx[2],
        origem_email=tx[3],
        destino_nome=tx[4],
        destino_email=tx[5],
    )


@app.route("/extrato-lista")
def extrato_lista():
    if "idUsuario" not in session:
        return redirect("/")

    db = get_db()
    cursor = db.cursor()

    idContaUser = obter_id_conta(cursor, session["idUsuario"])
    if not idContaUser:
        return redirect("/dashboard")

    cursor.execute("""
        SELECT
            t.idTransferencia,
            CASE
                WHEN t.idContaOrigem = ? THEN 'Pix enviado'
                ELSE 'Pix recebido'
            END AS descricao,
            CASE
                WHEN t.idContaOrigem = ? THEN 'DEBITO'
                ELSE 'CREDITO'
            END AS tipo,
            t.valor,
            t.dataTransferencia
        FROM transferencias t
        WHERE t.idContaOrigem = ?
           OR t.idContaDestino = ?
        ORDER BY t.dataTransferencia DESC
        LIMIT 20
    """, (idContaUser, idContaUser, idContaUser, idContaUser))

    extrato = cursor.fetchall()
    return render_template("extrato_lista.html", extrato=extrato)


@app.route("/cartoes")
def cartoes():
    if "idUsuario" not in session:
        return redirect("/")

    db = get_db()
    cursor = db.cursor()

    cartoes = buscar_cartoes_8cols(cursor, session["idUsuario"])

    faturas = []
    lancamentos = []
    if cartoes:
        idCartao_sel = cartoes[0][0]
        faturas, lancamentos = carregar_faturas_e_lancamentos(cursor, idCartao_sel)

    return render_template(
        "cartoes.html",
        cartoes=cartoes,
        faturas=faturas,
        lancamentos=lancamentos
    )


@app.route("/cartoes/solicitar", methods=["POST"])
def solicitar_cartao():
    if "idUsuario" not in session:
        return redirect("/")

    db = get_db()
    cursor = db.cursor()

    cartoes_existentes = buscar_cartoes_8cols(cursor, session["idUsuario"])

    if len(cartoes_existentes) >= 3:
        faturas, lancamentos = ([], [])
        if cartoes_existentes:
            faturas, lancamentos = carregar_faturas_e_lancamentos(cursor, cartoes_existentes[0][0])

        return render_template(
            "cartoes.html",
            cartoes=cartoes_existentes,
            faturas=faturas,
            lancamentos=lancamentos,
            erro="Limite máximo de cartões atingido."
        )

    numero_cartao = "".join(str(random.randint(0, 9)) for _ in range(16))
    cvv = random.randint(100, 999)

    hoje = date.today()
    validade_ano = hoje.year + random.randint(2, 10)
    validade_mes = random.randint(1, 12)

    limite = random.randrange(2000, 10001, 100)
    bandeira = random.choice(["VISA", "MASTERCARD"])
    nome_cartao = f"Atlas Bank {bandeira}"

    cursor.execute("""
        INSERT INTO cartoesCredito (
            idUsuario,
            nome,
            limite,
            bandeira,
            numero_cartao,
            cvv,
            validadeMes,
            validadeAno
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        session["idUsuario"],
        nome_cartao,
        limite,
        bandeira,
        numero_cartao,
        str(cvv),
        validade_mes,
        validade_ano
    ))

    db.commit()

    cartoes_novos = buscar_cartoes_8cols(cursor, session["idUsuario"])
    faturas, lancamentos = ([], [])
    if cartoes_novos:
        faturas, lancamentos = carregar_faturas_e_lancamentos(cursor, cartoes_novos[0][0])

    return render_template(
        "cartoes.html",
        cartoes=cartoes_novos,
        faturas=faturas,
        lancamentos=lancamentos,
        sucesso="Cartão aprovado com sucesso!"
    )


@app.route("/shopping")
def shopping():
    if "idUsuario" not in session:
        return redirect("/")

    produtos = [
        {"id": 1, "nome": "Fone Bluetooth", "valor": 299.00, "imagem": "/static/img/fone.png"},
        {"id": 2, "nome": "Smartwatch", "valor": 649.99, "imagem": "/static/img/smartwatch.png"},
        {"id": 3, "nome": "Notebook", "valor": 7998.00, "imagem": "/static/img/notebook.png"},
    ]

    db = get_db()
    cursor = db.cursor()

    cursor.execute("""
        SELECT idCartao, bandeira, numero_cartao
        FROM cartoesCredito
        WHERE idUsuario = ?
    """, (session["idUsuario"],))

    cartoes = [
        {"id": c[0], "bandeira": c[1], "final": c[2][-4:]}
        for c in cursor.fetchall()
    ]

    return render_template("shopping.html", produtos=produtos, cartoes=cartoes)


@app.route("/shopping/comprar", methods=["POST"])
def shopping_comprar():
    if "idUsuario" not in session:
        return redirect("/")

    try:
        idCartao = int(request.form["idCartao"])
        parcelas = int(request.form["parcelas"])
        valor_total = float(request.form["valor"])
        descricao_item = request.form.get("descricao", "Item")
    except:
        return redirect("/shopping")

    if parcelas <= 0:
        parcelas = 1

    db = get_db()
    cursor = db.cursor()

    # busca limite do cartão
    cursor.execute("""
        SELECT limite
        FROM cartoesCredito
        WHERE idCartao = ? AND idUsuario = ?
        LIMIT 1
    """, (idCartao, session["idUsuario"]))
    row_cartao = cursor.fetchone()

    cartoes = buscar_cartoes_8cols(cursor, session["idUsuario"])

    if not row_cartao:
        faturas, lancamentos = ([], [])
        if cartoes:
            faturas, lancamentos = carregar_faturas_e_lancamentos(cursor, cartoes[0][0])
        return render_template("cartoes.html", cartoes=cartoes, faturas=faturas, lancamentos=lancamentos, erro="Cartão inválido.")

    limite_disponivel = float(row_cartao[0])

    if valor_total <= 0:
        faturas, lancamentos = ([], [])
        if cartoes:
            faturas, lancamentos = carregar_faturas_e_lancamentos(cursor, cartoes[0][0])
        return render_template("cartoes.html", cartoes=cartoes, faturas=faturas, lancamentos=lancamentos, erro="Valor inválido para a compra.")

    if valor_total > limite_disponivel:
        faturas, lancamentos = ([], [])
        if cartoes:
            faturas, lancamentos = carregar_faturas_e_lancamentos(cursor, cartoes[0][0])
        return render_template("cartoes.html", cartoes=cartoes, faturas=faturas, lancamentos=lancamentos, erro="Limite insuficiente para realizar a compra.")

    # pega conta do usuário (pra gravar em lancamentos)
    cursor.execute("""
        SELECT idConta
        FROM contas
        WHERE idUsuario = ?
        LIMIT 1
    """, (session["idUsuario"],))
    row_conta = cursor.fetchone()
    if not row_conta:
        return redirect("/dashboard")
    idConta = row_conta[0]

    hoje = datetime.now()

    valor_parcela = round(valor_total / parcelas, 2)
    total_parcelas_calc = round(valor_parcela * parcelas, 2)
    ajuste = round(valor_total - total_parcelas_calc, 2)

    for i in range(parcelas):
        data_parcela = add_months(hoje, i)
        mes_ref = data_parcela.month
        ano_ref = data_parcela.year

        idFatura = get_or_create_fatura(cursor, idCartao, mes_ref, ano_ref)

        valor_i = valor_parcela + (ajuste if i == parcelas - 1 else 0.0)

        descricao = (
            f"Compra {descricao_item} ({i + 1}/{parcelas})"
            if parcelas > 1 else
            f"Compra {descricao_item}"
        )

        cursor.execute("""
            INSERT INTO lancamentos (
                idConta,
                idUsuario,
                idGrupo,
                idFatura,
                valor,
                tipo,
                descricao,
                dataLancamento
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            idConta,
            session["idUsuario"],
            1,
            idFatura,
            valor_i,
            "DEBITO",
            descricao,
            hoje
        ))

        cursor.execute("""
            UPDATE faturas
            SET valorTotal = valorTotal + ?
            WHERE idFatura = ?
        """, (valor_i, idFatura))

    cursor.execute("""
        UPDATE cartoesCredito
        SET limite = limite - ?
        WHERE idCartao = ?
    """, (valor_total, idCartao))

    db.commit()

    # recarrega para render (com lançamentos)
    cartoes = buscar_cartoes_8cols(cursor, session["idUsuario"])
    faturas, lancamentos = ([], [])
    if cartoes:
        # mostra extrato do cartão usado na compra, se existir na lista
        idCartao_sel = idCartao
        faturas, lancamentos = carregar_faturas_e_lancamentos(cursor, idCartao_sel)

    return render_template(
        "cartoes.html",
        cartoes=cartoes,
        faturas=faturas,
        lancamentos=lancamentos,
        sucesso="Compra aprovada com sucesso!"
    )

@app.route("/api/cartoes/<int:idCartao>/lancamentos")
def api_lancamentos_cartao(idCartao):
    if "idUsuario" not in session:
        return {"error": "unauthorized"}, 401

    db = get_db()
    cursor = db.cursor()

    # segurança: garante que o cartão é do usuário
    cursor.execute("""
        SELECT 1
        FROM cartoesCredito
        WHERE idCartao = ? AND idUsuario = ?
        LIMIT 1
    """, (idCartao, session["idUsuario"]))

    if not cursor.fetchone():
        return {"error": "forbidden"}, 403

    cursor.execute("""
        SELECT
            l.descricao,
            l.valor,
            l.dataLancamento,
            f.mesReferencia,
            f.anoReferencia
        FROM lancamentos l
        JOIN faturas f ON f.idFatura = l.idFatura
        WHERE f.idCartao = ?
        ORDER BY f.anoReferencia DESC, f.mesReferencia DESC, l.dataLancamento DESC
    """, (idCartao,))

    lancamentos = [
        {
            "descricao": l[0],
            "valor": f"{l[1]:.2f}".replace(".", ","),
            "data": str(l[2]).split(".")[0],
            "mes": l[3],
            "ano": l[4],
        }
        for l in cursor.fetchall()
    ]

    return {"lancamentos": lancamentos}


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


app.run(debug=True)
