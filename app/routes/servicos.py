from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from app.extensions import db
from app.models import Servico, Pacote
from app.utils import PORTES

bp = Blueprint("servicos", __name__, url_prefix="/servicos")


def duracao_from_form():
    valor = request.form.get("duracao_minutos", "").strip()
    if not valor:
        return 0
    try:
        duracao = int(valor)
    except ValueError:
        return None
    return duracao if duracao >= 0 else None


@bp.route("/")
@login_required
def index():
    servicos = Servico.query.order_by(Servico.nome, Servico.porte).all()
    pacotes = Pacote.query.order_by(Pacote.ativo.desc(), Pacote.nome).all()
    return render_template("servicos/index.html", servicos=servicos, pacotes=pacotes)


@bp.route("/novo", methods=["GET", "POST"])
@login_required
def novo():
    if request.method == "POST":
        servico = Servico(
            nome=request.form.get("nome", "").strip(),
            porte=request.form.get("porte", "Pequeno"),
            duracao_minutos=duracao_from_form(),
            valor=request.form.get("valor", type=float),
            observacoes=request.form.get("observacoes", "").strip() or None,
            ativo=True,
        )
        if not servico.nome or servico.valor is None:
            flash("Nome e valor são obrigatórios.", "warning")
            return render_template("servicos/form.html", servico=servico, portes=PORTES)
        if servico.duracao_minutos is None:
            flash("Informe uma duração inteira maior ou igual a zero, ou deixe em branco.", "warning")
            return render_template("servicos/form.html", servico=servico, portes=PORTES)
        db.session.add(servico)
        db.session.commit()
        flash("Serviço cadastrado com sucesso.", "success")
        return redirect(url_for("servicos.index"))
    return render_template("servicos/form.html", servico=None, portes=PORTES)


@bp.route("/<int:servico_id>/editar", methods=["GET", "POST"])
@login_required
def editar(servico_id):
    servico = db.get_or_404(Servico, servico_id)
    if request.method == "POST":
        servico.nome = request.form.get("nome", "").strip()
        servico.porte = request.form.get("porte", "Pequeno")
        duracao = duracao_from_form()
        if duracao is None:
            flash("Informe uma duração inteira maior ou igual a zero, ou deixe em branco.", "warning")
            return render_template("servicos/form.html", servico=servico, portes=PORTES)
        servico.duracao_minutos = duracao
        servico.valor = request.form.get("valor", type=float)
        servico.observacoes = request.form.get("observacoes", "").strip() or None
        servico.ativo = bool(request.form.get("ativo"))
        if not servico.nome or servico.valor is None:
            flash("Nome e valor são obrigatórios.", "warning")
            return render_template("servicos/form.html", servico=servico, portes=PORTES)
        db.session.commit()
        flash("Serviço atualizado com sucesso.", "success")
        return redirect(url_for("servicos.index"))
    return render_template("servicos/form.html", servico=servico, portes=PORTES)


@bp.route("/<int:servico_id>/excluir", methods=["POST"])
@login_required
def excluir(servico_id):
    servico = db.get_or_404(Servico, servico_id)
    servico.ativo = False
    db.session.commit()
    flash("Serviço inativado com sucesso.", "info")
    return redirect(url_for("servicos.index"))
