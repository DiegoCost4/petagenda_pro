from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from sqlalchemy import or_
from app.extensions import db
from app.models import Tutor, PacoteCliente

bp = Blueprint("tutores", __name__, url_prefix="/tutores")


@bp.route("/")
@login_required
def index():
    q = request.args.get("q", "").strip()
    query = Tutor.query
    if q:
        like = f"%{q}%"
        query = query.filter(or_(Tutor.nome.ilike(like), Tutor.telefone.ilike(like), Tutor.email.ilike(like)))
    tutores = query.order_by(Tutor.nome).all()
    return render_template("tutores/index.html", tutores=tutores, q=q)


@bp.route("/novo", methods=["GET", "POST"])
@login_required
def novo():
    if request.method == "POST":
        tutor = Tutor(
            nome=request.form.get("nome", "").strip(),
            telefone=request.form.get("telefone", "").strip(),
            email=request.form.get("email", "").strip() or None,
            endereco=request.form.get("endereco", "").strip() or None,
            bairro=request.form.get("bairro", "").strip() or None,
            observacoes=request.form.get("observacoes", "").strip() or None,
            ativo=True,
        )
        if not tutor.nome or not tutor.telefone:
            flash("Nome e telefone são obrigatórios.", "warning")
            return render_template("tutores/form.html", tutor=tutor)
        db.session.add(tutor)
        db.session.commit()
        flash("Tutor cadastrado com sucesso.", "success")
        return redirect(url_for("tutores.detalhe", tutor_id=tutor.id))
    return render_template("tutores/form.html", tutor=None)


@bp.route("/<int:tutor_id>")
@login_required
def detalhe(tutor_id):
    tutor = db.get_or_404(Tutor, tutor_id)
    pacotes_cliente = (
        PacoteCliente.query
        .filter_by(tutor_id=tutor.id)
        .order_by(PacoteCliente.status, PacoteCliente.data_fim.desc())
        .all()
    )
    return render_template("tutores/detalhe.html", tutor=tutor, pacotes_cliente=pacotes_cliente)


@bp.route("/<int:tutor_id>/editar", methods=["GET", "POST"])
@login_required
def editar(tutor_id):
    tutor = db.get_or_404(Tutor, tutor_id)
    if request.method == "POST":
        tutor.nome = request.form.get("nome", "").strip()
        tutor.telefone = request.form.get("telefone", "").strip()
        tutor.email = request.form.get("email", "").strip() or None
        tutor.endereco = request.form.get("endereco", "").strip() or None
        tutor.bairro = request.form.get("bairro", "").strip() or None
        tutor.observacoes = request.form.get("observacoes", "").strip() or None
        tutor.ativo = bool(request.form.get("ativo"))
        if not tutor.nome or not tutor.telefone:
            flash("Nome e telefone são obrigatórios.", "warning")
            return render_template("tutores/form.html", tutor=tutor)
        db.session.commit()
        flash("Tutor atualizado com sucesso.", "success")
        return redirect(url_for("tutores.detalhe", tutor_id=tutor.id))
    return render_template("tutores/form.html", tutor=tutor)


@bp.route("/<int:tutor_id>/excluir", methods=["POST"])
@login_required
def excluir(tutor_id):
    tutor = db.get_or_404(Tutor, tutor_id)
    tutor.ativo = False
    db.session.commit()
    flash("Tutor inativado com sucesso.", "info")
    return redirect(url_for("tutores.index"))
