import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import g
from sqlalchemy import inspect

from app import create_app, ensure_schema
from app.extensions import db
from app.models import SystemSetting, User
from config import Config


class ChristmasDecorationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.database_url = f"sqlite:///{Path(self.directory.name) / 'petagenda.db'}"
        with patch.object(Config, 'SQLALCHEMY_DATABASE_URI', self.database_url):
            self.app = create_app()
        self.app.config['TESTING'] = True
        self.context = self.app.app_context()
        self.context.push()
        self.admin = User(nome='Admin', email='admin@example.com', senha_hash='unused', role='admin', ativo=True)
        self.common = User(nome='Operador', email='operador@example.com', senha_hash='unused', role='operador', ativo=True)
        db.session.add_all([self.admin, self.common])
        db.session.commit()
        self.client = self.app.test_client()
        self.login(self.admin)

    def tearDown(self):
        db.session.remove()
        db.engine.dispose()
        self.context.pop()
        self.directory.cleanup()

    def login(self, user):
        with self.client.session_transaction() as session:
            session['_user_id'] = str(user.id)
            session['_fresh'] = True
        if hasattr(g, '_login_user'):
            del g._login_user

    def test_admin_toggle_applies_to_shared_pages_and_persists(self):
        self.assertNotIn('class="christmas-enabled"', self.client.get('/').get_data(as_text=True))
        response = self.client.post('/configuracoes/aparencia/natal',
                                    data={'christmas_decoration_enabled': 'true'},
                                    headers={'X-Requested-With': 'XMLHttpRequest'})
        self.assertEqual(response.json, {'christmas_decoration_enabled': True})
        for page in ('/', '/agenda/', '/tutores/', '/pets/', '/pacotes/',
                     '/pacotes/renovacoes', '/hotel/', '/configuracoes/'):
            with self.subTest(page=page):
                html = self.client.get(page).get_data(as_text=True)
                self.assertIn('class="christmas-enabled"', html)
                self.assertIn('christmas-decorations', html)
                if page == '/':
                    self.assertIn('holiday-dashboard-hero', html)
                    self.assertIn('holiday-stat--gift', html)
                elif page != '/configuracoes/':
                    self.assertIn('holiday-module-heading', html)

        admin_id = self.admin.id
        db.session.remove()
        db.engine.dispose()
        self.context.pop()
        with patch.object(Config, 'SQLALCHEMY_DATABASE_URI', self.database_url):
            restarted = create_app()
        self.app = restarted
        restarted.config['TESTING'] = True
        self.context = restarted.app_context()
        self.context.push()
        self.assertEqual(db.session.get(SystemSetting, 'christmas_decoration_enabled').value, 'true')
        restarted_client = restarted.test_client()
        with restarted_client.session_transaction() as session:
            session['_user_id'] = str(admin_id)
            session['_fresh'] = True
        self.assertIn('class="christmas-enabled"', restarted_client.get('/').get_data(as_text=True))

        response = restarted_client.post('/configuracoes/aparencia/natal', data={})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(db.session.get(SystemSetting, 'christmas_decoration_enabled').value, 'false')
        self.assertNotIn('class="christmas-enabled"', restarted_client.get('/').get_data(as_text=True))

    def test_common_user_sees_decoration_but_cannot_change_it(self):
        self.client.post('/configuracoes/aparencia/natal', data={'christmas_decoration_enabled': 'true'})
        self.login(self.common)
        self.assertIn('class="christmas-enabled"', self.client.get('/').get_data(as_text=True))
        self.assertNotIn('Decoração de Natal', self.client.get('/configuracoes/').get_data(as_text=True))
        self.assertEqual(self.client.post('/configuracoes/aparencia/natal', data={}).status_code, 403)
        self.assertEqual(db.session.get(SystemSetting, 'christmas_decoration_enabled').value, 'true')

    def test_additive_upgrade_creates_settings_without_touching_users(self):
        db.session.remove()
        SystemSetting.__table__.drop(db.engine)
        ensure_schema(self.app)
        ensure_schema(self.app)
        self.assertIn('system_settings', inspect(db.engine).get_table_names())
        self.assertEqual(User.query.count(), 2)
        self.assertIsNone(db.session.get(SystemSetting, 'christmas_decoration_enabled'))


if __name__ == '__main__':
    unittest.main()
