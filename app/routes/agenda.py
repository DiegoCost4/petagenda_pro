from datetime import datetime, date, timedelta
from decimal import Decimal
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required
from app.extensions import db
from app.models import Agendamento, AgendamentoServico, Tutor, Pet, Servico, BloqueioAgenda, Pagamento, PacoteCliente, UsoPacote
from app.utils import (
    STATUS_AGENDAMENTO,
    FORMAS_PAGAMENTO,
    add_minutes_to_time,
    has_conflict,
    validate_inside_business_hours,
    generate_available_slots,
    whatsapp_url,
)

bp = Blueprint("agenda", __name__, url_prefix="/agenda")


def parse_date_or_today(value):
    if not value:
        return date.today()
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return date.today()


def render_agendamento_form(agendamento, tutores, servicos, data_padrao, selected_servico_ids=None):
    if selected_servico_ids is None:
        selected_servico_ids = agendamento.servico_ids if agendamento else []
    return render_template(
        "agenda/form.html",
        agendamento=agendamento,
        tutores=tutores,
        servicos=servicos,
        formas=FORMAS_PAGAMENTO,
        data_padrao=data_padrao,
        pacote_atual=agendamento.pacote_cliente if agendamento else None,
        selected_servico_ids=selected_servico_ids,
    )


def servicos_from_form():
    servico_ids = request.form.getlist("servico_ids", type=int)
    legado_id = request.form.get("servico_id", type=int)
    if legado_id and legado_id not in servico_ids:
        servico_ids.insert(0, legado_id)

    ids_unicos = []
    for servico_id in servico_ids:
        if servico_id and servico_id not in ids_unicos:
            ids_unicos.append(servico_id)
    if not ids_unicos:
        return []

    encontrados = Servico.query.filter(Servico.id.in_(ids_unicos), Servico.ativo.is_(True)).all()
    por_id = {servico.id: servico for servico in encontrados}
    return [por_id[servico_id] for servico_id in ids_unicos if servico_id in por_id]


def parse_servico_ids_query():
    servico_ids = request.args.getlist("servico_ids", type=int)
    servico_ids.extend(request.args.getlist("servico_id", type=int))
    raw_ids = request.args.get("servico_ids", "")
    for raw_id in raw_ids.split(","):
        try:
            servico_ids.append(int(raw_id))
        except (TypeError, ValueError):
            pass

    ids_unicos = []
    for servico_id in servico_ids:
        if servico_id and servico_id not in ids_unicos:
            ids_unicos.append(servico_id)
    return ids_unicos


def calcular_valor_servicos(servicos):
    return sum((Decimal(servico.valor or 0) for servico in servicos), Decimal("0"))


def calcular_duracao_servicos(servicos):
    return sum((servico.duracao_minutos or 0) for servico in servicos)


def calcular_valor_cobrado(servicos, pacote_cliente=None):
    total = calcular_valor_servicos(servicos)
    if not pacote_cliente:
        return total
    valor_coberto = next(
        (Decimal(servico.valor or 0) for servico in servicos if servico.id == pacote_cliente.pacote.servico_id),
        Decimal("0"),
    )
    return max(total - valor_coberto, Decimal("0"))


def sincronizar_servicos_agendamento(agendamento, servicos):
    agendamento.servicos_itens = [
        AgendamentoServico(
            servico_id=servico.id,
            ordem=ordem,
            valor=Decimal(servico.valor or 0),
            duracao_minutos=servico.duracao_minutos,
        )
        for ordem, servico in enumerate(servicos)
    ]


def validar_pacote_agendamento(pacote_cliente_id, tutor_id, pet_id, servico_ids, data_agendamento, ignore_agendamento_id=None):
    if not pacote_cliente_id:
        return None, None
    pacote_cliente = db.session.get(PacoteCliente, pacote_cliente_id)
    if not pacote_cliente:
        return None, "Selecione um pacote válido."
    if pacote_cliente.tutor_id != tutor_id or pacote_cliente.pet_id != pet_id:
        return None, "O pacote selecionado não pertence ao tutor e pet informados."
    if pacote_cliente.pacote.servico_id not in servico_ids:
        return None, "O pacote selecionado não cobre nenhum dos serviços escolhidos."
    if not pacote_cliente.pode_consumir(pacote_cliente.pacote.servico_id, data_agendamento, ignore_agendamento_id):
        return None, "O pacote selecionado não tem saldo, validade ou serviço compatível."
    return pacote_cliente, None


def validar_pet_tutor(tutor_id, pet_id):
    pet = db.session.get(Pet, pet_id)
    if not pet or not pet.ativo or pet.tutor_id != tutor_id:
        return "Selecione um pet válido para o tutor informado."
    return None


def sincronizar_uso_pacote(agendamento, pacote_cliente):
    if not pacote_cliente:
        if agendamento.pacote_uso:
            db.session.delete(agendamento.pacote_uso)
        return
    if agendamento.pacote_uso:
        agendamento.pacote_uso.pacote_cliente_id = pacote_cliente.id
        agendamento.pacote_uso.data_consumo = agendamento.data
        agendamento.pacote_uso.quantidade = 1
    else:
        db.session.add(UsoPacote(
            pacote_cliente_id=pacote_cliente.id,
            agendamento_id=agendamento.id,
            data_consumo=agendamento.data,
            quantidade=1,
        ))


def sincronizar_pagamento_agendamento(agendamento, data_pagamento, pacote_cliente=None):
    if pacote_cliente and Decimal(agendamento.valor or 0) <= 0:
        agendamento.valor = Decimal("0")
        agendamento.forma_pagamento = "Pacote"
        agendamento.pago = True
        if agendamento.pagamento:
            db.session.delete(agendamento.pagamento)
        return

    if pacote_cliente and agendamento.forma_pagamento == "Pacote":
        agendamento.forma_pagamento = None

    if agendamento.pago:
        if agendamento.pagamento:
            agendamento.pagamento.valor = agendamento.valor
            agendamento.pagamento.forma_pagamento = agendamento.forma_pagamento or "Pix"
            agendamento.pagamento.data_pagamento = data_pagamento
        else:
            db.session.add(Pagamento(
                agendamento_id=agendamento.id,
                valor=agendamento.valor,
                forma_pagamento=agendamento.forma_pagamento or "Pix",
                status="Pago",
                data_pagamento=data_pagamento,
            ))
    elif agendamento.pagamento:
        db.session.delete(agendamento.pagamento)


@bp.route("/")
@login_required
def index():
    data_ref = parse_date_or_today(request.args.get("data"))
    status = request.args.get("status", "").strip()
    query = Agendamento.query.filter_by(data=data_ref)
    if status:
        query = query.filter_by(status=status)
    agendamentos = query.order_by(Agendamento.hora_inicio).all()
    bloqueios = BloqueioAgenda.query.filter_by(data=data_ref).order_by(BloqueioAgenda.hora_inicio).all()
    return render_template(
        "agenda/index.html",
        data_ref=data_ref,
        agendamentos=agendamentos,
        bloqueios=bloqueios,
        status_options=STATUS_AGENDAMENTO,
        status=status,
        ontem=data_ref - timedelta(days=1),
        amanha=data_ref + timedelta(days=1),
    )


@bp.route("/novo", methods=["GET", "POST"])
@login_required
def novo():
    tutores = Tutor.query.filter_by(ativo=True).order_by(Tutor.nome).all()
    servicos = Servico.query.filter_by(ativo=True).order_by(Servico.nome, Servico.porte).all()
    data_padrao = request.args.get("data", date.today().strftime("%Y-%m-%d"))

    if request.method == "POST":
        data_agendamento = parse_date_or_today(request.form.get("data"))
        servicos_selecionados = servicos_from_form()
        selected_servico_ids = [servico.id for servico in servicos_selecionados]
        if not servicos_selecionados:
            flash("Selecione um serviço válido.", "warning")
            return render_agendamento_form(None, tutores, servicos, data_padrao, selected_servico_ids)

        hora_inicio = request.form.get("hora_inicio", "").strip()
        duracao_total = calcular_duracao_servicos(servicos_selecionados)
        hora_fim = add_minutes_to_time(hora_inicio, duracao_total) if hora_inicio else ""
        tutor_id = request.form.get("tutor_id", type=int)
        pet_id = request.form.get("pet_id", type=int)
        pacote_cliente_id = request.form.get("pacote_cliente_id", type=int)
        valor = request.form.get("valor", type=float)

        if not tutor_id or not pet_id or not hora_inicio:
            flash("Tutor, pet e horário são obrigatórios.", "warning")
            return render_agendamento_form(None, tutores, servicos, data_agendamento.strftime("%Y-%m-%d"), selected_servico_ids)

        pet_error = validar_pet_tutor(tutor_id, pet_id)
        if pet_error:
            flash(pet_error, "warning")
            return render_agendamento_form(None, tutores, servicos, data_agendamento.strftime("%Y-%m-%d"), selected_servico_ids)

        pacote_cliente, pacote_error = validar_pacote_agendamento(
            pacote_cliente_id,
            tutor_id,
            pet_id,
            selected_servico_ids,
            data_agendamento,
        )
        if pacote_error:
            flash(pacote_error, "warning")
            return render_agendamento_form(None, tutores, servicos, data_agendamento.strftime("%Y-%m-%d"), selected_servico_ids)

        inside, message = validate_inside_business_hours(data_agendamento, hora_inicio, hora_fim)
        if not inside:
            flash(message, "warning")
            return render_agendamento_form(None, tutores, servicos, data_agendamento.strftime("%Y-%m-%d"), selected_servico_ids)

        if has_conflict(data_agendamento, hora_inicio, hora_fim):
            flash("Já existe agendamento ou bloqueio neste intervalo.", "danger")
            return render_agendamento_form(None, tutores, servicos, data_agendamento.strftime("%Y-%m-%d"), selected_servico_ids)

        servico_principal_id = pacote_cliente.pacote.servico_id if pacote_cliente else selected_servico_ids[0]
        valor_cobrado = calcular_valor_cobrado(servicos_selecionados, pacote_cliente)
        valor_final = Decimal(str(valor)) if valor is not None else valor_cobrado
        agendamento = Agendamento(
            tutor_id=tutor_id,
            pet_id=pet_id,
            servico_id=servico_principal_id,
            data=data_agendamento,
            hora_inicio=hora_inicio,
            hora_fim=hora_fim,
            valor=valor_final,
            status=request.form.get("status") or "Agendado",
            forma_pagamento="Pacote" if pacote_cliente and valor_final <= 0 else (request.form.get("forma_pagamento") or None),
            pago=True if pacote_cliente and valor_final <= 0 else bool(request.form.get("pago")),
            observacoes=request.form.get("observacoes", "").strip() or None,
        )
        db.session.add(agendamento)
        sincronizar_servicos_agendamento(agendamento, servicos_selecionados)
        db.session.flush()
        sincronizar_uso_pacote(agendamento, pacote_cliente)
        sincronizar_pagamento_agendamento(agendamento, data_agendamento, pacote_cliente)
        db.session.commit()
        flash("Agendamento criado com sucesso.", "success")
        return redirect(url_for("agenda.detalhe", agendamento_id=agendamento.id))

    return render_agendamento_form(None, tutores, servicos, data_padrao)


@bp.route("/<int:agendamento_id>")
@login_required
def detalhe(agendamento_id):
    agendamento = db.get_or_404(Agendamento, agendamento_id)
    msg_confirmacao = whatsapp_url(agendamento.tutor.telefone, agendamento.whatsapp_confirmacao)
    msg_pronto = whatsapp_url(agendamento.tutor.telefone, agendamento.whatsapp_pronto)
    return render_template("agenda/detalhe.html", agendamento=agendamento, status_options=STATUS_AGENDAMENTO, msg_confirmacao=msg_confirmacao, msg_pronto=msg_pronto)


@bp.route("/<int:agendamento_id>/editar", methods=["GET", "POST"])
@login_required
def editar(agendamento_id):
    agendamento = db.get_or_404(Agendamento, agendamento_id)
    tutores = Tutor.query.filter_by(ativo=True).order_by(Tutor.nome).all()
    servicos = Servico.query.filter_by(ativo=True).order_by(Servico.nome, Servico.porte).all()

    if request.method == "POST":
        servicos_selecionados = servicos_from_form()
        selected_servico_ids = [servico.id for servico in servicos_selecionados]
        if not servicos_selecionados:
            flash("Selecione um serviço válido.", "warning")
            return render_agendamento_form(agendamento, tutores, servicos, agendamento.data.strftime("%Y-%m-%d"), selected_servico_ids)
        data_agendamento = parse_date_or_today(request.form.get("data"))
        hora_inicio = request.form.get("hora_inicio", "").strip()
        duracao_total = calcular_duracao_servicos(servicos_selecionados)
        hora_fim = add_minutes_to_time(hora_inicio, duracao_total) if hora_inicio else ""
        tutor_id = request.form.get("tutor_id", type=int)
        pet_id = request.form.get("pet_id", type=int)
        pacote_cliente_id = request.form.get("pacote_cliente_id", type=int)
        valor = request.form.get("valor", type=float)

        if not tutor_id or not pet_id or not hora_inicio:
            flash("Tutor, pet e horário são obrigatórios.", "warning")
            return render_agendamento_form(agendamento, tutores, servicos, data_agendamento.strftime("%Y-%m-%d"), selected_servico_ids)

        pet_error = validar_pet_tutor(tutor_id, pet_id)
        if pet_error:
            flash(pet_error, "warning")
            return render_agendamento_form(agendamento, tutores, servicos, data_agendamento.strftime("%Y-%m-%d"), selected_servico_ids)

        pacote_cliente, pacote_error = validar_pacote_agendamento(
            pacote_cliente_id,
            tutor_id,
            pet_id,
            selected_servico_ids,
            data_agendamento,
            ignore_agendamento_id=agendamento.id,
        )
        if pacote_error:
            flash(pacote_error, "warning")
            return render_agendamento_form(agendamento, tutores, servicos, data_agendamento.strftime("%Y-%m-%d"), selected_servico_ids)

        inside, message = validate_inside_business_hours(data_agendamento, hora_inicio, hora_fim)
        if not inside:
            flash(message, "warning")
            return render_agendamento_form(agendamento, tutores, servicos, data_agendamento.strftime("%Y-%m-%d"), selected_servico_ids)
        if has_conflict(data_agendamento, hora_inicio, hora_fim, ignore_id=agendamento.id):
            flash("Já existe agendamento ou bloqueio neste intervalo.", "danger")
            return render_agendamento_form(agendamento, tutores, servicos, data_agendamento.strftime("%Y-%m-%d"), selected_servico_ids)

        agendamento.tutor_id = tutor_id
        agendamento.pet_id = pet_id
        servico_principal_id = pacote_cliente.pacote.servico_id if pacote_cliente else selected_servico_ids[0]
        valor_cobrado = calcular_valor_cobrado(servicos_selecionados, pacote_cliente)
        valor_final = Decimal(str(valor)) if valor is not None else valor_cobrado

        agendamento.servico_id = servico_principal_id
        agendamento.data = data_agendamento
        agendamento.hora_inicio = hora_inicio
        agendamento.hora_fim = hora_fim
        agendamento.valor = valor_final
        agendamento.status = request.form.get("status") or agendamento.status
        agendamento.forma_pagamento = "Pacote" if pacote_cliente and valor_final <= 0 else (request.form.get("forma_pagamento") or None)
        agendamento.pago = True if pacote_cliente and valor_final <= 0 else bool(request.form.get("pago"))
        agendamento.observacoes = request.form.get("observacoes", "").strip() or None
        sincronizar_servicos_agendamento(agendamento, servicos_selecionados)
        sincronizar_uso_pacote(agendamento, pacote_cliente)
        sincronizar_pagamento_agendamento(agendamento, data_agendamento, pacote_cliente)
        db.session.commit()
        flash("Agendamento atualizado com sucesso.", "success")
        return redirect(url_for("agenda.detalhe", agendamento_id=agendamento.id))

    return render_agendamento_form(agendamento, tutores, servicos, agendamento.data.strftime("%Y-%m-%d"))


@bp.route("/<int:agendamento_id>/status", methods=["POST"])
@login_required
def status(agendamento_id):
    agendamento = db.get_or_404(Agendamento, agendamento_id)
    novo_status = request.form.get("status")
    if novo_status not in STATUS_AGENDAMENTO:
        flash("Status inválido.", "warning")
    else:
        agendamento.status = novo_status
        db.session.commit()
        flash("Status atualizado.", "success")
    return redirect(request.referrer or url_for("agenda.detalhe", agendamento_id=agendamento.id))


@bp.route("/<int:agendamento_id>/excluir", methods=["POST"])
@login_required
def excluir(agendamento_id):
    agendamento = db.get_or_404(Agendamento, agendamento_id)
    db.session.delete(agendamento)
    db.session.commit()
    flash("Agendamento excluído.", "info")
    return redirect(url_for("agenda.index", data=agendamento.data.strftime("%Y-%m-%d")))


@bp.route("/api/pets")
@login_required
def api_pets():
    tutor_id = request.args.get("tutor_id", type=int)
    pets = Pet.query.filter_by(tutor_id=tutor_id, ativo=True).order_by(Pet.nome).all() if tutor_id else []
    return jsonify([{"id": p.id, "nome": p.nome, "porte": p.porte} for p in pets])


@bp.route("/api/pacotes")
@login_required
def api_pacotes():
    tutor_id = request.args.get("tutor_id", type=int)
    pet_id = request.args.get("pet_id", type=int)
    servico_ids = parse_servico_ids_query()
    agendamento_id = request.args.get("agendamento_id", type=int)
    data_ref = parse_date_or_today(request.args.get("data"))
    if not tutor_id or not pet_id or not servico_ids:
        return jsonify([])

    pacotes = (
        PacoteCliente.query
        .join(PacoteCliente.pacote)
        .filter(
            PacoteCliente.tutor_id == tutor_id,
            PacoteCliente.pet_id == pet_id,
            PacoteCliente.status == "Ativo",
            PacoteCliente.data_inicio <= data_ref,
            PacoteCliente.data_fim >= data_ref,
        )
        .order_by(PacoteCliente.data_fim, PacoteCliente.id)
        .all()
    )

    agendamento = db.session.get(Agendamento, agendamento_id) if agendamento_id else None
    pacote_atual_id = agendamento.pacote_cliente.id if agendamento and agendamento.pacote_cliente else None
    if pacote_atual_id and all(item.id != pacote_atual_id for item in pacotes):
        pacotes.append(agendamento.pacote_cliente)

    resposta = []
    for pacote_cliente in pacotes:
        if not pacote_cliente.pacote.ativo or pacote_cliente.pacote.servico_id not in servico_ids:
            continue
        saldo = pacote_cliente.saldo_disponivel(ignore_agendamento_id=agendamento_id)
        if saldo <= 0 and pacote_cliente.id != pacote_atual_id:
            continue
        resposta.append({
            "id": pacote_cliente.id,
            "nome": pacote_cliente.pacote.nome,
            "pet": pacote_cliente.pet.nome,
            "tutor": pacote_cliente.tutor.nome,
            "servico_id": pacote_cliente.pacote.servico_id,
            "servico_nome": pacote_cliente.pacote.servico.nome,
            "saldo": saldo,
            "total": pacote_cliente.quantidade_total,
            "data_fim": pacote_cliente.data_fim.strftime("%d/%m/%Y"),
            "atual": pacote_cliente.id == pacote_atual_id,
        })
    return jsonify(resposta)


@bp.route("/api/servico/<int:servico_id>")
@login_required
def api_servico(servico_id):
    servico = db.get_or_404(Servico, servico_id)
    return jsonify({"id": servico.id, "valor": float(servico.valor), "duracao_minutos": servico.duracao_minutos})


@bp.route("/api/horarios")
@login_required
def api_horarios():
    data_ref = parse_date_or_today(request.args.get("data"))
    duracao_minutos = request.args.get("duracao_minutos", type=int) or request.args.get("duracao", type=int)
    if not duracao_minutos:
        servico_ids = parse_servico_ids_query()
        servicos = Servico.query.filter(Servico.id.in_(servico_ids), Servico.ativo.is_(True)).all() if servico_ids else []
        duracao_minutos = calcular_duracao_servicos(servicos)
    if not duracao_minutos:
        return jsonify([])
    slots = generate_available_slots(data_ref, duracao_minutos)
    return jsonify(slots)
