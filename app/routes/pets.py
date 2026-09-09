from pathlib import Path
from uuid import uuid4
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required
from sqlalchemy import or_
from werkzeug.utils import secure_filename
from app.extensions import db
from app.models import Pet, Tutor, PacoteCliente
from app.utils import PORTES, ESPECIES

bp = Blueprint("pets", __name__, url_prefix="/pets")

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}


def save_photo(file_storage):
    if not file_storage or not file_storage.filename:
        return None
    ext = file_storage.filename.rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        flash("Formato de foto inválido. Use PNG, JPG, JPEG ou WEBP.", "warning")
        return None
    filename = secure_filename(f"{uuid4().hex}.{ext}")
    upload_dir = Path(current_app.config["UPLOAD_FOLDER"])
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_storage.save(upload_dir / filename)
    return f"uploads/{filename}"


@bp.route("/")
@login_required
def index():
    q = request.args.get("q", "").strip()
    query = Pet.query.join(Tutor)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(Pet.nome.ilike(like), Pet.raca.ilike(like), Tutor.nome.ilike(like)))
    pets = query.order_by(Pet.nome).all()
    return render_template("pets/index.html", pets=pets, q=q)


@bp.route("/novo", methods=["GET", "POST"])
@login_required
def novo():
    tutor_id = request.args.get("tutor_id", type=int)
    tutores = Tutor.query.filter_by(ativo=True).order_by(Tutor.nome).all()
    if request.method == "POST":
        foto = save_photo(request.files.get("foto"))
        pet = Pet(
            tutor_id=request.form.get("tutor_id", type=int),
            nome=request.form.get("nome", "").strip(),
            especie=request.form.get("especie", "Cachorro"),
            raca=request.form.get("raca", "").strip() or None,
            porte=request.form.get("porte", "Pequeno"),
            sexo=request.form.get("sexo", "").strip() or None,
            idade=request.form.get("idade", "").strip() or None,
            peso=request.form.get("peso", "").strip() or None,
            foto=foto,
            observacoes=request.form.get("observacoes", "").strip() or None,
            restricoes=request.form.get("restricoes", "").strip() or None,
            ativo=True,
        )
        if not pet.tutor_id or not pet.nome or not pet.porte:
            flash("Tutor, nome do pet e porte são obrigatórios.", "warning")
            return render_template("pets/form.html", pet=pet, tutores=tutores, portes=PORTES, especies=ESPECIES)
        db.session.add(pet)
        db.session.commit()
        flash("Pet cadastrado com sucesso.", "success")
        return redirect(url_for("pets.detalhe", pet_id=pet.id))
    pet = Pet(tutor_id=tutor_id) if tutor_id else None
    return render_template("pets/form.html", pet=pet, tutores=tutores, portes=PORTES, especies=ESPECIES)


@bp.route("/<int:pet_id>")
@login_required
def detalhe(pet_id):
    pet = db.get_or_404(Pet, pet_id)
    pacotes_cliente = (
        PacoteCliente.query
        .filter_by(pet_id=pet.id)
        .order_by(PacoteCliente.status, PacoteCliente.data_fim.desc())
        .all()
    )
    return render_template("pets/detalhe.html", pet=pet, pacotes_cliente=pacotes_cliente)


@bp.route("/<int:pet_id>/editar", methods=["GET", "POST"])
@login_required
def editar(pet_id):
    pet = db.get_or_404(Pet, pet_id)
    tutores = Tutor.query.filter_by(ativo=True).order_by(Tutor.nome).all()
    if request.method == "POST":
        pet.tutor_id = request.form.get("tutor_id", type=int)
        pet.nome = request.form.get("nome", "").strip()
        pet.especie = request.form.get("especie", "Cachorro")
        pet.raca = request.form.get("raca", "").strip() or None
        pet.porte = request.form.get("porte", "Pequeno")
        pet.sexo = request.form.get("sexo", "").strip() or None
        pet.idade = request.form.get("idade", "").strip() or None
        pet.peso = request.form.get("peso", "").strip() or None
        pet.observacoes = request.form.get("observacoes", "").strip() or None
        pet.restricoes = request.form.get("restricoes", "").strip() or None
        pet.ativo = bool(request.form.get("ativo"))
        foto = save_photo(request.files.get("foto"))
        if foto:
            pet.foto = foto
        if not pet.tutor_id or not pet.nome or not pet.porte:
            flash("Tutor, nome do pet e porte são obrigatórios.", "warning")
            return render_template("pets/form.html", pet=pet, tutores=tutores, portes=PORTES, especies=ESPECIES)
        db.session.commit()
        flash("Pet atualizado com sucesso.", "success")
        return redirect(url_for("pets.detalhe", pet_id=pet.id))
    return render_template("pets/form.html", pet=pet, tutores=tutores, portes=PORTES, especies=ESPECIES)


@bp.route("/<int:pet_id>/excluir", methods=["POST"])
@login_required
def excluir(pet_id):
    pet = db.get_or_404(Pet, pet_id)
    pet.ativo = False
    db.session.commit()
    flash("Pet inativado com sucesso.", "info")
    return redirect(url_for("pets.index"))
