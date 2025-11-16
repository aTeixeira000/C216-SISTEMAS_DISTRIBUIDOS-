import os
from flask import Flask, render_template, request, redirect, url_for, flash
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import sessionmaker, declarative_base

# -------------------------------------------------------------------
# Configuração Flask
# -------------------------------------------------------------------
app = Flask(__name__)
app.secret_key = "chave-secreta-bem-simples"  # só pra usar flash()

# -------------------------------------------------------------------
# Configuração do Banco (MySQL via SQLAlchemy)
# -------------------------------------------------------------------
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "mysql+pymysql://user:password@db:3306/faculdade_db"  # default pro docker-compose
)

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

CURSOS_VALIDOS = {"GEC", "GEA", "GES", "GEB", "GET"}


class Aluno(Base):
    __tablename__ = "alunos"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String(100), nullable=False)
    email = Column(String(100), nullable=False, unique=True)
    curso = Column(String(10), nullable=False)
    matricula = Column(String(20), nullable=False, unique=True)


# Cria tabela se não existir
Base.metadata.create_all(bind=engine)


# -------------------------------------------------------------------
# Funções auxiliares
# -------------------------------------------------------------------
def gerar_matricula(db, curso: str) -> str:
    """
    Gera a próxima matrícula daquele curso.
    Ex: GEC1, GEC2, GEA1, ...
    """
    ultimo = (
        db.query(Aluno)
        .filter(Aluno.curso == curso)
        .order_by(Aluno.id.desc())
        .first()
    )

    if ultimo and ultimo.matricula.startswith(curso):
        try:
            numero_atual = int(ultimo.matricula[len(curso):])
        except ValueError:
            numero_atual = 0
        proximo = numero_atual + 1
    else:
        proximo = 1

    return f"{curso}{proximo}"


def get_db():
    """Helper pra criar/fechar sessão."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# -------------------------------------------------------------------
# Rotas Flask (frontend + backend juntos)
# -------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/alunos")
def listar_alunos():
    db = next(get_db())
    alunos = db.query(Aluno).order_by(Aluno.id).all()
    return render_template("alunos_listar.html", alunos=alunos)


@app.route("/alunos/novo", methods=["GET", "POST"])
def novo_aluno():
    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        email = request.form.get("email", "").strip()
        curso = request.form.get("curso", "").strip().upper()

        if not nome or not email or not curso:
            flash("Preencha todos os campos.", "error")
            return redirect(url_for("novo_aluno"))

        if curso not in CURSOS_VALIDOS:
            flash("Curso inválido! Use GEC, GEA, GES, GEB ou GET.", "error")
            return redirect(url_for("novo_aluno"))

        db = next(get_db())
        try:
            matricula = gerar_matricula(db, curso)

            aluno = Aluno(
                nome=nome,
                email=email,
                curso=curso,
                matricula=matricula,
            )
            db.add(aluno)
            db.commit()
            flash(f"Aluno {nome} cadastrado com sucesso! Matrícula: {matricula}", "success")
        except Exception as e:
            db.rollback()
            flash(f"Erro ao cadastrar aluno: {e}", "error")

        return redirect(url_for("listar_alunos"))

    # GET -> mostra formulário
    return render_template("alunos_form.html", aluno=None)


@app.route("/alunos/<int:aluno_id>/editar", methods=["GET", "POST"])
def editar_aluno(aluno_id):
    db = next(get_db())
    aluno = db.query(Aluno).filter(Aluno.id == aluno_id).first()

    if not aluno:
        flash("Aluno não encontrado.", "error")
        return redirect(url_for("listar_alunos"))

    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        email = request.form.get("email", "").strip()
        curso = request.form.get("curso", "").strip().upper()

        if not nome or not email or not curso:
            flash("Preencha todos os campos.", "error")
            return redirect(url_for("editar_aluno", aluno_id=aluno_id))

        if curso not in CURSOS_VALIDOS:
            flash("Curso inválido! Use GEC, GEA, GES, GEB ou GET.", "error")
            return redirect(url_for("editar_aluno", aluno_id=aluno_id))

        try:
            aluno.nome = nome
            aluno.email = email

            # Se mudou o curso, gera nova matrícula
            if curso != aluno.curso:
                aluno.curso = curso
                aluno.matricula = gerar_matricula(db, curso)
                flash("Aluno atualizado com nova matrícula.", "success")
            else:
                flash("Aluno atualizado.", "success")

            db.commit()
        except Exception as e:
            db.rollback()
            flash(f"Erro ao atualizar aluno: {e}", "error")

        return redirect(url_for("listar_alunos"))

    # GET -> mostra formulário com dados preenchidos
    return render_template("alunos_form.html", aluno=aluno)


@app.route("/alunos/<int:aluno_id>/deletar", methods=["POST"])
def deletar_aluno(aluno_id):
    db = next(get_db())
    aluno = db.query(Aluno).filter(Aluno.id == aluno_id).first()

    if not aluno:
        flash("Aluno não encontrado.", "error")
        return redirect(url_for("listar_alunos"))

    try:
        db.delete(aluno)
        db.commit()
        flash("Aluno removido com sucesso!", "success")
    except Exception as e:
        db.rollback()
        flash(f"Erro ao remover aluno: {e}", "error")

    return redirect(url_for("listar_alunos"))


if __name__ == "__main__":
    # roda no 0.0.0.0 para funcionar dentro do container
    app.run(host="0.0.0.0", port=8000, debug=True)
