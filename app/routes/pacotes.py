from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy.exc import IntegrityError
from sqlalchemy import or_
from app.extensions import db
from app.models import Pacote, PacoteCliente, Tutor, Pet, Servico, UsoPacote, Agendamento, RenovacaoPacote
from app.package_cycles import decidir, pendencias, proximo_aniversario
from app.utils import FORMAS_PAGAMENTO, STATUS_PACOTE_CLIENTE

bp = Blueprint("pacotes", __name__, url_prefix="/pacotes")


def parse_date(value, default=None):
    if not value:
        return default
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return default


def parse_decimal(value, default=Decimal("0")):
    value = (value or "").strip().replace(",", ".")
    if not value:
        return default
    try:
        amount = Decimal(value)
        return amount if amount.is_finite() else Decimal("-1")
    except InvalidOperation:
        return Decimal("-1")


def render_pacote_form(pacote=None):
    servicos = Servico.query.filter_by(ativo=True).order_by(Servico.nome, Servico.porte).all()
    return render_template("pacotes/form.html", pacote=pacote, servicos=servicos)


def cliente_form_context(pacote_cliente=None):
    tutores = Tutor.query.filter_by(ativo=True).order_by(Tutor.nome).all()
    pacotes_query = Pacote.query.filter(Pacote.ativo.is_(True))
    if pacote_cliente and pacote_cliente.pacote_id:
        pacotes_query = Pacote.query.filter(or_(Pacote.ativo.is_(True), Pacote.id == pacote_cliente.pacote_id))
    pacotes = pacotes_query.order_by(Pacote.nome).all()
    tutor_id = request.args.get("tutor_id", type=int) or (pacote_cliente.tutor_id if pacote_cliente else None)
    pet_options = Pet.query.filter_by(tutor_id=tutor_id, ativo=True).order_by(Pet.nome).all() if tutor_id else []
    return {
        "pacote_cliente": pacote_cliente,
        "tutores": tutores,
        "pets": pet_options,
        "pacotes": pacotes,
        "formas": FORMAS_PAGAMENTO,
        "status_options": STATUS_PACOTE_CLIENTE,
        "hoje": date.today(),
    }


@bp.route("/")
@login_required
def index():
    q = request.args.get("q", "").strip()
    status = request.args.get("status", "Ativo").strip()

    modelos = Pacote.query.order_by(Pacote.ativo.desc(), Pacote.nome).all()
    query = (
        PacoteCliente.query
        .join(PacoteCliente.tutor)
        .join(PacoteCliente.pet)
        .join(PacoteCliente.pacote)
    )
    if q:
        like = f"%{q}%"
        query = query.filter(or_(Tutor.nome.ilike(like), Pet.nome.ilike(like), Pacote.nome.ilike(like)))
    if status:
        query = query.filter(PacoteCliente.status == status)
    pacotes_clientes = query.order_by(PacoteCliente.data_fim, PacoteCliente.id.desc()).all()

    hoje = date.today()
    ativos = PacoteCliente.query.filter_by(status="Ativo").all()
    ativos_vigentes = [item for item in ativos if item.data_inicio <= hoje <= item.data_fim]
    creditos_abertos = sum(item.saldo for item in ativos_vigentes)
    vencendo = sum(1 for item in ativos_vigentes if 0 <= (item.data_fim - hoje).days <= 7)

    return render_template(
        "pacotes/index.html",
        modelos=modelos,
        pacotes_clientes=pacotes_clientes,
        q=q,
        status=status,
        status_options=STATUS_PACOTE_CLIENTE,
        total_ativos=len(ativos_vigentes),
        creditos_abertos=creditos_abertos,
        vencendo=vencendo,
    )


@bp.route("/novo", methods=["GET", "POST"])
@login_required
def novo():
    if request.method == "POST":
        pacote = Pacote(
            servico_id=request.form.get("servico_id", type=int),
            nome=request.form.get("nome", "").strip(),
            quantidade_atendimentos=request.form.get("quantidade_atendimentos", type=int),
            validade_dias=request.form.get("validade_dias", type=int) or 30,
            valor=parse_decimal(request.form.get("valor")),
            observacoes=request.form.get("observacoes", "").strip() or None,
            ativo=True,
        )
        if (
            not pacote.servico_id
            or not pacote.nome
            or not pacote.quantidade_atendimentos
            or pacote.quantidade_atendimentos <= 0
            or pacote.validade_dias <= 0
            or pacote.valor < 0
        ):
            flash("Informe serviço, nome, quantidade, validade e valor válidos.", "warning")
            return render_pacote_form(pacote)
        db.session.add(pacote)
        db.session.commit()
        flash("Pacote cadastrado com sucesso.", "success")
        return redirect(url_for("pacotes.index"))
    return render_pacote_form()


@bp.route("/<int:pacote_id>/editar", methods=["GET", "POST"])
@login_required
def editar(pacote_id):
    pacote = db.get_or_404(Pacote, pacote_id)
    if request.method == "POST":
        antigo_servico_id = pacote.servico_id
        pacote.servico_id = request.form.get("servico_id", type=int)
        pacote.nome = request.form.get("nome", "").strip()
        pacote.quantidade_atendimentos = request.form.get("quantidade_atendimentos", type=int)
        pacote.validade_dias = request.form.get("validade_dias", type=int) or 30
        pacote.valor = parse_decimal(request.form.get("valor"))
        pacote.observacoes = request.form.get("observacoes", "").strip() or None
        pacote.ativo = bool(request.form.get("ativo"))
        if pacote.clientes and pacote.servico_id != antigo_servico_id:
            db.session.rollback()
            flash("O serviço de um modelo com vínculos históricos não pode ser alterado.", "warning")
            return render_pacote_form(pacote)
        if (
            not pacote.servico_id
            or not pacote.nome
            or not pacote.quantidade_atendimentos
            or pacote.quantidade_atendimentos <= 0
            or pacote.validade_dias <= 0
            or pacote.valor < 0
        ):
            flash("Informe serviço, nome, quantidade, validade e valor válidos.", "warning")
            return render_pacote_form(pacote)
        db.session.commit()
        flash("Pacote atualizado com sucesso.", "success")
        return redirect(url_for("pacotes.index"))
    return render_pacote_form(pacote)


@bp.route("/<int:pacote_id>/inativar", methods=["POST"])
@login_required
def inativar(pacote_id):
    pacote = db.get_or_404(Pacote, pacote_id)
    pacote.ativo = False
    db.session.commit()
    flash("Pacote inativado.", "info")
    return redirect(url_for("pacotes.index"))


@bp.route("/<int:pacote_id>/excluir", methods=["POST"])
@login_required
def excluir(pacote_id):
    pacote = db.get_or_404(Pacote, pacote_id)
    pacote.ativo = False
    db.session.commit()
    flash("Modelo de pacote inativado; histórico preservado.", "info")
    return redirect(url_for("pacotes.index"))


@bp.route("/cliente/novo", methods=["GET", "POST"])
@login_required
def cliente_novo():
    pacote_cliente = PacoteCliente(
        tutor_id=request.args.get("tutor_id", type=int),
        pet_id=request.args.get("pet_id", type=int),
        pacote_id=request.args.get("pacote_id", type=int),
        data_inicio=date.today(),
    )
    if request.method == "POST":
        pacote, tutor, pet, error = validate_cliente_form()
        if error:
            flash(error, "warning")
            pacote_cliente = build_cliente_from_request(pacote_cliente)
            return render_template("pacotes/cliente_form.html", **cliente_form_context(pacote_cliente))

        pacote_cliente = build_cliente_from_request(PacoteCliente(), pacote)
        if pacote_cliente.valor < 0 or pacote_cliente.quantidade_total <= 0:
            flash("Informe quantidade e valor válidos.", "warning")
            return render_template("pacotes/cliente_form.html", **cliente_form_context(pacote_cliente))
        if pacote_cliente.data_fim < pacote_cliente.data_inicio:
            flash("A data final precisa ser maior ou igual à data inicial.", "warning")
            return render_template("pacotes/cliente_form.html", **cliente_form_context(pacote_cliente))
        db.session.add(pacote_cliente)
        db.session.commit()
        flash("Pacote vinculado ao pet com sucesso.", "success")
        return redirect(url_for("pacotes.cliente_detalhe", pacote_cliente_id=pacote_cliente.id))
    return render_template("pacotes/cliente_form.html", **cliente_form_context(pacote_cliente))


@bp.route("/cliente/<int:pacote_cliente_id>")
@login_required
def cliente_detalhe(pacote_cliente_id):
    pacote_cliente = db.get_or_404(PacoteCliente, pacote_cliente_id)
    usos = (
        UsoPacote.query
        .join(UsoPacote.agendamento)
        .filter(UsoPacote.pacote_cliente_id == pacote_cliente.id)
        .order_by(Agendamento.data.desc(), Agendamento.hora_inicio.desc())
        .all()
    )
    root_id = pacote_cliente.contrato_id or pacote_cliente.id
    ciclos = PacoteCliente.query.filter(or_(PacoteCliente.id == root_id, PacoteCliente.contrato_id == root_id)).order_by(PacoteCliente.data_inicio.desc(), PacoteCliente.id.desc()).all()
    hoje = date.today()
    return render_template("pacotes/cliente_detalhe.html", pacote_cliente=pacote_cliente, usos=usos, ciclos=ciclos, hoje=hoje, novo_fim=proximo_aniversario(hoje) - timedelta(days=1))


@bp.route("/renovacoes")
@login_required
def renovacoes():
    q = request.args.get("q", "").strip().lower()
    filtro = request.args.get("status", "Pendentes")
    inicio = parse_date(request.args.get("inicio"))
    fim = parse_date(request.args.get("fim"))
    pendentes = pendencias()
    decisoes = RenovacaoPacote.query.order_by(RenovacaoPacote.decidida_em.desc()).limit(300).all()
    items = pendentes if filtro == "Pendentes" else [d for d in decisoes if filtro == "Histórico" or (filtro == "Renovados" and d.decisao == "Aprovada") or (filtro == "Não renovados" and d.decisao == "Recusada")]
    if q:
        items = [item for item in items if q in " ".join([
            (item if filtro == "Pendentes" else item.ciclo_anterior).tutor.nome,
            (item if filtro == "Pendentes" else item.ciclo_anterior).pet.nome,
            (item if filtro == "Pendentes" else item.ciclo_anterior).pacote.nome,
        ]).lower()]
    if inicio or fim:
        items = [item for item in items if (not inicio or (item if filtro == "Pendentes" else item.ciclo_anterior).data_fim >= inicio) and (not fim or (item if filtro == "Pendentes" else item.ciclo_anterior).data_fim <= fim)]
    return render_template("pacotes/renovacoes.html", items=items, filtro=filtro, q=q, inicio=inicio, fim=fim, total_pendentes=len(pendentes))


@bp.route("/cliente/<int:pacote_cliente_id>/renovar", methods=["POST"])
@login_required
def renovar(pacote_cliente_id):
    decisao = request.form.get("decisao")
    antecipada = request.form.get("antecipada") == "1"
    try:
        novo = decidir(pacote_cliente_id, current_user.id, decisao, antecipada)
        flash("Novo ciclo criado com sucesso." if novo else "Não renovação registrada.", "success")
        return redirect(url_for("pacotes.cliente_detalhe", pacote_cliente_id=novo.id if novo else pacote_cliente_id))
    except (ValueError, IntegrityError) as exc:
        db.session.rollback()
        flash(str(exc) if isinstance(exc, ValueError) else "Este ciclo já foi decidido por outro usuário.", "warning")
        return redirect(request.referrer or url_for("pacotes.renovacoes"))


@bp.route("/cliente/<int:pacote_cliente_id>/editar", methods=["GET", "POST"])
@login_required
def cliente_editar(pacote_cliente_id):
    pacote_cliente = db.get_or_404(PacoteCliente, pacote_cliente_id)
    if request.method == "POST":
        if pacote_cliente.proximo_ciclo or pacote_cliente.status == "Encerrado":
            flash("Ciclos históricos encerrados não podem ser editados.", "warning")
            return redirect(url_for("pacotes.cliente_detalhe", pacote_cliente_id=pacote_cliente.id))
        pacote, tutor, pet, error = validate_cliente_form(allow_inactive_id=pacote_cliente.pacote_id)
        if error:
            flash(error, "warning")
            pacote_cliente = build_cliente_from_request(pacote_cliente)
            return render_template("pacotes/cliente_form.html", **cliente_form_context(pacote_cliente))

        tem_usos = bool(pacote_cliente.usos)
        datas_originais = (pacote_cliente.data_inicio, pacote_cliente.data_fim, pacote_cliente.quantidade_total)
        identidade_alterada = (
            pacote_cliente.pacote_id != pacote.id
            or pacote_cliente.tutor_id != tutor.id
            or pacote_cliente.pet_id != pet.id
        )
        if (tem_usos or pacote_cliente.ciclo_anterior_id) and identidade_alterada:
            flash("Pacotes com uso já registrado não podem trocar modelo, tutor ou pet.", "warning")
            return render_template("pacotes/cliente_form.html", **cliente_form_context(pacote_cliente))

        consumidos = pacote_cliente.usos_consumidos()
        old_status = pacote_cliente.status
        atualizado = build_cliente_from_request(pacote_cliente, pacote)
        if (tem_usos or pacote_cliente.ciclo_anterior_id or datas_originais[1] < date.today()) and (atualizado.data_inicio, atualizado.data_fim, atualizado.quantidade_total) != datas_originais:
            flash("Datas e créditos de ciclos com histórico ou vencidos não podem ser alterados.", "warning")
            db.session.rollback()
            return render_template("pacotes/cliente_form.html", **cliente_form_context(pacote_cliente))
        if atualizado.valor < 0 or atualizado.quantidade_total <= 0:
            flash("Informe quantidade e valor válidos.", "warning")
            return render_template("pacotes/cliente_form.html", **cliente_form_context(pacote_cliente))
        if atualizado.data_fim < atualizado.data_inicio:
            flash("A data final precisa ser maior ou igual à data inicial.", "warning")
            return render_template("pacotes/cliente_form.html", **cliente_form_context(pacote_cliente))
        if atualizado.quantidade_total < consumidos:
            flash("A quantidade não pode ficar menor que os usos já consumidos.", "warning")
            return render_template("pacotes/cliente_form.html", **cliente_form_context(pacote_cliente))
        if old_status == "Ativo" and atualizado.status != "Ativo":
            atualizado.encerrado_em = date.today()
            atualizado.creditos_expirados = atualizado.saldo
        db.session.commit()
        flash("Pacote do cliente atualizado.", "success")
        return redirect(url_for("pacotes.cliente_detalhe", pacote_cliente_id=pacote_cliente.id))
    return render_template("pacotes/cliente_form.html", **cliente_form_context(pacote_cliente))


@bp.route("/cliente/<int:pacote_cliente_id>/encerrar", methods=["POST"])
@login_required
def cliente_encerrar(pacote_cliente_id):
    pacote_cliente = db.get_or_404(PacoteCliente, pacote_cliente_id)
    pacote_cliente.status = "Encerrado"
    pacote_cliente.encerrado_em = date.today()
    pacote_cliente.creditos_expirados = pacote_cliente.saldo
    db.session.commit()
    flash("Pacote encerrado.", "info")
    return redirect(request.referrer or url_for("pacotes.index"))


@bp.route("/cliente/<int:pacote_cliente_id>/excluir", methods=["POST"])
@login_required
def cliente_excluir(pacote_cliente_id):
    pacote_cliente = db.get_or_404(PacoteCliente, pacote_cliente_id)
    if pacote_cliente.usos or pacote_cliente.proximo_ciclo or pacote_cliente.ciclo_anterior_id or RenovacaoPacote.query.filter_by(ciclo_anterior_id=pacote_cliente.id).first():
        flash("Pacotes com consumo na agenda nao podem ser excluidos. Remova o vinculo dos agendamentos antes.", "warning")
        return redirect(request.referrer or url_for("pacotes.cliente_detalhe", pacote_cliente_id=pacote_cliente.id))

    pacote_cliente.status = "Cancelado"
    pacote_cliente.encerrado_em = date.today()
    pacote_cliente.creditos_expirados = pacote_cliente.saldo
    db.session.commit()
    flash("Pacote cancelado; histórico e financeiro preservados.", "info")
    return redirect(url_for("pacotes.index"))


def validate_cliente_form(allow_inactive_id=None):
    pacote = db.session.get(Pacote, request.form.get("pacote_id", type=int))
    tutor = db.session.get(Tutor, request.form.get("tutor_id", type=int))
    pet = db.session.get(Pet, request.form.get("pet_id", type=int))
    if not pacote or (not pacote.ativo and pacote.id != allow_inactive_id):
        return pacote, tutor, pet, "Selecione um pacote ativo."
    if not tutor or not tutor.ativo:
        return pacote, tutor, pet, "Selecione um tutor ativo."
    if not pet or not pet.ativo or pet.tutor_id != tutor.id:
        return pacote, tutor, pet, "Selecione um pet válido para o tutor informado."
    return pacote, tutor, pet, None


def build_cliente_from_request(pacote_cliente, pacote=None):
    pacote = pacote or db.session.get(Pacote, request.form.get("pacote_id", type=int))
    data_inicio = parse_date(request.form.get("data_inicio"), date.today())
    data_fim = parse_date(request.form.get("data_fim"))
    if not pacote_cliente.id:
        data_fim = proximo_aniversario(data_inicio) - timedelta(days=1)

    pacote_cliente.pacote_id = request.form.get("pacote_id", type=int)
    pacote_cliente.tutor_id = request.form.get("tutor_id", type=int)
    pacote_cliente.pet_id = request.form.get("pet_id", type=int)
    pacote_cliente.data_inicio = data_inicio
    if not pacote_cliente.id:
        pacote_cliente.dia_ancora = data_inicio.day
    pacote_cliente.data_fim = data_fim or data_inicio
    pacote_cliente.quantidade_total = (
        request.form.get("quantidade_total", type=int)
        or (pacote.quantidade_atendimentos if pacote else 0)
    )
    pacote_cliente.valor = parse_decimal(request.form.get("valor"), pacote.valor if pacote else Decimal("0"))
    pacote_cliente.pago = bool(request.form.get("pago"))
    pacote_cliente.forma_pagamento = request.form.get("forma_pagamento") or None
    pacote_cliente.data_pagamento = parse_date(request.form.get("data_pagamento"), date.today() if pacote_cliente.pago else None)
    pacote_cliente.status = request.form.get("status") if request.form.get("status") in STATUS_PACOTE_CLIENTE else "Ativo"
    pacote_cliente.observacoes = request.form.get("observacoes", "").strip() or None
    if not pacote_cliente.pago:
        pacote_cliente.data_pagamento = None
    return pacote_cliente
