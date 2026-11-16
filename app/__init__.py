from pathlib import Path
from datetime import date
import hashlib
import sqlite3
from contextlib import closing
import click
from flask import Flask, render_template
from flask_login import LoginManager, current_user
from flask_migrate import Migrate
from sqlalchemy import inspect, text
from .extensions import db
from .models import User, HorarioFuncionamento, Servico, Pet, HotelConfig

login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message = "Faça login para acessar o sistema."
login_manager.login_message_category = "warning"
migrate = Migrate()


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


def create_app():
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object("config.Config")

    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)
    with app.app_context():
        # Banco novo de desenvolvimento: cria tudo. Banco existente: upgrade explícito
        # após backup, antes de iniciar o serviço com esta versão.
        if "pacotes_clientes" not in inspect(db.engine).get_table_names():
            ensure_schema(app)

    from .routes.auth import bp as auth_bp
    from .routes.dashboard import bp as dashboard_bp
    from .routes.tutores import bp as tutores_bp
    from .routes.pets import bp as pets_bp
    from .routes.servicos import bp as servicos_bp
    from .routes.pacotes import bp as pacotes_bp
    from .routes.agenda import bp as agenda_bp
    from .routes.financeiro import bp as financeiro_bp
    from .routes.configuracoes import bp as configuracoes_bp
    from .routes.hotel import bp as hotel_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(tutores_bp)
    app.register_blueprint(pets_bp)
    app.register_blueprint(servicos_bp)
    app.register_blueprint(pacotes_bp)
    app.register_blueprint(agenda_bp)
    app.register_blueprint(financeiro_bp)
    app.register_blueprint(configuracoes_bp)
    app.register_blueprint(hotel_bp)

    @app.errorhandler(404)
    def not_found(error):
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        return render_template("errors/500.html"), 500

    @app.context_processor
    def inject_pet_birthday_alerts():
        if not current_user.is_authenticated:
            return {"pet_birthday_alerts": []}
        hoje = date.today()
        pets = Pet.query.filter(Pet.ativo.is_(True), Pet.data_aniversario.isnot(None)).all()
        alertas = []
        for pet in pets:
            dias = pet.dias_para_aniversario(hoje)
            if dias is not None and dias <= 7:
                alertas.append({"pet": pet, "dias": dias})
        alertas.sort(key=lambda item: (item["dias"], item["pet"].nome))
        return {"pet_birthday_alerts": alertas[:5]}

    register_commands(app)
    return app


def ensure_schema(app):
    with app.app_context():
        db.create_all()
        inspector = inspect(db.engine)
        if "pets" not in inspector.get_table_names():
            return
        columns = {column["name"] for column in inspector.get_columns("pets")}
        if "data_aniversario" not in columns:
            with db.engine.begin() as connection:
                connection.execute(text("ALTER TABLE pets ADD COLUMN data_aniversario DATE"))
        # Migração incremental de tabelas legadas; nunca altera valores existentes.
        package_columns = {column["name"] for column in inspector.get_columns("pacotes_clientes")}
        additions = {
            "contrato_id": "INTEGER REFERENCES pacotes_clientes(id)",
            "ciclo_anterior_id": "INTEGER REFERENCES pacotes_clientes(id)",
            "tipo_renovacao": "VARCHAR(20)",
            "aprovado_em": "TIMESTAMP",
            "aprovado_por_id": "INTEGER REFERENCES users(id)",
            "encerrado_em": "DATE",
            "creditos_expirados": "INTEGER NOT NULL DEFAULT 0",
            "dia_ancora": "INTEGER",
        }
        with db.engine.begin() as connection:
            for name, definition in additions.items():
                if name not in package_columns:
                    connection.execute(text(f"ALTER TABLE pacotes_clientes ADD COLUMN {name} {definition}"))
            connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_pacote_ciclo_anterior ON pacotes_clientes(ciclo_anterior_id)"))
        hotel_columns = {column["name"] for column in inspector.get_columns("hospedagens")}
        hotel_additions = {
            "pago": "BOOLEAN NOT NULL DEFAULT 0",
            "data_pagamento": "DATE",
            "forma_pagamento": "VARCHAR(50)",
        }
        with db.engine.begin() as connection:
            for name, definition in hotel_additions.items():
                if name not in hotel_columns:
                    connection.execute(text(f"ALTER TABLE hospedagens ADD COLUMN {name} {definition}"))
        if db.session.get(HotelConfig, 1) is None:
            db.session.add(HotelConfig(id=1, diaria_padrao=0))
            db.session.commit()


def register_commands(app):
    @app.cli.command("backup-db")
    @click.argument("destino", type=click.Path(path_type=Path))
    def backup_db_command(destino):
        """Backup consistente e verificado do SQLite, sem sobrescrever arquivos."""
        if db.engine.dialect.name != "sqlite" or not db.engine.url.database:
            raise click.ClickException("Use pg_dump para PostgreSQL; este comando é apenas para SQLite em arquivo.")
        origem = Path(db.engine.url.database).resolve()
        destino = destino.resolve()
        if destino.exists() or destino == origem:
            raise click.ClickException("Destino já existe ou coincide com o banco original.")
        destino.parent.mkdir(parents=True, exist_ok=True)
        try:
            with closing(sqlite3.connect(f"file:{origem.as_posix()}?mode=ro", uri=True)) as source:
                with closing(sqlite3.connect(destino)) as target:
                    source.backup(target)
                    result = target.execute("PRAGMA integrity_check").fetchone()[0]
                    if result != "ok":
                        raise click.ClickException(f"Backup falhou na verificação: {result}")
                    tables = target.execute("SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
                    if tables == 0:
                        raise click.ClickException("Backup sem tabelas.")
            digest = hashlib.sha256(destino.read_bytes()).hexdigest()
            click.echo(f"Backup validado: {destino} | SHA256 {digest}")
        except Exception:
            if destino.exists():
                destino.unlink()
            raise

    @app.cli.command("upgrade-safe")
    def upgrade_safe_command():
        """Confere e aplica apenas estruturas aditivas; faça backup antes em produção."""
        ensure_schema(app)
        click.echo("Estrutura aditiva verificada.")
    @app.cli.command("init-db")
    def init_db_command():
        """Cria as tabelas e dados iniciais."""
        db.create_all()
        seed_defaults()
        click.echo("Banco inicializado com sucesso.")
        click.echo("Login padrão: admin@petagenda.local / admin123")

    @app.cli.command("seed")
    def seed_command():
        """Cria dados iniciais sem recriar tabelas."""
        seed_defaults()
        click.echo("Dados iniciais verificados/criados.")


def seed_defaults():
    if not User.query.filter_by(email="admin@petagenda.local").first():
        admin = User(nome="Administrador", email="admin@petagenda.local", role="admin", ativo=True)
        admin.set_password("admin123")
        db.session.add(admin)

    horarios = [
        (0, "Segunda", "08:00", "18:00", True),
        (1, "Terça", "08:00", "18:00", True),
        (2, "Quarta", "08:00", "18:00", True),
        (3, "Quinta", "08:00", "18:00", True),
        (4, "Sexta", "08:00", "18:00", True),
        (5, "Sábado", "08:00", "14:00", True),
        (6, "Domingo", "08:00", "12:00", False),
    ]
    for dia_semana, nome, inicio, fim, ativo in horarios:
        if not HorarioFuncionamento.query.filter_by(dia_semana=dia_semana).first():
            db.session.add(HorarioFuncionamento(
                dia_semana=dia_semana,
                nome_dia=nome,
                hora_inicio=inicio,
                hora_fim=fim,
                ativo=ativo,
            ))

    servicos = [
        ("Banho", "Pequeno", 60, 50.00),
        ("Banho", "Médio", 90, 70.00),
        ("Banho", "Grande", 120, 100.00),
        ("Banho + Tosa", "Pequeno", 120, 90.00),
        ("Banho + Tosa", "Médio", 150, 120.00),
        ("Tosa higiênica", "Todos", 45, 40.00),
        ("Corte de unhas", "Todos", 20, 20.00),
    ]
    for nome, porte, duracao, valor in servicos:
        exists = Servico.query.filter_by(nome=nome, porte=porte).first()
        if not exists:
            db.session.add(Servico(nome=nome, porte=porte, duracao_minutos=duracao, valor=valor, ativo=True))

    db.session.commit()
