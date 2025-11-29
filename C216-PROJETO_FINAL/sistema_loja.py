import os
from datetime import date, datetime

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session,
    jsonify,
)
from flask_cors import CORS
from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Date,
    ForeignKey,
)
from sqlalchemy.orm import sessionmaker, declarative_base, relationship

# -------------------------------------------------------------------
# Config Flask
# -------------------------------------------------------------------
app = Flask(__name__)
app.secret_key = "chave-secreta-simples"

# CORS (para cumprir requisito e permitir front separado acessar /api/*)
CORS(app, resources={r"/api/*": {"origins": "http://localhost:*"}})

# -------------------------------------------------------------------
# Config Banco (MySQL via SQLAlchemy)
# -------------------------------------------------------------------
# Em produção / docker, vem do docker-compose:
# DATABASE_URL=mysql+pymysql://user:password@db:3306/loja_db
DATABASE_URL = os.getenv(
    "DATABASE_URL", "sqlite:///loja.db"  # fallback local
)

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# -------------------------------------------------------------------
# MODELOS
# -------------------------------------------------------------------

class Jogo(Base):
    __tablename__ = "jogos"

    id = Column(Integer, primary_key=True, index=True)
    titulo = Column(String(150), nullable=False)
    genero = Column(String(80), nullable=False)
    ano_lancamento = Column(Integer, nullable=False)
    plataformas = Column(String(150), nullable=False)  # ex: "PC, PS5, Xbox"
    desenvolvedora = Column(String(150), nullable=False)
    copias_total = Column(Integer, nullable=False, default=1)

    # relação 1:N com Locacao
    locacoes = relationship("Locacao", back_populates="jogo")

    # relação N:M com Pedido via ItemPedido (lado Jogo)
    itens_pedido = relationship("ItemPedido", back_populates="jogo")

    @property
    def copias_disponiveis(self):
        alugados = sum(1 for loc in self.locacoes if loc.status == "ALUGADO")
        return self.copias_total - alugados


class Cliente(Base):
    __tablename__ = "clientes"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String(150), nullable=False)
    telefone = Column(String(30), nullable=False)
    cpf = Column(String(20), nullable=False, unique=True)
    endereco = Column(String(200), nullable=False)

    # 1:N com Locacao
    locacoes = relationship("Locacao", back_populates="cliente")
    # 1:N com Pedido
    pedidos = relationship("Pedido", back_populates="cliente")


class Locacao(Base):
    """
    Locação de um jogo por um cliente.
    Relação N:1 Cliente-›Locacao e N:1 Jogo-›Locacao.
    """
    __tablename__ = "locacoes"

    id = Column(Integer, primary_key=True, index=True)
    cliente_id = Column(Integer, ForeignKey("clientes.id"), nullable=False)
    jogo_id = Column(Integer, ForeignKey("jogos.id"), nullable=False)
    data_retirada = Column(Date, nullable=False, default=date.today)
    data_devolucao_prevista = Column(Date, nullable=True)
    data_devolucao_real = Column(Date, nullable=True)
    status = Column(String(20), nullable=False, default="ALUGADO")

    cliente = relationship("Cliente", back_populates="locacoes")
    jogo = relationship("Jogo", back_populates="locacoes")


class Pedido(Base):
    """
    Pedido de compra/locação (carrinho).
    Relação N:1 Cliente-›Pedido.
    N:M com Jogo via ItemPedido.
    """
    __tablename__ = "pedidos"

    id = Column(Integer, primary_key=True, index=True)
    cliente_id = Column(Integer, ForeignKey("clientes.id"), nullable=False)
    data = Column(Date, nullable=False, default=date.today)
    status = Column(String(20), nullable=False, default="CONCLUIDO")

    cliente = relationship("Cliente", back_populates="pedidos")
    itens = relationship(
        "ItemPedido",
        back_populates="pedido",
        cascade="all, delete-orphan",
    )


class ItemPedido(Base):
    """
    Tabela intermediária da relação N:M entre Pedido e Jogo.
    """
    __tablename__ = "itens_pedido"

    id = Column(Integer, primary_key=True, index=True)
    pedido_id = Column(Integer, ForeignKey("pedidos.id"), nullable=False)
    jogo_id = Column(Integer, ForeignKey("jogos.id"), nullable=False)
    quantidade = Column(Integer, nullable=False, default=1)

    pedido = relationship("Pedido", back_populates="itens")
    jogo = relationship("Jogo", back_populates="itens_pedido")


# cria tabelas se não existirem
Base.metadata.create_all(bind=engine)

# -------------------------------------------------------------------
# Helpers para converter modelos em dict (JSON)
# -------------------------------------------------------------------

def jogo_to_dict(jogo: Jogo):
    return {
        "id": jogo.id,
        "titulo": jogo.titulo,
        "genero": jogo.genero,
        "ano_lancamento": jogo.ano_lancamento,
        "plataformas": jogo.plataformas,
        "desenvolvedora": jogo.desenvolvedora,
        "copias_total": jogo.copias_total,
        "copias_disponiveis": jogo.copias_disponiveis,
    }


def cliente_to_dict(cliente: Cliente):
    return {
        "id": cliente.id,
        "nome": cliente.nome,
        "telefone": cliente.telefone,
        "cpf": cliente.cpf,
        "endereco": cliente.endereco,
    }


def pedido_to_dict(pedido: Pedido):
    return {
        "id": pedido.id,
        "cliente_id": pedido.cliente_id,
        "data": pedido.data.isoformat() if pedido.data else None,
        "status": pedido.status,
        "itens": [
            {
                "id": item.id,
                "jogo_id": item.jogo_id,
                "quantidade": item.quantidade,
            }
            for item in pedido.itens
        ],
    }


# -------------------------------------------------------------------
# Helper de sessão / banco
# -------------------------------------------------------------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# -------------------------------------------------------------------
# Carrinho de compras via session
# -------------------------------------------------------------------
def get_cart():
    """Retorna o carrinho da sessão como dict {jogo_id: quantidade}."""
    cart = session.get("cart", {})
    # garantir que as chaves sejam int
    return {int(k): int(v) for k, v in cart.items()}


def save_cart(cart):
    """Salva o carrinho na sessão."""
    session["cart"] = {str(k): int(v) for k, v in cart.items()}


# -------------------------------------------------------------------
# ROTAS HTML (páginas)
# -------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


# -------------------- JOGOS --------------------
@app.route("/jogos")
def listar_jogos():
    db = next(get_db())
    jogos = db.query(Jogo).order_by(Jogo.titulo).all()
    return render_template("jogos_listar.html", jogos=jogos)


@app.route("/jogos/novo", methods=["GET", "POST"])
def cadastrar_jogo():
    db = next(get_db())
    if request.method == "POST":
        titulo = request.form.get("titulo")
        genero = request.form.get("genero")
        ano_lancamento = request.form.get("ano_lancamento")
        plataformas = request.form.get("plataformas")
        desenvolvedora = request.form.get("desenvolvedora")
        copias_total = request.form.get("copias_total")

        if not (titulo and genero and ano_lancamento and plataformas and desenvolvedora and copias_total):
            flash("Preencha todos os campos.", "error")
            return redirect(url_for("cadastrar_jogo"))

        try:
            ano_int = int(ano_lancamento)
            copias_int = int(copias_total)
            if copias_int <= 0:
                raise ValueError
        except ValueError:
            flash("Ano de lançamento e cópias devem ser números válidos.", "error")
            return redirect(url_for("cadastrar_jogo"))

        try:
            jogo = Jogo(
                titulo=titulo,
                genero=genero,
                ano_lancamento=ano_int,
                plataformas=plataformas,
                desenvolvedora=desenvolvedora,
                copias_total=copias_int,
            )
            db.add(jogo)
            db.commit()
            flash("Jogo cadastrado com sucesso!", "success")
        except Exception as e:
            db.rollback()
            flash(f"Erro ao cadastrar jogo: {e}", "error")

        return redirect(url_for("listar_jogos"))

    return render_template("jogos_cadastrar.html")


@app.route("/jogos/<int:jogo_id>/editar", methods=["GET", "POST"])
def editar_jogo(jogo_id):
    db = next(get_db())
    jogo = db.query(Jogo).filter(Jogo.id == jogo_id).first()
    if not jogo:
        flash("Jogo não encontrado.", "error")
        return redirect(url_for("listar_jogos"))

    if request.method == "POST":
        jogo.titulo = request.form.get("titulo")
        jogo.genero = request.form.get("genero")
        jogo.plataformas = request.form.get("plataformas")
        jogo.desenvolvedora = request.form.get("desenvolvedora")

        try:
            jogo.ano_lancamento = int(request.form.get("ano_lancamento"))
            jogo.copias_total = int(request.form.get("copias_total"))
        except ValueError:
            flash("Ano de lançamento e cópias devem ser números válidos.", "error")
            return redirect(url_for("editar_jogo", jogo_id=jogo_id))

        try:
            db.commit()
            flash("Jogo atualizado com sucesso!", "success")
        except Exception as e:
            db.rollback()
            flash(f"Erro ao atualizar jogo: {e}", "error")

        return redirect(url_for("listar_jogos"))

    return render_template("jogos_editar.html", jogo=jogo)


@app.route("/jogos/<int:jogo_id>/deletar", methods=["POST"])
def deletar_jogo(jogo_id):
    db = next(get_db())
    jogo = db.query(Jogo).filter(Jogo.id == jogo_id).first()
    if not jogo:
        flash("Jogo não encontrado.", "error")
        return redirect(url_for("listar_jogos"))

    try:
        db.delete(jogo)
        db.commit()
        flash("Jogo removido com sucesso!", "success")
    except Exception as e:
        db.rollback()
        flash(f"Erro ao remover jogo: {e}", "error")

    return redirect(url_for("listar_jogos"))


# -------------------- CLIENTES --------------------

@app.route("/clientes")
def listar_clientes():
    db = next(get_db())
    clientes = db.query(Cliente).order_by(Cliente.nome).all()
    return render_template("clientes_listar.html", clientes=clientes)


@app.route("/clientes/novo", methods=["GET", "POST"])
def cadastrar_cliente():
    db = next(get_db())
    if request.method == "POST":
        nome = request.form.get("nome")
        telefone = request.form.get("telefone")
        cpf = request.form.get("cpf")
        endereco = request.form.get("endereco")

        if not (nome and telefone and cpf and endereco):
            flash("Preencha todos os campos.", "error")
            return redirect(url_for("cadastrar_cliente"))

        cliente = Cliente(
            nome=nome,
            telefone=telefone,
            cpf=cpf,
            endereco=endereco,
        )
        db.add(cliente)
        try:
            db.commit()
            flash("Cliente cadastrado com sucesso!", "success")
        except Exception as e:
            db.rollback()
            flash(f"Erro ao cadastrar cliente: {e}", "error")

        return redirect(url_for("listar_clientes"))

    return render_template("clientes_cadastrar.html")


@app.route("/clientes/<int:cliente_id>/editar", methods=["GET", "POST"])
def editar_cliente(cliente_id):
    db = next(get_db())
    cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
    if not cliente:
        flash("Cliente não encontrado.", "error")
        return redirect(url_for("listar_clientes"))

    if request.method == "POST":
        cliente.nome = request.form.get("nome")
        cliente.telefone = request.form.get("telefone")
        cliente.cpf = request.form.get("cpf")
        cliente.endereco = request.form.get("endereco")

        try:
            db.commit()
            flash("Cliente atualizado com sucesso!", "success")
        except Exception as e:
            db.rollback()
            flash(f"Erro ao atualizar cliente: {e}", "error")

        return redirect(url_for("listar_clientes"))

    return render_template("clientes_editar.html", cliente=cliente)


@app.route("/clientes/<int:cliente_id>/deletar", methods=["POST"])
def deletar_cliente(cliente_id):
    db = next(get_db())
    cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
    if not cliente:
        flash("Cliente não encontrado.", "error")
        return redirect(url_for("listar_clientes"))

    try:
        db.delete(cliente)
        db.commit()
        flash("Cliente removido com sucesso!", "success")
    except Exception as e:
        db.rollback()
        flash(f"Erro ao remover cliente: {e}", "error")

    return redirect(url_for("listar_clientes"))


# -------------------- LOJA / CARRINHO --------------------

@app.route("/loja")
def loja():
    db = next(get_db())
    jogos = db.query(Jogo).order_by(Jogo.titulo).all()
    cart = get_cart()
    return render_template("loja.html", jogos=jogos, cart=cart)


@app.route("/carrinho")
def ver_carrinho():
    db = next(get_db())
    cart = get_cart()
    jogos = db.query(Jogo).filter(Jogo.id.in_(cart.keys())).all() if cart else []
    jogos_map = {j.id: j for j in jogos}
    return render_template("carrinho.html", cart=cart, jogos=jogos_map)


@app.route("/carrinho/adicionar/<int:jogo_id>", methods=["POST"])
def adicionar_ao_carrinho(jogo_id):
    cart = get_cart()
    qtd = int(request.form.get("quantidade", 1))
    if qtd <= 0:
        qtd = 1
    cart[jogo_id] = cart.get(jogo_id, 0) + qtd
    save_cart(cart)
    flash("Jogo adicionado ao carrinho.", "success")
    return redirect(url_for("loja"))


@app.route("/carrinho/remover/<int:jogo_id>", methods=["POST"])
def remover_do_carrinho(jogo_id):
    cart = get_cart()
    if jogo_id in cart:
        del cart[jogo_id]
        save_cart(cart)
        flash("Item removido do carrinho.", "success")
    else:
        flash("Item não encontrado no carrinho.", "error")

    return redirect(url_for("ver_carrinho"))


@app.route("/carrinho/finalizar", methods=["GET", "POST"])
def finalizar_compra():
    db = next(get_db())
    cart = get_cart()

    if not cart:
        flash("Carrinho vazio.", "error")
        return redirect(url_for("loja"))

    # busca os jogos do carrinho uma vez só
    jogos = db.query(Jogo).filter(Jogo.id.in_(cart.keys())).all()
    jogos_map = {j.id: j for j in jogos}

    if request.method == "POST":
        cliente_id = request.form.get("cliente_id")

        if not cliente_id:
            flash("Selecione um cliente para finalizar a compra.", "error")
            return redirect(url_for("finalizar_compra"))

        try:
            cliente_id_int = int(cliente_id)
        except ValueError:
            flash("Cliente inválido.", "error")
            return redirect(url_for("finalizar_compra"))

        cliente = db.query(Cliente).filter(Cliente.id == cliente_id_int).first()
        if not cliente:
            flash("Cliente não encontrado.", "error")
            return redirect(url_for("finalizar_compra"))

        # 1) valida se tem estoque suficiente pra todos os itens
        for jogo_id, quantidade in cart.items():
            jogo = jogos_map.get(jogo_id)
            if not jogo:
                continue
            if jogo.copias_disponiveis < quantidade:
                flash(
                    f"Não há estoque suficiente de '{jogo.titulo}' "
                    f"para essa compra (disponíveis: {jogo.copias_disponiveis}).",
                    "error",
                )
                return redirect(url_for("ver_carrinho"))

        try:
            # 2) cria o PEDIDO (compra)
            pedido = Pedido(
                cliente_id=cliente.id,
                data=date.today(),
                status="CONCLUIDO",
            )
            db.add(pedido)
            db.flush()  # garante pedido.id

            # 3) cria os ITENS DO PEDIDO e abate do estoque
            for jogo_id, quantidade in cart.items():
                jogo = jogos_map.get(jogo_id)
                if not jogo:
                    continue

                item = ItemPedido(
                    pedido_id=pedido.id,
                    jogo_id=jogo.id,
                    quantidade=quantidade,
                )
                db.add(item)

                # abate do estoque total
                jogo.copias_total -= quantidade
                if jogo.copias_total < 0:
                    jogo.copias_total = 0  # só por segurança

            db.commit()
            # limpa carrinho
            save_cart({})
            flash("Compra finalizada com sucesso!", "success")
            return redirect(url_for("loja"))

        except Exception as e:
            db.rollback()
            flash(f"Erro ao finalizar compra: {e}", "error")
            return redirect(url_for("ver_carrinho"))

    # GET -> mostra página para escolher cliente e confirmar
    clientes = db.query(Cliente).order_by(Cliente.nome).all()
    jogos = db.query(Jogo).filter(Jogo.id.in_(cart.keys())).all()
    jogos_map = {j.id: j for j in jogos}
    return render_template("finalizar_compra.html", cart=cart, jogos=jogos_map, clientes=clientes)


# -------------------------------------------------------------------
# API REST (JSON) - CRUD completo para Jogo e Cliente + listagem de pedidos
# -------------------------------------------------------------------

# ---------- JOGOS (CRUD completo) ----------

@app.route("/api/jogos", methods=["GET"])
def api_listar_jogos():
    db = next(get_db())
    jogos = db.query(Jogo).order_by(Jogo.titulo).all()
    return jsonify([jogo_to_dict(j) for j in jogos]), 200


@app.route("/api/jogos/<int:jogo_id>", methods=["GET"])
def api_obter_jogo(jogo_id):
    db = next(get_db())
    jogo = db.query(Jogo).filter(Jogo.id == jogo_id).first()
    if not jogo:
        return jsonify({"error": "Jogo não encontrado"}), 404
    return jsonify(jogo_to_dict(jogo)), 200


@app.route("/api/jogos", methods=["POST"])
def api_criar_jogo():
    db = next(get_db())
    data = request.get_json() or {}

    campos_obrigatorios = ["titulo", "genero", "ano_lancamento", "plataformas", "desenvolvedora", "copias_total"]
    if not all(c in data for c in campos_obrigatorios):
        return jsonify({"error": "Campos obrigatórios: " + ", ".join(campos_obrigatorios)}), 400

    try:
        ano = int(data["ano_lancamento"])
        copias = int(data["copias_total"])
        if copias <= 0:
            raise ValueError
    except (ValueError, TypeError):
        return jsonify({"error": "ano_lancamento e copias_total devem ser inteiros válidos"}), 400

    jogo = Jogo(
        titulo=data["titulo"],
        genero=data["genero"],
        ano_lancamento=ano,
        plataformas=data["plataformas"],
        desenvolvedora=data["desenvolvedora"],
        copias_total=copias,
    )

    db.add(jogo)
    db.commit()
    db.refresh(jogo)
    return jsonify(jogo_to_dict(jogo)), 201


@app.route("/api/jogos/<int:jogo_id>", methods=["PUT"])
def api_atualizar_jogo(jogo_id):
    db = next(get_db())
    jogo = db.query(Jogo).filter(Jogo.id == jogo_id).first()
    if not jogo:
        return jsonify({"error": "Jogo não encontrado"}), 404

    data = request.get_json() or {}

    if "titulo" in data:
        jogo.titulo = data["titulo"]
    if "genero" in data:
        jogo.genero = data["genero"]
    if "ano_lancamento" in data:
        try:
            jogo.ano_lancamento = int(data["ano_lancamento"])
        except (ValueError, TypeError):
            return jsonify({"error": "ano_lancamento deve ser inteiro"}), 400
    if "plataformas" in data:
        jogo.plataformas = data["plataformas"]
    if "desenvolvedora" in data:
        jogo.desenvolvedora = data["desenvolvedora"]
    if "copias_total" in data:
        try:
            copias = int(data["copias_total"])
            if copias <= 0:
                raise ValueError
            jogo.copias_total = copias
        except (ValueError, TypeError):
            return jsonify({"error": "copias_total deve ser inteiro positivo"}), 400

    db.commit()
    db.refresh(jogo)
    return jsonify(jogo_to_dict(jogo)), 200


@app.route("/api/jogos/<int:jogo_id>", methods=["DELETE"])
def api_deletar_jogo(jogo_id):
    db = next(get_db())
    jogo = db.query(Jogo).filter(Jogo.id == jogo_id).first()
    if not jogo:
        return jsonify({"error": "Jogo não encontrado"}), 404

    db.delete(jogo)
    db.commit()
    return jsonify({"message": "Jogo deletado com sucesso"}), 200


# ---------- CLIENTES (CRUD completo) ----------

@app.route("/api/clientes", methods=["GET"])
def api_listar_clientes():
    db = next(get_db())
    clientes = db.query(Cliente).order_by(Cliente.nome).all()
    return jsonify([cliente_to_dict(c) for c in clientes]), 200


@app.route("/api/clientes/<int:cliente_id>", methods=["GET"])
def api_obter_cliente(cliente_id):
    db = next(get_db())
    cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
    if not cliente:
        return jsonify({"error": "Cliente não encontrado"}), 404
    return jsonify(cliente_to_dict(cliente)), 200


@app.route("/api/clientes", methods=["POST"])
def api_criar_cliente():
    db = next(get_db())
    data = request.get_json() or {}

    campos_obrigatorios = ["nome", "telefone", "cpf", "endereco"]
    if not all(c in data for c in campos_obrigatorios):
        return jsonify({"error": "Campos obrigatórios: " + ", ".join(campos_obrigatorios)}), 400

    cliente = Cliente(
        nome=data["nome"],
        telefone=data["telefone"],
        cpf=data["cpf"],
        endereco=data["endereco"],
    )
    db.add(cliente)
    try:
        db.commit()
        db.refresh(cliente)
    except Exception as e:
        db.rollback()
        return jsonify({"error": f"Erro ao salvar cliente: {e}"}), 400

    return jsonify(cliente_to_dict(cliente)), 201

@app.route("/api/clientes/<int:cliente_id>", methods=["PUT"])
def api_atualizar_cliente(cliente_id):
    db = next(get_db())
    cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
    if not cliente:
        return jsonify({"error": "Cliente não encontrado"}), 404

    data = request.get_json() or {}

    if "nome" in data:
        cliente.nome = data["nome"]
    if "telefone" in data:
        cliente.telefone = data["telefone"]
    if "cpf" in data:
        cliente.cpf = data["cpf"]
    if "endereco" in data:
        cliente.endereco = data["endereco"]

    try:
        db.commit()
        db.refresh(cliente)
    except Exception as e:
        db.rollback()
        return jsonify({"error": f"Erro ao atualizar cliente: {e}"}), 400

    return jsonify(cliente_to_dict(cliente)), 200


@app.route("/api/clientes/<int:cliente_id>", methods=["DELETE"])
def api_deletar_cliente(cliente_id):
    db = next(get_db())
    cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
    if not cliente:
        return jsonify({"error": "Cliente não encontrado"}), 404

    try:
        db.delete(cliente)
        db.commit()
    except Exception as e:
        db.rollback()
        return jsonify({"error": f"Erro ao remover cliente: {e}"}), 400

    return jsonify({"message": "Cliente deletado com sucesso"}), 200


# ---------- PEDIDOS (lista pedidos de um cliente, mostrando N:1 e N:M) ----------

@app.route("/api/clientes/<int:cliente_id>/pedidos", methods=["GET"])
def api_listar_pedidos_cliente(cliente_id):
    db = next(get_db())
    cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
    if not cliente:
        return jsonify({"error": "Cliente não encontrado"}), 404

    pedidos = db.query(Pedido).filter(Pedido.cliente_id == cliente_id).all()
    return jsonify([pedido_to_dict(p) for p in pedidos]), 200

# -------------------- LOCAÇÕES --------------------

# -------------------- LOCAÇÕES (ALUGUEL) --------------------

@app.route("/locacoes")
def listar_locacoes():
    db = next(get_db())
    locacoes = (
        db.query(Locacao)
        .order_by(Locacao.data_retirada.desc())
        .all()
    )
    return render_template("locacoes_listar.html", locacoes=locacoes)


@app.route("/locacoes/novo", methods=["GET", "POST"])
def cadastrar_locacao():
    db = next(get_db())

    if request.method == "POST":
        cliente_id = request.form.get("cliente_id")
        jogo_id = request.form.get("jogo_id")
        data_retirada_str = request.form.get("data_retirada")
        data_prevista_str = request.form.get("data_devolucao_prevista")
        status = request.form.get("status", "ALUGADO")
        ja_devolveu = (status == "DEVOLVIDO")

        # valida campos básicos
        if not (cliente_id and jogo_id and data_retirada_str):
            flash("Preencha cliente, jogo e data de retirada.", "error")
            return redirect(url_for("cadastrar_locacao"))

        try:
            cliente_id_int = int(cliente_id)
            jogo_id_int = int(jogo_id)
        except ValueError:
            flash("Cliente ou jogo inválido.", "error")
            return redirect(url_for("cadastrar_locacao"))

        cliente = db.query(Cliente).filter(Cliente.id == cliente_id_int).first()
        jogo = db.query(Jogo).filter(Jogo.id == jogo_id_int).first()

        if not cliente or not jogo:
            flash("Cliente ou jogo não encontrado.", "error")
            return redirect(url_for("cadastrar_locacao"))

        # converte datas
        try:
            data_retirada = datetime.strptime(data_retirada_str, "%Y-%m-%d").date()
        except ValueError:
            flash("Data de retirada inválida.", "error")
            return redirect(url_for("cadastrar_locacao"))

        data_prevista = None
        if data_prevista_str:
            try:
                data_prevista = datetime.strptime(data_prevista_str, "%Y-%m-%d").date()
            except ValueError:
                flash("Data de devolução prevista inválida.", "error")
                return redirect(url_for("cadastrar_locacao"))

        # se for aluguel em aberto, checa se tem cópias disponíveis
        if not ja_devolveu and jogo.copias_disponiveis <= 0:
            flash(f"Não há cópias disponíveis de '{jogo.titulo}' para alugar.", "error")
            return redirect(url_for("cadastrar_locacao"))

        # se já devolveu, data_devolucao_real = hoje (ou mesma da retirada, se preferir)
        data_devolucao_real = None
        if ja_devolveu:
            data_devolucao_real = date.today()

        try:
            loc = Locacao(
                cliente_id=cliente.id,
                jogo_id=jogo.id,
                data_retirada=data_retirada,
                data_devolucao_prevista=data_prevista,
                data_devolucao_real=data_devolucao_real,
                status=status,
            )
            db.add(loc)
            db.commit()
            flash("Locação registrada com sucesso!", "success")
            return redirect(url_for("listar_locacoes"))
        except Exception as e:
            db.rollback()
            flash(f"Erro ao registrar locação: {e}", "error")
            return redirect(url_for("cadastrar_locacao"))

    # GET -> mostra form
    clientes = db.query(Cliente).order_by(Cliente.nome).all()
    jogos = db.query(Jogo).order_by(Jogo.titulo).all()
    return render_template("locacoes_cadastrar.html", clientes=clientes, jogos=jogos)


@app.route("/locacoes/<int:locacao_id>/editar", methods=["GET", "POST"])
def editar_locacao(locacao_id):
    db = next(get_db())
    loc = db.query(Locacao).filter(Locacao.id == locacao_id).first()
    if not loc:
        flash("Locação não encontrada.", "error")
        return redirect(url_for("listar_locacoes"))

    if request.method == "POST":
        status = request.form.get("status", "ALUGADO")
        data_devolucao_real_str = request.form.get("data_devolucao_real")

        loc.status = status

        # se marcar como DEVOLVIDO e não tiver data, preenche com hoje
        if status == "DEVOLVIDO":
            if data_devolucao_real_str:
                try:
                    loc.data_devolucao_real = datetime.strptime(
                        data_devolucao_real_str, "%Y-%m-%d"
                    ).date()
                except ValueError:
                    flash("Data de devolução real inválida.", "error")
                    return redirect(url_for("editar_locacao", locacao_id=loc.id))
            else:
                loc.data_devolucao_real = date.today()
        else:
            # se voltar para ALUGADO, opcionalmente zera a data_devolucao_real
            loc.data_devolucao_real = None

        try:
            db.commit()
            flash("Locação atualizada com sucesso!", "success")
        except Exception as e:
            db.rollback()
            flash(f"Erro ao atualizar locação: {e}", "error")

        return redirect(url_for("listar_locacoes"))

    return render_template("locacoes_editar.html", locacao=loc)


@app.route("/locacoes/<int:locacao_id>/deletar", methods=["POST"])
def deletar_locacao(locacao_id):
    db = next(get_db())
    loc = db.query(Locacao).filter(Locacao.id == locacao_id).first()
    if not loc:
        flash("Locação não encontrada.", "error")
        return redirect(url_for("listar_locacoes"))

    try:
        db.delete(loc)
        db.commit()
        flash("Locação removida com sucesso!", "success")
    except Exception as e:
        db.rollback()
        flash(f"Erro ao remover locação: {e}", "error")

    return redirect(url_for("listar_locacoes"))

@app.route("/locacoes/<int:locacao_id>/devolver", methods=["POST"])
def devolver_locacao(locacao_id):
    db = next(get_db())
    loc = db.query(Locacao).filter(Locacao.id == locacao_id).first()
    if not loc:
        flash("Locação não encontrada.", "error")
        return redirect(url_for("listar_locacoes"))

    if loc.status == "DEVOLVIDO":
        flash("Essa locação já está marcada como devolvida.", "info")
        return redirect(url_for("listar_locacoes"))

    # Marca como devolvido e registra data de hoje
    loc.status = "DEVOLVIDO"
    loc.data_devolucao_real = date.today()

    try:
        db.commit()
        flash("Devolução registrada com sucesso!", "success")
    except Exception as e:
        db.rollback()
        flash(f"Erro ao registrar devolução: {e}", "error")

    return redirect(url_for("listar_locacoes"))



# -------------------------------------------------------------------
# MAIN
# -------------------------------------------------------------------
if __name__ == "__main__":
    # No docker-compose, o host 0.0.0.0 é obrigatório
    app.run(host="0.0.0.0", port=8000, debug=True)
