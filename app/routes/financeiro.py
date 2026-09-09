from datetime import date, datetime
from decimal import Decimal
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from sqlalchemy import func, or_
from app.extensions import db
from app.models import Agendamento, Pagamento, PacoteCliente
from app.utils import FORMAS_PAGAMENTO

bp = Blueprint("financeiro", __name__, url_prefix="/financeiro")


def parse_date(value, default):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date() if value else default
    except ValueError:
        return default


@bp.route("/")
@login_required
def index():
    hoje = date.today()
    data_ini = parse_date(request.args.get("data_ini"), hoje.replace(day=1))
    data_fim = parse_date(request.args.get("data_fim"), hoje)

    agendamentos = Agendamento.query.filter(
        Agendamento.data >= data_ini,
        Agendamento.data <= data_fim,
        Agendamento.status.notin_(["Cancelado", "Faltou"]),
    ).order_by(Agendamento.data.desc(), Agendamento.hora_inicio).all()

    pacotes_periodo = PacoteCliente.query.filter(
        PacoteCliente.status != "Cancelado",
        or_(
            (PacoteCliente.data_inicio >= data_ini) & (PacoteCliente.data_inicio <= data_fim),
            (PacoteCliente.data_pagamento >= data_ini) & (PacoteCliente.data_pagamento <= data_fim),
        ),
    ).order_by(PacoteCliente.data_inicio.desc()).all()

    total_previsto_atendimentos = sum((Decimal(a.valor or 0) for a in agendamentos), Decimal("0"))
    total_previsto_pacotes = sum((Decimal(p.valor or 0) for p in pacotes_periodo), Decimal("0"))
    total_recebido_atendimentos = (
        Pagamento.query.with_entities(func.coalesce(func.sum(Pagamento.valor), 0))
        .filter(Pagamento.data_pagamento >= data_ini, Pagamento.data_pagamento <= data_fim)
        .scalar()
    )
    total_recebido_atendimentos = Decimal(total_recebido_atendimentos or 0)
    total_recebido_pacotes = (
        PacoteCliente.query.with_entities(func.coalesce(func.sum(PacoteCliente.valor), 0))
        .filter(
            PacoteCliente.pago.is_(True),
            PacoteCliente.data_pagamento >= data_ini,
            PacoteCliente.data_pagamento <= data_fim,
        )
        .scalar()
    )
    total_recebido_pacotes = Decimal(total_recebido_pacotes or 0)
    total_previsto = total_previsto_atendimentos + total_previsto_pacotes
    total_recebido = total_recebido_atendimentos + total_recebido_pacotes
    total_pendente = total_previsto - total_recebido

    pagamentos_por_forma_atendimentos = (
        db.session.query(Pagamento.forma_pagamento, func.coalesce(func.sum(Pagamento.valor), 0))
        .filter(Pagamento.data_pagamento >= data_ini, Pagamento.data_pagamento <= data_fim)
        .group_by(Pagamento.forma_pagamento)
        .all()
    )
    pagamentos_por_forma_pacotes = (
        db.session.query(PacoteCliente.forma_pagamento, func.coalesce(func.sum(PacoteCliente.valor), 0))
        .filter(
            PacoteCliente.pago.is_(True),
            PacoteCliente.data_pagamento >= data_ini,
            PacoteCliente.data_pagamento <= data_fim,
        )
        .group_by(PacoteCliente.forma_pagamento)
        .all()
    )
    totais_por_forma = {}
    for forma, total in pagamentos_por_forma_atendimentos + pagamentos_por_forma_pacotes:
        forma = forma or "Não informado"
        totais_por_forma[forma] = totais_por_forma.get(forma, Decimal("0")) + Decimal(total or 0)
    pagamentos_por_forma = sorted(totais_por_forma.items())

    return render_template(
        "financeiro/index.html",
        data_ini=data_ini,
        data_fim=data_fim,
        agendamentos=agendamentos,
        total_previsto=total_previsto,
        total_recebido=total_recebido,
        total_pendente=total_pendente,
        pagamentos_por_forma=pagamentos_por_forma,
        pacotes_periodo=pacotes_periodo,
        total_previsto_atendimentos=total_previsto_atendimentos,
        total_previsto_pacotes=total_previsto_pacotes,
        total_recebido_atendimentos=total_recebido_atendimentos,
        total_recebido_pacotes=total_recebido_pacotes,
        formas=FORMAS_PAGAMENTO,
    )


@bp.route("/pagar/<int:agendamento_id>", methods=["POST"])
@login_required
def pagar(agendamento_id):
    agendamento = db.get_or_404(Agendamento, agendamento_id)
    forma = request.form.get("forma_pagamento") or agendamento.forma_pagamento or "Pix"
    valor = request.form.get("valor", type=float)
    data_pagamento = parse_date(request.form.get("data_pagamento"), date.today())
    if agendamento.pagamento:
        pagamento = agendamento.pagamento
        pagamento.valor = Decimal(str(valor if valor is not None else agendamento.valor))
        pagamento.forma_pagamento = forma
        pagamento.status = "Pago"
        pagamento.data_pagamento = data_pagamento
    else:
        pagamento = Pagamento(
            agendamento_id=agendamento.id,
            valor=Decimal(str(valor if valor is not None else agendamento.valor)),
            forma_pagamento=forma,
            status="Pago",
            data_pagamento=data_pagamento,
        )
        db.session.add(pagamento)
    agendamento.pago = True
    agendamento.forma_pagamento = forma
    if agendamento.status in ["Agendado", "Confirmado", "Pronto"]:
        agendamento.status = "Entregue"
    db.session.commit()
    flash("Pagamento registrado com sucesso.", "success")
    return redirect(request.referrer or url_for("financeiro.index"))


@bp.route("/estornar/<int:agendamento_id>", methods=["POST"])
@login_required
def estornar(agendamento_id):
    agendamento = db.get_or_404(Agendamento, agendamento_id)
    if agendamento.pagamento:
        db.session.delete(agendamento.pagamento)
    agendamento.pago = False
    db.session.commit()
    flash("Pagamento removido.", "info")
    return redirect(request.referrer or url_for("financeiro.index"))
