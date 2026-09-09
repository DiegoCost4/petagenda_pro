from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app.extensions import db
from app.models import HorarioFuncionamento, BloqueioAgenda, User

bp = Blueprint("configuracoes", __name__, url_prefix="/configuracoes")


@bp.route("/", methods=["GET", "POST"])
@login_required
def index():
    horarios = HorarioFuncionamento.query.order_by(HorarioFuncionamento.dia_semana).all()
    bloqueios = BloqueioAgenda.query.order_by(BloqueioAgenda.data.desc(), BloqueioAgenda.hora_inicio).limit(30).all()
    usuarios = User.query.order_by(User.nome).all()
    return render_template("configuracoes/index.html", horarios=horarios, bloqueios=bloqueios, usuarios=usuarios)


@bp.route("/horarios", methods=["POST"])
@login_required
def salvar_horarios():
    horarios = HorarioFuncionamento.query.order_by(HorarioFuncionamento.dia_semana).all()
    for horario in horarios:
        prefix = f"dia_{horario.id}"
        horario.hora_inicio = request.form.get(f"{prefix}_inicio", horario.hora_inicio)
        horario.hora_fim = request.form.get(f"{prefix}_fim", horario.hora_fim)
        horario.pausa_inicio = request.form.get(f"{prefix}_pausa_inicio") or None
        horario.pausa_fim = request.form.get(f"{prefix}_pausa_fim") or None
        horario.ativo = bool(request.form.get(f"{prefix}_ativo"))
    db.session.commit()
    flash("Horários de funcionamento atualizados.", "success")
    return redirect(url_for("configuracoes.index"))


@bp.route("/bloqueios/novo", methods=["POST"])
@login_required
def novo_bloqueio():
    try:
        data_ref = datetime.strptime(request.form.get("data"), "%Y-%m-%d").date()
    except Exception:
        flash("Data inválida.", "warning")
        return redirect(url_for("configuracoes.index"))
    bloqueio = BloqueioAgenda(
        data=data_ref,
        hora_inicio=request.form.get("hora_inicio"),
        hora_fim=request.form.get("hora_fim"),
        motivo=request.form.get("motivo", "Bloqueio manual"),
    )
    if not bloqueio.hora_inicio or not bloqueio.hora_fim:
        flash("Informe início e fim do bloqueio.", "warning")
        return redirect(url_for("configuracoes.index"))
    db.session.add(bloqueio)
    db.session.commit()
    flash("Bloqueio criado com sucesso.", "success")
    return redirect(url_for("configuracoes.index"))


@bp.route("/bloqueios/<int:bloqueio_id>/excluir", methods=["POST"])
@login_required
def excluir_bloqueio(bloqueio_id):
    bloqueio = db.get_or_404(BloqueioAgenda, bloqueio_id)
    db.session.delete(bloqueio)
    db.session.commit()
    flash("Bloqueio excluído.", "info")
    return redirect(url_for("configuracoes.index"))


@bp.route("/usuarios/novo", methods=["POST"])
@login_required
def novo_usuario():
    nome = request.form.get("nome", "").strip()
    email = request.form.get("email", "").strip().lower()
    senha = request.form.get("senha", "")
    if not nome or not email or not senha:
        flash("Nome, e-mail e senha são obrigatórios.", "warning")
        return redirect(url_for("configuracoes.index"))
    if User.query.filter_by(email=email).first():
        flash("Já existe um usuário com esse e-mail.", "warning")
        return redirect(url_for("configuracoes.index"))
    usuario = User(nome=nome, email=email, role="admin", ativo=True)
    usuario.set_password(senha)
    db.session.add(usuario)
    db.session.commit()
    flash("Usuário criado com sucesso.", "success")
    return redirect(url_for("configuracoes.index"))


@bp.route("/usuarios/<int:user_id>/status", methods=["POST"])
@login_required
def alternar_usuario(user_id):
    usuario = db.get_or_404(User, user_id)
    if usuario.id == current_user.id:
        flash("Você não pode inativar seu próprio usuário.", "warning")
        return redirect(url_for("configuracoes.index"))
    usuario.ativo = not usuario.ativo
    db.session.commit()
    flash("Status do usuário atualizado.", "success")
    return redirect(url_for("configuracoes.index"))
