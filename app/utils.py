from datetime import datetime, timedelta, date
from decimal import Decimal
from urllib.parse import quote
from .models import Agendamento, BloqueioAgenda, HorarioFuncionamento

STATUS_AGENDAMENTO = [
    "Agendado",
    "Confirmado",
    "Em atendimento",
    "Pronto",
    "Entregue",
    "Cancelado",
    "Faltou",
]

FORMAS_PAGAMENTO = ["Pix", "Dinheiro", "Cartão de débito", "Cartão de crédito", "Pacote", "Outro"]
STATUS_PACOTE_CLIENTE = ["Ativo", "Pausado", "Encerrado", "Cancelado"]
PORTES = ["Pequeno", "Médio", "Grande", "Todos"]
ESPECIES = ["Cachorro", "Gato", "Outro"]


def parse_time(value: str):
    return datetime.strptime(value, "%H:%M").time()


def add_minutes_to_time(hora: str, minutos: int) -> str:
    base = datetime.strptime(hora, "%H:%M")
    return (base + timedelta(minutes=minutos)).strftime("%H:%M")


def intervals_overlap(start_a: str, end_a: str, start_b: str, end_b: str) -> bool:
    # Sem duracao, a reserva representa apenas o instante de chegada.
    if start_a == end_a:
        return start_a == start_b or start_b <= start_a < end_b
    if start_b == end_b:
        return start_a <= start_b < end_a
    return start_a < end_b and start_b < end_a


def has_conflict(data_agendamento: date, hora_inicio: str, hora_fim: str, ignore_id=None, *, tutor_id=None, pet_id=None) -> bool:
    query = Agendamento.query.filter(
        Agendamento.data == data_agendamento,
        Agendamento.status.notin_(["Cancelado", "Faltou"]),
    )
    if ignore_id:
        query = query.filter(Agendamento.id != ignore_id)
    for item in query.all():
        if (
            tutor_id and pet_id
            and item.tutor_id == tutor_id
            and item.pet_id != pet_id
            and item.hora_inicio == hora_inicio
        ):
            continue
        if intervals_overlap(hora_inicio, hora_fim, item.hora_inicio, item.hora_fim):
            return True

    for bloqueio in BloqueioAgenda.query.filter_by(data=data_agendamento).all():
        if intervals_overlap(hora_inicio, hora_fim, bloqueio.hora_inicio, bloqueio.hora_fim):
            return True
    return False


def validate_inside_business_hours(data_agendamento: date, hora_inicio: str, hora_fim: str) -> tuple[bool, str]:
    horario = HorarioFuncionamento.query.filter_by(dia_semana=data_agendamento.weekday()).first()
    if not horario or not horario.ativo:
        return False, "A pet não atende neste dia da semana."

    if hora_fim < hora_inicio:
        return False, "O atendimento deve terminar no mesmo dia."

    if hora_inicio < horario.hora_inicio or hora_inicio >= horario.hora_fim or hora_fim > horario.hora_fim:
        return False, f"Horário fora do funcionamento: {horario.hora_inicio} às {horario.hora_fim}."

    if horario.pausa_inicio and horario.pausa_fim:
        if intervals_overlap(hora_inicio, hora_fim, horario.pausa_inicio, horario.pausa_fim):
            return False, f"Horário conflita com a pausa: {horario.pausa_inicio} às {horario.pausa_fim}."

    return True, "OK"


def generate_available_slots(data_agendamento: date, duracao_minutos: int, step_minutes: int = 30, *, tutor_id=None, pet_id=None, ignore_id=None):
    if duracao_minutos < 0 or step_minutes <= 0:
        return []
    horario = HorarioFuncionamento.query.filter_by(dia_semana=data_agendamento.weekday()).first()
    if not horario or not horario.ativo:
        return []

    candidatos = set()
    current = datetime.combine(data_agendamento, parse_time(horario.hora_inicio))
    fim = datetime.combine(data_agendamento, parse_time(horario.hora_fim))
    while current < fim and current + timedelta(minutes=duracao_minutos) <= fim:
        candidatos.add(current.strftime("%H:%M"))
        current += timedelta(minutes=step_minutes)

    if tutor_id and pet_id:
        existentes = Agendamento.query.filter(
            Agendamento.data == data_agendamento,
            Agendamento.tutor_id == tutor_id,
            Agendamento.status.notin_(["Cancelado", "Faltou"]),
        ).all()
        for item in existentes:
            if item.pet_id != pet_id or item.id == ignore_id:
                candidatos.add(item.hora_inicio)

    slots = []
    for inicio_str in sorted(candidatos):
        inicio = datetime.combine(data_agendamento, parse_time(inicio_str))
        termino = inicio + timedelta(minutes=duracao_minutos)
        if termino > fim:
            continue
        fim_str = termino.strftime("%H:%M")
        inside, _ = validate_inside_business_hours(data_agendamento, inicio_str, fim_str)
        if inside and not has_conflict(
            data_agendamento, inicio_str, fim_str, ignore_id,
            tutor_id=tutor_id, pet_id=pet_id,
        ):
            slots.append({"inicio": inicio_str, "fim": fim_str})
    return slots


def brl(value) -> str:
    if value is None:
        value = Decimal("0")
    return f"R$ {float(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def whatsapp_url(phone: str, message: str) -> str:
    digits = "".join(ch for ch in (phone or "") if ch.isdigit())
    if len(digits) <= 11:
        digits = "55" + digits
    return f"https://wa.me/{digits}?text={quote(message)}"
