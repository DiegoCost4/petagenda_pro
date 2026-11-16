from datetime import date, timedelta
from decimal import Decimal
import unittest
from unittest.mock import patch
from flask import template_rendered
from sqlalchemy import inspect, text

from config import Config
from app import create_app, ensure_schema
from app.extensions import db
from app.models import (User, Tutor, Pet, Servico, Pacote, PacoteCliente,
                        RenovacaoPacote, Hospedagem, HotelConfig, Agendamento, UsoPacote)
from app.package_cycles import decidir, pendencias, proximo_aniversario
from app.routes.hotel import calcular
from app.routes.dashboard import db_total_recebido


class EvolutionTests(unittest.TestCase):
    def setUp(self):
        with patch.object(Config, 'SQLALCHEMY_DATABASE_URI', 'sqlite://'):
            self.app = create_app()
        self.app.config['TESTING'] = True
        self.ctx = self.app.app_context()
        self.ctx.push()
        self.user = User(nome='Gestora', email='gestora@example.com', senha_hash='x')
        self.tutor = Tutor(nome='Ana', telefone='31999999999')
        self.pet = Pet(nome='Bento', tutor=self.tutor, porte='Pequeno')
        self.pet2 = Pet(nome='Lola', tutor=self.tutor, porte='Pequeno')
        self.other_tutor = Tutor(nome='Outro', telefone='31888888888')
        self.other_pet = Pet(nome='Fora', tutor=self.other_tutor, porte='Pequeno')
        self.service = Servico(nome='Banho', porte='Pequeno', duracao_minutos=60, valor=50)
        self.model = Pacote(nome='Mensal', servico=self.service, quantidade_atendimentos=4, validade_dias=30, valor=180)
        db.session.add_all([self.user, self.tutor, self.other_tutor, self.pet, self.pet2, self.other_pet, self.model])
        db.session.commit()
        self.client = self.app.test_client()
        with self.client.session_transaction() as session:
            session['_user_id'] = str(self.user.id)
            session['_fresh'] = True

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def cycle(self, start, end):
        item = PacoteCliente(pacote=self.model, tutor=self.tutor, pet=self.pet,
                            data_inicio=start, data_fim=end, quantidade_total=4, valor=180)
        db.session.add(item)
        db.session.commit()
        return item

    def hotel_payload(self, **changes):
        payload = dict(tutor_id=str(self.tutor.id), pet_ids=[str(self.pet.id), str(self.pet2.id)],
                       entrada='2030-01-10', saida='2030-01-15', diaria='80', desconto_percentual='10')
        payload.update(changes)
        return payload

    def test_month_end_anchor_and_non_cumulative_approval(self):
        start = date(2027, 1, 31)
        self.assertEqual(proximo_aniversario(start), date(2027, 2, 28))
        previous = self.cycle(start, date(2027, 2, 27))
        self.assertIn(previous, pendencias(date(2027, 3, 1)))
        next_cycle = decidir(previous.id, self.user.id, 'Aprovada', hoje=date(2027, 2, 28))
        self.assertEqual((next_cycle.data_inicio, next_cycle.data_fim), (date(2027, 2, 28), date(2027, 3, 30)))
        self.assertEqual(next_cycle.saldo, 4)
        self.assertEqual(previous.creditos_expirados, 4)
        self.assertEqual(previous.status, 'Encerrado')
        self.assertEqual(next_cycle.contrato_id, previous.id)
        self.assertEqual(RenovacaoPacote.query.count(), 1)
        with self.assertRaises(ValueError):
            decidir(previous.id, self.user.id, 'Aprovada', hoje=date(2027, 2, 28))

    def test_refusal_and_early_renewal(self):
        today = date.today()
        previous = self.cycle(today - timedelta(days=40), today - timedelta(days=11))
        self.assertIsNone(decidir(previous.id, self.user.id, 'Recusada', hoje=today))
        self.assertEqual(PacoteCliente.query.count(), 1)
        self.assertEqual(previous.status, 'Encerrado')
        active = self.cycle(today - timedelta(days=3), today + timedelta(days=26))
        renewed = decidir(active.id, self.user.id, 'Aprovada', antecipada=True, hoje=today)
        self.assertEqual(renewed.data_inicio, today)
        self.assertEqual(renewed.tipo_renovacao, 'Antecipada')
        self.assertEqual(active.data_fim, today + timedelta(days=26))
        self.assertNotIn(active, pendencias(today + timedelta(days=27)))

    def test_package_booking_prefill_and_expired_credit(self):
        today = date.today()
        expired = self.cycle(today - timedelta(days=40), today - timedelta(days=11))
        self.assertFalse(expired.pode_consumir(self.service.id, today - timedelta(days=20)))
        item = self.cycle(today, today + timedelta(days=29))
        html = self.client.get('/agenda/novo', query_string={'pacote_cliente_id': item.id}).get_data(as_text=True)
        self.assertIn(f'<option value="{self.tutor.id}" selected>', html)
        self.assertIn(f'value="{self.pet.id}" selected', html)
        self.assertIn(f'value="{self.service.id}"', html)
        self.assertIn('const pacoteAtualId = %d' % item.id, html)
        decidir(item.id, self.user.id, 'Aprovada', antecipada=True, hoje=today)
        self.assertFalse(item.pode_consumir(self.service.id, today))

    def test_cancellation_does_not_reactivate_expired_credit(self):
        today = date.today()
        cycle = self.cycle(today - timedelta(days=2), today + timedelta(days=27))
        booking = Agendamento(tutor=self.tutor, pet=self.pet, servico=self.service, data=today,
                              hora_inicio='09:00', hora_fim='10:00', valor=0, status='Confirmado')
        db.session.add(booking)
        db.session.flush()
        db.session.add(UsoPacote(pacote_cliente=cycle, agendamento=booking, data_consumo=today, quantidade=1))
        db.session.commit()
        self.assertEqual(cycle.saldo, 3)
        decidir(cycle.id, self.user.id, 'Aprovada', antecipada=True, hoje=today)
        self.assertEqual(cycle.creditos_expirados, 3)
        self.client.post(f'/agenda/{booking.id}/status', data={'status': 'Cancelado'})
        self.assertEqual(cycle.creditos_expirados, 4)
        self.assertEqual(cycle.saldo_utilizavel, 0)
        self.client.post(f'/agenda/{booking.id}/status', data={'status': 'Confirmado'})
        self.assertEqual(booking.status, 'Cancelado')

    def test_renewal_panel_and_first_monthly_contract(self):
        today = date.today()
        old = self.cycle(today - timedelta(days=40), today - timedelta(days=11))
        html = self.client.get('/pacotes/renovacoes').get_data(as_text=True)
        self.assertIn('Bento', html)
        self.assertIn('Aprovar', html)
        response = self.client.post('/pacotes/cliente/novo', data={
            'tutor_id': str(self.tutor.id), 'pet_id': str(self.pet.id), 'pacote_id': str(self.model.id),
            'data_inicio': '2027-01-31', 'data_fim': '2027-03-31', 'quantidade_total': '4', 'valor': '180',
        })
        self.assertEqual(response.status_code, 302)
        created = PacoteCliente.query.filter(PacoteCliente.id != old.id).one()
        self.assertEqual(created.data_fim, date(2027, 2, 27))

    def test_hotel_calculation_and_validation(self):
        self.assertEqual(calcular(date(2030, 1, 10), date(2030, 1, 15), Decimal('80'), 2, Decimal('10')),
                         (5, Decimal('800.00'), Decimal('80.00'), Decimal('720.00')))
        with self.assertRaises(ValueError):
            calcular(date(2030, 1, 10), date(2030, 1, 10), Decimal('80'), 1, Decimal('0'))
        with self.assertRaises(ValueError):
            calcular(date(2030, 1, 10), date(2030, 1, 11), Decimal('80'), 1, Decimal('101'))

    def test_hotel_create_overlap_edit_status_and_price_history(self):
        response = self.client.post('/hotel/novo', data=self.hotel_payload())
        self.assertEqual(response.status_code, 302)
        item = Hospedagem.query.one()
        self.assertEqual((item.diarias, item.total, len(item.pets)), (5, Decimal('720.00'), 2))
        self.assertEqual(self.client.post('/hotel/novo', data=self.hotel_payload()).status_code, 200)
        self.assertEqual(Hospedagem.query.count(), 1)
        self.assertEqual(self.client.post('/hotel/novo', data=self.hotel_payload(pet_ids=[str(self.other_pet.id)])).status_code, 200)
        self.assertEqual(self.client.post('/hotel/configuracoes', data={'diaria_padrao': '100'}).status_code, 200)
        self.assertEqual(db.session.get(HotelConfig, 1).diaria_padrao, Decimal('100.00'))
        self.assertEqual(item.diaria, Decimal('80.00'))
        response = self.client.post(f'/hotel/{item.id}/editar', data=self.hotel_payload(saida='2030-01-14'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(item.total, Decimal('576.00'))
        self.assertEqual(self.client.post(f'/hotel/{item.id}/status', data={'acao': 'checkin'}).status_code, 302)
        self.assertEqual(item.status, 'Hospedado')
        self.assertIsNotNone(item.checkin_em)
        self.client.post(f'/hotel/{item.id}/status', data={'acao': 'checkout'})
        self.assertEqual(item.status, 'Finalizado')
        self.assertIsNotNone(item.checkout_em)

    def test_hotel_cancel_and_bad_inputs(self):
        bad = [self.hotel_payload(saida='2030-01-10'),
               self.hotel_payload(desconto_percentual='101'),
               self.hotel_payload(diaria='-1'),
               self.hotel_payload(pet_ids=[str(self.other_pet.id)])]
        for payload in bad:
            with self.subTest(payload=payload):
                self.assertEqual(self.client.post('/hotel/novo', data=payload).status_code, 200)
                self.assertEqual(Hospedagem.query.count(), 0)
        self.client.post('/hotel/novo', data=self.hotel_payload())
        item = Hospedagem.query.one()
        self.client.post(f'/hotel/{item.id}/status', data={'acao': 'cancelar'})
        self.assertEqual(item.status, 'Cancelado')
        self.assertEqual(self.client.post('/hotel/novo', data=self.hotel_payload()).status_code, 302)

    def test_hotel_finance_payment_and_visibility(self):
        today = date.today()
        self.client.post('/hotel/novo', data=self.hotel_payload(
            entrada=today.isoformat(), saida=(today + timedelta(days=1)).isoformat(),
            desconto_percentual='0'))
        item = Hospedagem.query.one()
        self.assertEqual(item.total, Decimal('160.00'))
        self.client.post(f'/hotel/{item.id}/pagar', data={'forma_pagamento': 'Pix'})
        self.assertFalse(item.pago)

        contexts = []
        def capture(sender, template, context, **extra):
            if template.name == 'financeiro/index.html':
                contexts.append(context)
        template_rendered.connect(capture, self.app)
        try:
            response = self.client.get('/financeiro/')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(contexts[-1]['total_previsto_hotel'], Decimal('160.00'))
            self.assertEqual(contexts[-1]['total_recebido_hotel'], Decimal('0'))
            self.assertEqual(contexts[-1]['total_pendente'], Decimal('160.00'))
            self.assertIn('toggle-values', response.get_data(as_text=True))
            self.assertIn('sensitive-value', response.get_data(as_text=True))

            self.client.post(f'/hotel/{item.id}/pagar', data={
                'data_pagamento': today.isoformat(), 'forma_pagamento': 'Pix'})
            self.assertTrue(item.pago)
            self.assertEqual(item.data_pagamento, today)
            self.assertNotIn('Editar hospedagem', self.client.get(f'/hotel/{item.id}').get_data(as_text=True))
            self.assertEqual(db_total_recebido(today, today), Decimal('160.00'))
            self.client.get('/financeiro/')
            self.assertEqual(contexts[-1]['total_recebido_hotel'], Decimal('160.00'))
            self.assertEqual(contexts[-1]['pagamentos_por_forma'], [('Pix', Decimal('160.00'))])

            self.client.post(f'/hotel/{item.id}/status', data={'acao': 'cancelar'})
            self.assertEqual(item.status, 'Agendado')
            self.client.post(f'/hotel/{item.id}/estornar')
            self.assertFalse(item.pago)
            self.assertIsNone(item.data_pagamento)
            self.assertEqual(db_total_recebido(today, today), Decimal('0'))
            self.client.post(f'/hotel/{item.id}/status', data={'acao': 'cancelar'})
            self.client.get('/financeiro/')
            self.assertEqual(contexts[-1]['total_previsto_hotel'], Decimal('0'))
        finally:
            template_rendered.disconnect(capture, self.app)

    def test_hotel_payment_columns_upgrade_existing_rows(self):
        self.client.post('/hotel/novo', data=self.hotel_payload())
        item_id = Hospedagem.query.one().id
        db.session.remove()
        with db.engine.begin() as connection:
            for column in ('pago', 'data_pagamento', 'forma_pagamento'):
                connection.execute(text(f'ALTER TABLE hospedagens DROP COLUMN {column}'))
        ensure_schema(self.app)
        ensure_schema(self.app)
        columns = {column['name'] for column in inspect(db.engine).get_columns('hospedagens')}
        self.assertTrue({'pago', 'data_pagamento', 'forma_pagamento'} <= columns)
        item = db.session.get(Hospedagem, item_id)
        self.assertFalse(item.pago)
        self.assertIsNone(item.data_pagamento)

    def test_new_pages_render_with_real_records(self):
        cycle = self.cycle(date.today(), date.today() + timedelta(days=29))
        self.client.post('/hotel/novo', data=self.hotel_payload())
        stay = Hospedagem.query.one()
        for path in ['/', '/pacotes/renovacoes', f'/pacotes/cliente/{cycle.id}',
                     '/hotel/', '/hotel/novo', f'/hotel/{stay.id}',
                     f'/hotel/{stay.id}/editar', '/hotel/configuracoes',
                     f'/pets/{self.pet.id}', f'/tutores/{self.tutor.id}']:
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)


if __name__ == '__main__':
    unittest.main()
