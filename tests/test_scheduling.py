from datetime import date
from decimal import Decimal
from html.parser import HTMLParser
import unittest
from unittest.mock import patch

from app import create_app
from app.extensions import db
from app.models import (
    Agendamento, BloqueioAgenda, HorarioFuncionamento, Pacote,
    PacoteCliente, Pet, Servico, Tutor, User,
)
from config import Config


class Inputs(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.fields = {}
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == 'input' and 'name' in values:
            self.fields[values['name']] = values


class SchedulingTests(unittest.TestCase):
    day = date(2030, 1, 7)

    def setUp(self):
        with patch.object(Config, 'SQLALCHEMY_DATABASE_URI', 'sqlite://'):
            self.app = create_app()
        self.app.config['TESTING'] = True
        self.context = self.app.app_context()
        self.context.push()
        user = User(nome='Tester', email='test@example.local', senha_hash='unused')
        self.tutor = Tutor(nome='Tutor A', telefone='31999999999')
        self.other_tutor = Tutor(nome='Tutor B', telefone='31888888888')
        self.pet = Pet(nome='Pet A', tutor=self.tutor, porte='Pequeno')
        self.sibling = Pet(nome='Pet B', tutor=self.tutor, porte='Pequeno')
        self.other_pet = Pet(nome='Pet C', tutor=self.other_tutor, porte='Pequeno')
        self.bath = Servico(nome='Banho', porte='Pequeno', duracao_minutos=60, valor=50)
        self.extra = Servico(nome='Complemento', porte='Todos', duracao_minutos=0, valor=10)
        db.session.add_all([
            user, self.tutor, self.other_tutor, self.pet, self.sibling,
            self.other_pet, self.bath, self.extra,
            HorarioFuncionamento(
                dia_semana=0, nome_dia='Segunda', hora_inicio='08:00', hora_fim='18:00',
                pausa_inicio='12:00', pausa_fim='13:00', ativo=True,
            ),
        ])
        db.session.commit()
        self.client = self.app.test_client()
        with self.client.session_transaction() as session:
            session['_user_id'] = str(user.id)
            session['_fresh'] = True

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def payload(self, pet=None, services=None, time='09:00', **overrides):
        pet = pet or self.pet
        data = {
            'tutor_id': str(pet.tutor_id), 'pet_id': str(pet.id),
            'servico_ids': [str(service.id) for service in (services or [self.bath])],
            'data': self.day.isoformat(), 'hora_inicio': time,
        }
        data.update(overrides)
        return data

    def book(self, **kwargs):
        response = self.client.post('/agenda/novo', data=self.payload(**kwargs))
        self.assertEqual(response.status_code, 302)
        return db.session.get(Agendamento, int(response.location.rsplit('/', 1)[1]))

    def slots(self, pet=None, services=None, **extra):
        pet = pet or self.pet
        query = {
            'data': self.day.isoformat(), 'tutor_id': pet.tutor_id, 'pet_id': pet.id,
            'servico_ids': ','.join(str(service.id) for service in (services or [self.bath])),
            **extra,
        }
        response = self.client.get('/agenda/api/horarios', query_string=query)
        self.assertEqual(response.status_code, 200)
        return {slot['inicio']: slot['fim'] for slot in response.json}

    def test_siblings_can_share_start_with_independent_services_and_prices(self):
        first = self.book()
        self.assertIn('09:00', self.slots(self.sibling))
        second = self.book(pet=self.sibling, services=[self.bath, self.extra])
        self.assertNotEqual(first.id, second.id)
        self.assertEqual((first.hora_inicio, second.hora_inicio), ('09:00', '09:00'))
        self.assertEqual((first.valor, second.valor), (Decimal('50'), Decimal('60')))
        self.assertEqual((first.hora_fim, second.hora_fim), ('10:00', '10:00'))
        self.assertEqual([item.duracao_minutos for item in second.servicos_itens], [60, 0])

    def test_same_pet_other_tutors_and_different_start_still_conflict(self):
        self.book()
        self.assertNotIn('09:00', self.slots())
        self.assertNotIn('09:00', self.slots(self.other_pet))
        self.assertNotIn('09:30', self.slots(self.sibling))
        for pet, time in [(self.pet, '09:00'), (self.other_pet, '09:00'), (self.sibling, '09:30')]:
            with self.subTest(pet=pet.nome, time=time):
                response = self.client.post('/agenda/novo', data=self.payload(pet=pet, time=time))
                self.assertEqual(response.status_code, 200)
                self.assertEqual(Agendamento.query.count(), 1)

    def test_blocks_and_other_clients_still_prevent_longer_sibling_visit(self):
        self.book()
        self.book(pet=self.other_pet, time='10:00')
        longer = Servico(nome='Longo', porte='Pequeno', duracao_minutos=90, valor=80)
        db.session.add(longer)
        db.session.commit()
        self.assertNotIn('09:00', self.slots(self.sibling, [longer]))
        response = self.client.post('/agenda/novo', data=self.payload(pet=self.sibling, services=[longer]))
        self.assertEqual(response.status_code, 200)
        db.session.add(BloqueioAgenda(data=self.day, hora_inicio='09:00', hora_fim='09:30', motivo='Bloqueio'))
        db.session.commit()
        self.assertNotIn('09:00', self.slots(self.sibling))
        response = self.client.post('/agenda/novo', data=self.payload(pet=self.sibling))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Agendamento.query.count(), 2)

    def test_edit_ignores_itself_but_checks_other_visits(self):
        first = self.book()
        second = self.book(pet=self.sibling)
        self.assertIn('09:00', self.slots(agendamento_id=first.id))
        response = self.client.post(f'/agenda/{first.id}/editar', data=self.payload(services=[self.bath, self.extra]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(first.valor, Decimal('60'))
        self.book(pet=self.other_pet, time='10:00')
        self.assertNotIn('10:00', self.slots(agendamento_id=first.id))
        response = self.client.post(f'/agenda/{first.id}/editar', data=self.payload(time='10:00'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(first.hora_inicio, '09:00')
        self.assertEqual(second.hora_inicio, '09:00')

    def test_matching_start_outside_regular_slot_grid_is_available(self):
        self.book(time='09:15')
        self.assertEqual(self.slots(self.sibling)['09:15'], '10:15')
        self.book(pet=self.sibling, time='09:15')

    def test_cancelled_visits_and_absences_do_not_block(self):
        for status in ['Cancelado', 'Faltou']:
            with self.subTest(status=status):
                item = self.book(status=status)
                self.assertIn('09:00', self.slots(self.other_pet))
                db.session.delete(item)
                db.session.commit()

    def test_zero_duration_alone_can_be_booked_and_is_not_duplicated(self):
        slots = self.slots(services=[self.extra])
        self.assertEqual(slots['08:00'], '08:00')
        self.assertNotIn('12:00', slots)
        self.assertNotIn('12:30', slots)
        self.assertNotIn('18:00', slots)
        item = self.book(services=[self.extra])
        self.assertEqual((item.hora_inicio, item.hora_fim), ('09:00', '09:00'))
        self.assertEqual(item.duracao_total_minutos, 0)
        self.assertNotIn('09:00', self.slots(services=[self.extra]))
        self.assertNotIn('09:00', self.slots(self.other_pet))
        self.assertIn('09:00', self.slots(self.sibling, [self.extra]))
        self.assertEqual(self.client.post('/agenda/novo', data=self.payload(services=[self.extra])).status_code, 200)

    def test_zero_duration_respects_block_pause_and_closing_boundaries(self):
        db.session.add(BloqueioAgenda(data=self.day, hora_inicio='09:00', hora_fim='10:00', motivo='Bloqueio'))
        db.session.commit()
        slots = self.slots(services=[self.extra])
        self.assertNotIn('09:00', slots)
        self.assertNotIn('09:30', slots)
        self.assertIn('10:00', slots)
        for time in ['09:00', '12:00', '18:00']:
            self.assertEqual(self.client.post('/agenda/novo', data=self.payload(services=[self.extra], time=time)).status_code, 200)
        self.assertEqual(Agendamento.query.count(), 0)

    def test_slots_validate_identity_services_and_zero_duration(self):
        self.assertEqual(self.slots(self.sibling, tutor_id=self.other_tutor.id), {})
        self.assertEqual(self.slots(servico_ids='999999'), {})
        self.assertEqual(self.client.get('/agenda/api/horarios', query_string={'data': self.day.isoformat()}).json, [])
        response = self.client.get('/agenda/api/horarios', query_string={'data': self.day.isoformat(), 'duracao_minutos': 0})
        self.assertTrue(response.json)
        self.assertEqual(self.client.get('/agenda/api/horarios', query_string={'data': self.day.isoformat(), 'duracao_minutos': -1}).json, [])

    def test_service_duration_optional_on_create_and_edit(self):
        for duration in [None, '', '0', '25']:
            with self.subTest(duration=duration):
                data = {'nome': f'Extra [{duration}]', 'porte': 'Todos', 'valor': '15'}
                if duration is not None:
                    data['duracao_minutos'] = duration
                self.assertEqual(self.client.post('/servicos/novo', data=data).status_code, 302)
                item = Servico.query.filter_by(nome=data['nome']).one()
                self.assertEqual(item.duracao_minutos, int(duration or 0))
        response = self.client.post(f'/servicos/{self.bath.id}/editar', data={
            'nome': 'Banho', 'porte': 'Pequeno', 'valor': '50', 'duracao_minutos': '', 'ativo': 'on',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.bath.duracao_minutos, 0)
        html = self.client.get(f'/servicos/{self.bath.id}/editar').get_data(as_text=True)
        field = Inputs(html).fields['duracao_minutos']
        self.assertNotIn('required', field)
        self.assertEqual(field['min'], '0')
        self.assertEqual(field['value'], '')

    def test_invalid_duration_does_not_save(self):
        initial_count = Servico.query.count()
        for duration in ['-10', 'invalid', '1.5']:
            data = {'nome': 'Invalid', 'porte': 'Todos', 'valor': '10', 'duracao_minutos': duration}
            self.assertEqual(self.client.post('/servicos/novo', data=data).status_code, 200)
            self.assertEqual(Servico.query.count(), initial_count)
            self.assertEqual(self.client.post(f'/servicos/{self.bath.id}/editar', data=data).status_code, 200)
            self.assertEqual(self.bath.duracao_minutos, 60)

    def test_packages_are_consumed_per_pet_when_sharing_time(self):
        model = Pacote(servico=self.bath, nome='Mensal', quantidade_atendimentos=4, validade_dias=30, valor=180)
        db.session.add(model)
        packages = []
        for pet in [self.pet, self.sibling]:
            package = PacoteCliente(pacote=model, tutor=self.tutor, pet=pet,
                                   data_inicio=self.day, data_fim=date(2030, 2, 1), quantidade_total=4, valor=180)
            db.session.add(package)
            packages.append(package)
        db.session.commit()
        first = self.book(pacote_cliente_id=packages[0].id)
        second = self.book(pet=self.sibling, services=[self.bath, self.extra], pacote_cliente_id=packages[1].id)
        self.assertEqual(first.valor, Decimal('0'))
        self.assertEqual(second.valor, Decimal('10'))
        self.assertEqual([package.saldo for package in packages], [3, 3])
        response = self.client.get('/agenda/api/pacotes', query_string={
            'data': self.day.isoformat(), 'tutor_id': self.tutor.id, 'pet_id': self.sibling.id,
            'servico_ids': self.bath.id, 'agendamento_id': first.id,
        })
        self.assertEqual([item['id'] for item in response.json], [packages[1].id])

    def test_second_pet_shortcut_prefills_tutor_and_date(self):
        item = self.book()
        html = self.client.get(f'/agenda/{item.id}').get_data(as_text=True)
        self.assertIn('Agendar outro pet', html)
        response = self.client.get('/agenda/novo', query_string={
            'tutor_id': self.tutor.id, 'data': self.day.isoformat(), 'hora_inicio': '09:00',
        })
        html = response.get_data(as_text=True)
        self.assertIn(f'<option value="{self.tutor.id}" selected>', html)
        self.assertIn(self.sibling.nome, html)
        self.assertEqual(Inputs(html).fields['data']['value'], self.day.isoformat())
        self.assertIn('let horarioPreferido = "09:00";', html)


if __name__ == '__main__':
    unittest.main()
