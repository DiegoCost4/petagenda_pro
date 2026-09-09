from datetime import date, timedelta
from decimal import Decimal
from flask import Blueprint, render_template
from flask_login import login_required
from sqlalchemy import func, or_
from app.models import Agendamento, Tutor, Pet, Pagamento, PacoteCliente
from app.utils import brl, generate_available_slots

bp = Blueprint("dashboard", __name__)


@bp.app_template_filter("brl")
def brl_filter(value):
    return brl(value)


@bp.route("/")
@login_required
def index():
    hoje = date.today()
    agendamentos_hoje = Agendamento.query.filter_by(data=hoje).order_by(Agendamento.hora_inicio).all()
    ativos_hoje = [a for a in agendamentos_hoje if a.status not in ["Cancelado", "Faltou"]]
    pacotes_hoje = PacoteCliente.query.filter(
        PacoteCliente.status != "Cancelado",
        or_(PacoteCliente.data_inicio == hoje, PacoteCliente.data_pagamento == hoje),
    ).all()
    total_previsto = (
        sum((Decimal(a.valor or 0) for a in ativos_hoje), Decimal("0"))
        + sum((Decimal(p.valor or 0) for p in pacotes_hoje), Decimal("0"))
    )
    total_recebido = db_total_recebido(hoje, hoje)
    proximo = next((a for a in ativos_hoje if a.status in ["Agendado", "Confirmado", "Em atendimento"]), None)

    status_count = {}
    for a in agendamentos_hoje:
        status_count[a.status] = status_count.get(a.status, 0) + 1

    semana_inicio = hoje - timedelta(days=hoje.weekday())
    semana_fim = semana_inicio + timedelta(days=6)
    agenda_semana = Agendamento.query.filter(
        Agendamento.data >= semana_inicio,
        Agendamento.data <= semana_fim,
    ).order_by(Agendamento.data, Agendamento.hora_inicio).all()

    return render_template(
        "dashboard/index.html",
        hoje=hoje,
        agendamentos_hoje=agendamentos_hoje,
        total_agendamentos=len(ativos_hoje),
        total_previsto=total_previsto,
        total_recebido=total_recebido,
        proximo=proximo,
        status_count=status_count,
        total_tutores=Tutor.query.filter_by(ativo=True).count(),
        total_pets=Pet.query.filter_by(ativo=True).count(),
        agenda_semana=agenda_semana,
    )


def db_total_recebido(data_ini, data_fim):
    total_atendimentos = (
        Pagamento.query.with_entities(func.coalesce(func.sum(Pagamento.valor), 0))
        .filter(Pagamento.data_pagamento >= data_ini, Pagamento.data_pagamento <= data_fim)
        .scalar()
    )
    total_pacotes = (
        PacoteCliente.query.with_entities(func.coalesce(func.sum(PacoteCliente.valor), 0))
        .filter(
            PacoteCliente.pago.is_(True),
            PacoteCliente.data_pagamento >= data_ini,
            PacoteCliente.data_pagamento <= data_fim,
        )
        .scalar()
    )
    return Decimal(total_atendimentos or 0) + Decimal(total_pacotes or 0)
