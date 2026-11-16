from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import json
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy import or_, update
from app.extensions import db
from app.models import HotelConfig, Hospedagem, HospedagemEvento, HospedagemPet, Tutor, Pet
from app.utils import FORMAS_PAGAMENTO

bp = Blueprint("hotel", __name__, url_prefix="/hotel")
CENT = Decimal("0.01")


def money(value):
    try:
        amount = Decimal(str(value).replace(",", "."))
        if not amount.is_finite() or amount < 0 or amount > Decimal("99999999.99"):
            raise ValueError
        return amount.quantize(CENT, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("Valor monetário inválido.")


def config():
    item = db.session.get(HotelConfig, 1)
    if not item:
        item = HotelConfig(id=1, diaria_padrao=Decimal("0"))
        db.session.add(item)
        db.session.flush()
    return item


def calcular(entrada, saida, diaria, quantidade_pets, desconto_percentual):
    if saida <= entrada or quantidade_pets < 1:
        raise ValueError("A saída deve ser posterior à entrada e ao menos um pet é necessário.")
    if desconto_percentual < 0 or desconto_percentual > 100:
        raise ValueError("O desconto deve ficar entre 0% e 100%.")
    diarias = (saida - entrada).days
    subtotal = (diaria * diarias * quantidade_pets).quantize(CENT)
    if subtotal > Decimal("9999999999.99"):
        raise ValueError("O total excede o limite permitido.")
    desconto = (subtotal * desconto_percentual / Decimal("100")).quantize(CENT, rounding=ROUND_HALF_UP)
    return diarias, subtotal, desconto, subtotal - desconto


def evento(hospedagem, acao, detalhes=None):
    db.session.add(HospedagemEvento(hospedagem_id=hospedagem.id, usuario_id=current_user.id, acao=acao, detalhes=detalhes))


def dados_form(hospedagem=None):
    try:
        tutor_id = int(request.form.get("tutor_id", ""))
        pet_ids = list(dict.fromkeys(int(x) for x in request.form.getlist("pet_ids")))
        entrada = date.fromisoformat(request.form.get("entrada", ""))
        saida = date.fromisoformat(request.form.get("saida", ""))
        diaria = money(request.form.get("diaria"))
        percentual = Decimal(str(request.form.get("desconto_percentual", "0")).replace(",", "."))
        if not percentual.is_finite() or percentual < 0 or percentual > 100:
            raise ValueError("Desconto inválido.")
        percentual = percentual.quantize(CENT, rounding=ROUND_HALF_UP)
    except (TypeError, ValueError, InvalidOperation):
        raise ValueError("Confira tutor, pets, datas, diária e desconto.")
    tutor = db.session.get(Tutor, tutor_id)
    pets = Pet.query.filter(Pet.id.in_(pet_ids)).with_for_update().all() if pet_ids else []
    if not tutor or not tutor.ativo or not pet_ids or len(pets) != len(pet_ids) or any(p.tutor_id != tutor_id or not p.ativo for p in pets):
        raise ValueError("Selecione pets ativos pertencentes ao tutor.")
    diarias, subtotal, desconto, total = calcular(entrada, saida, diaria, len(pets), percentual)
    conflitos = (Hospedagem.query.join(HospedagemPet)
        .filter(HospedagemPet.pet_id.in_(pet_ids), Hospedagem.status != "Cancelado",
                Hospedagem.entrada < saida, Hospedagem.saida > entrada))
    if hospedagem:
        conflitos = conflitos.filter(Hospedagem.id != hospedagem.id)
    if conflitos.first():
        raise ValueError("Um dos pets já tem hospedagem neste período.")
    return tutor, pets, entrada, saida, diaria, percentual, diarias, subtotal, desconto, total


@bp.route("/")
@login_required
def index():
    q = request.args.get("q", "").strip()
    inicio = request.args.get("inicio", "")
    fim = request.args.get("fim", "")
    query = Hospedagem.query.join(Tutor)
    if q:
        query = query.filter(or_(Tutor.nome.ilike(f"%{q}%"), Hospedagem.pets.any(Pet.nome.ilike(f"%{q}%"))))
    try:
        if inicio:
            query = query.filter(Hospedagem.saida > date.fromisoformat(inicio))
        if fim:
            query = query.filter(Hospedagem.entrada <= date.fromisoformat(fim))
    except ValueError:
        flash("Filtro de data inválido.", "warning")
    hospedagens = query.order_by(Hospedagem.entrada.desc(), Hospedagem.id.desc()).limit(200).all()
    hoje = date.today()
    hospedados = Hospedagem.query.filter(Hospedagem.status == "Hospedado").all()
    entradas = Hospedagem.query.filter(Hospedagem.entrada == hoje, Hospedagem.status == "Agendado").all()
    saidas = Hospedagem.query.filter(Hospedagem.saida == hoje, Hospedagem.status == "Hospedado").all()
    return render_template("hotel/index.html", hospedagens=hospedagens, hospedados=hospedados, entradas=entradas, saidas=saidas, q=q, inicio=inicio, fim=fim)


def form_context(hospedagem=None):
    tutores = Tutor.query.filter_by(ativo=True).order_by(Tutor.nome).all()
    tutor_id = request.form.get("tutor_id", type=int) if request.method == "POST" else (hospedagem.tutor_id if hospedagem else None)
    pets = Pet.query.filter_by(tutor_id=tutor_id, ativo=True).order_by(Pet.nome).all() if tutor_id else []
    return dict(hospedagem=hospedagem, tutores=tutores, pets=pets, selecionados=request.form.getlist("pet_ids", type=int) if request.method == "POST" else ([p.id for p in hospedagem.pets] if hospedagem else []), diaria_padrao=config().diaria_padrao)


@bp.route("/novo", methods=["GET", "POST"])
@login_required
def novo():
    if request.method == "POST":
        try:
            tutor, pets, entrada, saida, diaria, percentual, diarias, subtotal, desconto, total = dados_form()
            item = Hospedagem(tutor=tutor, pets=pets, entrada=entrada, saida=saida, diaria=diaria,
                desconto_percentual=percentual, diarias=diarias, subtotal=subtotal,
                desconto_valor=desconto, total=total, observacoes=request.form.get("observacoes", "").strip())
            db.session.add(item)
            db.session.flush()
            evento(item, "Criado")
            db.session.commit()
            flash("Hospedagem agendada.", "success")
            return redirect(url_for("hotel.detalhe", hospedagem_id=item.id))
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "warning")
    return render_template("hotel/form.html", **form_context())


@bp.route("/<int:hospedagem_id>")
@login_required
def detalhe(hospedagem_id):
    item = db.get_or_404(Hospedagem, hospedagem_id)
    eventos = HospedagemEvento.query.filter_by(hospedagem_id=item.id).order_by(HospedagemEvento.ocorrido_em.desc()).all()
    return render_template("hotel/detalhe.html", item=item, eventos=eventos,
                           formas=[forma for forma in FORMAS_PAGAMENTO if forma != "Pacote"], hoje=date.today())


@bp.route("/<int:hospedagem_id>/editar", methods=["GET", "POST"])
@login_required
def editar(hospedagem_id):
    item = db.get_or_404(Hospedagem, hospedagem_id)
    if item.status != "Agendado" or item.pago:
        flash("Só hospedagens agendadas e pendentes podem ser editadas.", "warning")
        return redirect(url_for("hotel.detalhe", hospedagem_id=item.id))
    if request.method == "POST":
        try:
            tutor, pets, entrada, saida, diaria, percentual, diarias, subtotal, desconto, total = dados_form(item)
            anterior = {"tutor_id": item.tutor_id, "pet_ids": [p.id for p in item.pets], "entrada": item.entrada.isoformat(), "saida": item.saida.isoformat(), "diaria": str(item.diaria), "desconto_percentual": str(item.desconto_percentual), "total": str(item.total)}
            novo = {"tutor_id": tutor.id, "pet_ids": [p.id for p in pets], "entrada": entrada.isoformat(), "saida": saida.isoformat(), "diaria": str(diaria), "desconto_percentual": str(percentual), "total": str(total)}
            item.tutor, item.pets, item.entrada, item.saida = tutor, pets, entrada, saida
            item.diaria, item.desconto_percentual, item.diarias = diaria, percentual, diarias
            item.subtotal, item.desconto_valor, item.total = subtotal, desconto, total
            item.observacoes = request.form.get("observacoes", "").strip()
            db.session.flush()
            evento(item, "Editado", json.dumps({"antes": anterior, "depois": novo}, ensure_ascii=False))
            db.session.commit()
            flash("Hospedagem atualizada.", "success")
            return redirect(url_for("hotel.detalhe", hospedagem_id=item.id))
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "warning")
    return render_template("hotel/form.html", **form_context(item))


@bp.route("/<int:hospedagem_id>/status", methods=["POST"])
@login_required
def status(hospedagem_id):
    item = db.get_or_404(Hospedagem, hospedagem_id)
    acao = request.form.get("acao")
    transicoes = {("Agendado", "checkin"): "Hospedado", ("Hospedado", "checkout"): "Finalizado", ("Agendado", "cancelar"): "Cancelado"}
    novo_status = transicoes.get((item.status, acao))
    if acao == "cancelar" and item.pago:
        flash("Estorne o pagamento antes de cancelar a hospedagem.", "warning")
        return redirect(url_for("hotel.detalhe", hospedagem_id=item.id))
    if not novo_status:
        flash("Transição de status inválida.", "warning")
    else:
        changes = {"status": novo_status}
        if acao == "checkin":
            changes["checkin_em"] = datetime.utcnow()
        elif acao == "checkout":
            changes["checkout_em"] = datetime.utcnow()
        result = db.session.execute(update(Hospedagem).where(Hospedagem.id == item.id, Hospedagem.status == item.status).values(**changes))
        if result.rowcount != 1:
            db.session.rollback()
            flash("Outro usuário já alterou esta hospedagem.", "warning")
        else:
            evento(item, novo_status)
            db.session.commit()
            flash("Status atualizado.", "success")
    return redirect(url_for("hotel.detalhe", hospedagem_id=item.id))


@bp.route("/<int:hospedagem_id>/pagar", methods=["POST"])
@login_required
def pagar(hospedagem_id):
    item = db.get_or_404(Hospedagem, hospedagem_id)
    forma = request.form.get("forma_pagamento", "").strip()
    try:
        data_pagamento = date.fromisoformat(request.form.get("data_pagamento", ""))
    except (TypeError, ValueError):
        data_pagamento = None
    if item.status == "Cancelado" or item.pago or forma not in FORMAS_PAGAMENTO or forma == "Pacote" or not data_pagamento:
        flash("Confira o status, a data e a forma de pagamento.", "warning")
    else:
        item.pago = True
        item.forma_pagamento = forma
        item.data_pagamento = data_pagamento
        evento(item, "Pagamento registrado", f"{item.total} · {forma} · {data_pagamento.isoformat()}")
        db.session.commit()
        flash("Pagamento da hospedagem registrado.", "success")
    return redirect(url_for("hotel.detalhe", hospedagem_id=item.id))


@bp.route("/<int:hospedagem_id>/estornar", methods=["POST"])
@login_required
def estornar(hospedagem_id):
    item = db.get_or_404(Hospedagem, hospedagem_id)
    if item.pago:
        evento(item, "Pagamento estornado", f"{item.total} · {item.forma_pagamento} · {item.data_pagamento}")
        item.pago = False
        item.forma_pagamento = None
        item.data_pagamento = None
        db.session.commit()
        flash("Pagamento da hospedagem estornado.", "info")
    return redirect(url_for("hotel.detalhe", hospedagem_id=item.id))


@bp.route("/configuracoes", methods=["GET", "POST"])
@login_required
def configuracoes():
    item = config()
    if request.method == "POST":
        try:
            item.diaria_padrao = money(request.form.get("diaria_padrao"))
            db.session.commit()
            flash("Diária padrão atualizada.", "success")
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "warning")
    return render_template("hotel/configuracoes.html", config=item)
