from pathlib import Path
import click
from flask import Flask, render_template
from flask_login import LoginManager
from flask_migrate import Migrate
from .extensions import db
from .models import User, HorarioFuncionamento, Servico

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

    from .routes.auth import bp as auth_bp
    from .routes.dashboard import bp as dashboard_bp
    from .routes.tutores import bp as tutores_bp
    from .routes.pets import bp as pets_bp
    from .routes.servicos import bp as servicos_bp
    from .routes.pacotes import bp as pacotes_bp
    from .routes.agenda import bp as agenda_bp
    from .routes.financeiro import bp as financeiro_bp
    from .routes.configuracoes import bp as configuracoes_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(tutores_bp)
    app.register_blueprint(pets_bp)
    app.register_blueprint(servicos_bp)
    app.register_blueprint(pacotes_bp)
    app.register_blueprint(agenda_bp)
    app.register_blueprint(financeiro_bp)
    app.register_blueprint(configuracoes_bp)

    @app.errorhandler(404)
    def not_found(error):
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        return render_template("errors/500.html"), 500

    register_commands(app)
    return app


def register_commands(app):
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
