from datetime import datetime, date
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from .extensions import db


class TimestampMixin:
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class User(UserMixin, TimestampMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(160), unique=True, nullable=False, index=True)
    senha_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(30), default="admin", nullable=False)
    ativo = db.Column(db.Boolean, default=True, nullable=False)

    def set_password(self, password: str):
        self.senha_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.senha_hash, password)


class Tutor(TimestampMixin, db.Model):
    __tablename__ = "tutores"

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(150), nullable=False, index=True)
    telefone = db.Column(db.String(30), nullable=False, index=True)
    email = db.Column(db.String(160))
    endereco = db.Column(db.String(255))
    bairro = db.Column(db.String(100))
    observacoes = db.Column(db.Text)
    ativo = db.Column(db.Boolean, default=True, nullable=False)

    pets = db.relationship("Pet", back_populates="tutor", cascade="all, delete-orphan")
    agendamentos = db.relationship("Agendamento", back_populates="tutor")
    pacotes_clientes = db.relationship("PacoteCliente", back_populates="tutor")

    @property
    def whatsapp_link(self):
        digits = "".join(ch for ch in (self.telefone or "") if ch.isdigit())
        if len(digits) <= 11:
            digits = "55" + digits
        return f"https://wa.me/{digits}"


class Pet(TimestampMixin, db.Model):
    __tablename__ = "pets"

    id = db.Column(db.Integer, primary_key=True)
    tutor_id = db.Column(db.Integer, db.ForeignKey("tutores.id"), nullable=False, index=True)
    nome = db.Column(db.String(120), nullable=False, index=True)
    especie = db.Column(db.String(40), default="Cachorro", nullable=False)
    raca = db.Column(db.String(100))
    porte = db.Column(db.String(30), nullable=False)
    sexo = db.Column(db.String(20))
    idade = db.Column(db.String(50))
    peso = db.Column(db.String(30))
    foto = db.Column(db.String(255))
    observacoes = db.Column(db.Text)
    restricoes = db.Column(db.Text)
    ativo = db.Column(db.Boolean, default=True, nullable=False)

    tutor = db.relationship("Tutor", back_populates="pets")
    agendamentos = db.relationship("Agendamento", back_populates="pet")
    pacotes_clientes = db.relationship("PacoteCliente", back_populates="pet")


class Servico(TimestampMixin, db.Model):
    __tablename__ = "servicos"

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False, index=True)
    porte = db.Column(db.String(30), nullable=False)
    duracao_minutos = db.Column(db.Integer, nullable=False)
    valor = db.Column(db.Numeric(10, 2), nullable=False)
    ativo = db.Column(db.Boolean, default=True, nullable=False)
    observacoes = db.Column(db.Text)

    agendamentos = db.relationship("Agendamento", back_populates="servico")
    pacotes = db.relationship("Pacote", back_populates="servico")

    @property
    def descricao(self):
        return f"{self.nome} - {self.porte} ({self.duracao_minutos}min)"


class Pacote(TimestampMixin, db.Model):
    __tablename__ = "pacotes"

    id = db.Column(db.Integer, primary_key=True)
    servico_id = db.Column(db.Integer, db.ForeignKey("servicos.id"), nullable=False, index=True)
    nome = db.Column(db.String(120), nullable=False, index=True)
    quantidade_atendimentos = db.Column(db.Integer, nullable=False)
    validade_dias = db.Column(db.Integer, default=30, nullable=False)
    valor = db.Column(db.Numeric(10, 2), nullable=False)
    ativo = db.Column(db.Boolean, default=True, nullable=False)
    observacoes = db.Column(db.Text)

    servico = db.relationship("Servico", back_populates="pacotes")
    clientes = db.relationship("PacoteCliente", back_populates="pacote")

    @property
    def descricao(self):
        return f"{self.nome} - {self.quantidade_atendimentos} atendimentos"

    @property
    def valor_por_atendimento(self):
        if not self.quantidade_atendimentos:
            return self.valor
        return self.valor / self.quantidade_atendimentos


class PacoteCliente(TimestampMixin, db.Model):
    __tablename__ = "pacotes_clientes"

    id = db.Column(db.Integer, primary_key=True)
    pacote_id = db.Column(db.Integer, db.ForeignKey("pacotes.id"), nullable=False, index=True)
    tutor_id = db.Column(db.Integer, db.ForeignKey("tutores.id"), nullable=False, index=True)
    pet_id = db.Column(db.Integer, db.ForeignKey("pets.id"), nullable=False, index=True)
    data_inicio = db.Column(db.Date, default=date.today, nullable=False, index=True)
    data_fim = db.Column(db.Date, nullable=False, index=True)
    quantidade_total = db.Column(db.Integer, nullable=False)
    valor = db.Column(db.Numeric(10, 2), nullable=False)
    pago = db.Column(db.Boolean, default=False, nullable=False)
    forma_pagamento = db.Column(db.String(30))
    data_pagamento = db.Column(db.Date)
    status = db.Column(db.String(30), default="Ativo", nullable=False, index=True)
    observacoes = db.Column(db.Text)

    pacote = db.relationship("Pacote", back_populates="clientes")
    tutor = db.relationship("Tutor", back_populates="pacotes_clientes")
    pet = db.relationship("Pet", back_populates="pacotes_clientes")
    usos = db.relationship("UsoPacote", back_populates="pacote_cliente", cascade="all, delete-orphan")

    @property
    def consumidos(self):
        return self.usos_consumidos()

    @property
    def saldo(self):
        return self.saldo_disponivel()

    @property
    def progresso_percentual(self):
        if not self.quantidade_total:
            return 0
        return min(100, int((self.consumidos / self.quantidade_total) * 100))

    @property
    def badge_class(self):
        if self.status == "Ativo" and self.saldo <= 0:
            return "secondary"
        if self.status == "Ativo" and self.data_fim < date.today():
            return "warning"
        return {
            "Ativo": "success",
            "Pausado": "warning",
            "Encerrado": "secondary",
            "Cancelado": "danger",
        }.get(self.status, "secondary")

    @property
    def status_operacional(self):
        if self.status == "Ativo" and self.saldo <= 0:
            return "Sem saldo"
        if self.status == "Ativo" and self.data_fim < date.today():
            return "Vencido"
        return self.status

    def usos_consumidos(self, ignore_agendamento_id=None):
        total = 0
        for uso in self.usos:
            if ignore_agendamento_id and uso.agendamento_id == ignore_agendamento_id:
                continue
            if uso.agendamento and uso.agendamento.is_ativo:
                total += uso.quantidade or 1
        return total

    def saldo_disponivel(self, ignore_agendamento_id=None):
        return max((self.quantidade_total or 0) - self.usos_consumidos(ignore_agendamento_id), 0)

    def vigente_em(self, data_ref):
        return self.data_inicio <= data_ref <= self.data_fim

    def pode_consumir(self, servico_id, data_ref, ignore_agendamento_id=None):
        return (
            self.status == "Ativo"
            and self.pacote
            and self.pacote.ativo
            and self.pacote.servico_id == servico_id
            and self.vigente_em(data_ref)
            and self.saldo_disponivel(ignore_agendamento_id) > 0
        )


class UsoPacote(TimestampMixin, db.Model):
    __tablename__ = "usos_pacote"

    id = db.Column(db.Integer, primary_key=True)
    pacote_cliente_id = db.Column(db.Integer, db.ForeignKey("pacotes_clientes.id"), nullable=False, index=True)
    agendamento_id = db.Column(db.Integer, db.ForeignKey("agendamentos.id"), nullable=False, unique=True, index=True)
    data_consumo = db.Column(db.Date, nullable=False, index=True)
    quantidade = db.Column(db.Integer, default=1, nullable=False)
    observacoes = db.Column(db.Text)

    pacote_cliente = db.relationship("PacoteCliente", back_populates="usos")
    agendamento = db.relationship("Agendamento", back_populates="pacote_uso")


class HorarioFuncionamento(TimestampMixin, db.Model):
    __tablename__ = "horarios_funcionamento"

    id = db.Column(db.Integer, primary_key=True)
    dia_semana = db.Column(db.Integer, unique=True, nullable=False)
    nome_dia = db.Column(db.String(30), nullable=False)
    hora_inicio = db.Column(db.String(5), nullable=False)
    hora_fim = db.Column(db.String(5), nullable=False)
    pausa_inicio = db.Column(db.String(5))
    pausa_fim = db.Column(db.String(5))
    ativo = db.Column(db.Boolean, default=True, nullable=False)


class BloqueioAgenda(TimestampMixin, db.Model):
    __tablename__ = "bloqueios_agenda"

    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.Date, nullable=False, index=True)
    hora_inicio = db.Column(db.String(5), nullable=False)
    hora_fim = db.Column(db.String(5), nullable=False)
    motivo = db.Column(db.String(255), nullable=False)


class Agendamento(TimestampMixin, db.Model):
    __tablename__ = "agendamentos"

    id = db.Column(db.Integer, primary_key=True)
    tutor_id = db.Column(db.Integer, db.ForeignKey("tutores.id"), nullable=False, index=True)
    pet_id = db.Column(db.Integer, db.ForeignKey("pets.id"), nullable=False, index=True)
    servico_id = db.Column(db.Integer, db.ForeignKey("servicos.id"), nullable=False, index=True)
    data = db.Column(db.Date, nullable=False, index=True)
    hora_inicio = db.Column(db.String(5), nullable=False)
    hora_fim = db.Column(db.String(5), nullable=False)
    valor = db.Column(db.Numeric(10, 2), nullable=False)
    status = db.Column(db.String(30), default="Agendado", nullable=False, index=True)
    forma_pagamento = db.Column(db.String(30))
    pago = db.Column(db.Boolean, default=False, nullable=False)
    observacoes = db.Column(db.Text)

    tutor = db.relationship("Tutor", back_populates="agendamentos")
    pet = db.relationship("Pet", back_populates="agendamentos")
    servico = db.relationship("Servico", back_populates="agendamentos")
    pagamento = db.relationship("Pagamento", back_populates="agendamento", uselist=False, cascade="all, delete-orphan")
    pacote_uso = db.relationship("UsoPacote", back_populates="agendamento", uselist=False, cascade="all, delete-orphan")

    @property
    def is_ativo(self):
        return self.status not in {"Cancelado", "Faltou"}

    @property
    def pacote_cliente(self):
        return self.pacote_uso.pacote_cliente if self.pacote_uso else None

    @property
    def coberto_por_pacote(self):
        return self.pacote_uso is not None

    @property
    def badge_class(self):
        return {
            "Agendado": "secondary",
            "Confirmado": "primary",
            "Em atendimento": "warning",
            "Pronto": "info",
            "Entregue": "success",
            "Cancelado": "danger",
            "Faltou": "dark",
        }.get(self.status, "secondary")

    @property
    def whatsapp_confirmacao(self):
        msg = f"Olá! Confirmando o agendamento do {self.pet.nome} para {self.data.strftime('%d/%m/%Y')} às {self.hora_inicio}. Serviço: {self.servico.nome}."
        return msg

    @property
    def whatsapp_pronto(self):
        return f"Olá! O {self.pet.nome} já está pronto para retirada."


class Pagamento(TimestampMixin, db.Model):
    __tablename__ = "pagamentos"

    id = db.Column(db.Integer, primary_key=True)
    agendamento_id = db.Column(db.Integer, db.ForeignKey("agendamentos.id"), nullable=False, unique=True, index=True)
    valor = db.Column(db.Numeric(10, 2), nullable=False)
    forma_pagamento = db.Column(db.String(30), nullable=False)
    status = db.Column(db.String(30), default="Pago", nullable=False)
    data_pagamento = db.Column(db.Date, default=date.today, nullable=False)

    agendamento = db.relationship("Agendamento", back_populates="pagamento")
