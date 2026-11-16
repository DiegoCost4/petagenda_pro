"""Regras de renovação. A consulta de pendências é derivada das datas, sem job frágil."""
import calendar
from datetime import date, datetime, timedelta
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from .extensions import db
from .models import PacoteCliente, RenovacaoPacote


def proximo_aniversario(inicio, dia_ancora=None):
    """Dia 29/30/31 é limitado ao último dia do mês seguinte."""
    year = inicio.year + (inicio.month == 12)
    month = inicio.month % 12 + 1
    return date(year, month, min(dia_ancora or inicio.day, calendar.monthrange(year, month)[1]))


def pendencias(hoje=None):
    hoje = hoje or date.today()
    return (PacoteCliente.query.filter(PacoteCliente.status == "Ativo", PacoteCliente.data_fim < hoje)
            .order_by(PacoteCliente.data_fim, PacoteCliente.id).all())


def decidir(ciclo_id, usuario_id, decisao, antecipada=False, hoje=None):
    hoje = hoje or date.today()
    if decisao not in {"Aprovada", "Recusada"}:
        raise ValueError("Decisão inválida.")
    ciclo = db.session.get(PacoteCliente, ciclo_id)
    if not ciclo or ciclo.status != "Ativo" or ciclo.proximo_ciclo:
        raise ValueError("Este ciclo já foi encerrado ou renovado.")
    if antecipada and not ciclo.vigente_em(hoje):
        raise ValueError("Renovação antecipada exige um ciclo vigente.")
    if not antecipada and ciclo.data_fim >= hoje:
        raise ValueError("Este pacote ainda não venceu.")
    if antecipada and decisao != "Aprovada":
        raise ValueError("A renovação antecipada precisa ser aprovada.")
    # Agendamentos futuros já vinculados ao ciclo antigo não podem ficar sem cobertura.
    if antecipada and any(u.agendamento and u.agendamento.is_ativo and u.agendamento.data > hoje for u in ciclo.usos):
        raise ValueError("Há agendamentos futuros neste ciclo. Reagende ou desvincule antes de renovar.")
    expirados = ciclo.saldo
    tipo = "Antecipada" if antecipada else "Normal"
    try:
        changed = db.session.execute(update(PacoteCliente).where(
            PacoteCliente.id == ciclo_id, PacoteCliente.status == "Ativo"
        ).values(status="Encerrado", encerrado_em=hoje, creditos_expirados=expirados))
        if changed.rowcount != 1:
            raise ValueError("Este ciclo já foi decidido por outro usuário.")
        novo = None
        if decisao == "Aprovada":
            inicio = hoje if antecipada else max(hoje, ciclo.data_fim + timedelta(days=1))
            ancora = inicio.day if antecipada else (ciclo.dia_ancora or ciclo.data_inicio.day)
            novo = PacoteCliente(
                pacote_id=ciclo.pacote_id, tutor_id=ciclo.tutor_id, pet_id=ciclo.pet_id,
                contrato_id=ciclo.contrato_id or ciclo.id, ciclo_anterior_id=ciclo.id,
                data_inicio=inicio, data_fim=proximo_aniversario(inicio, ancora) - timedelta(days=1),
                dia_ancora=ancora,
                quantidade_total=ciclo.quantidade_total,
                valor=ciclo.valor, pago=False, status="Ativo",
                tipo_renovacao=tipo, aprovado_em=datetime.utcnow(), aprovado_por_id=usuario_id,
            )
            db.session.add(novo)
            db.session.flush()
        db.session.add(RenovacaoPacote(
            ciclo_anterior_id=ciclo.id, novo_ciclo_id=novo.id if novo else None,
            decisao=decisao, tipo=tipo, usuario_id=usuario_id,
            creditos_expirados=expirados,
        ))
        db.session.commit()
        return novo
    except (IntegrityError, ValueError):
        db.session.rollback()
        raise
