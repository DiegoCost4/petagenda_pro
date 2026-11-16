"""Valida o upgrade numa cópia SQLite; nunca escreve no banco informado."""
import argparse
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from config import Config
from app import create_app, ensure_schema
from app.extensions import db


def snapshot(connection):
    names = [r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    return {name: connection.execute(f'SELECT count(*) FROM "{name}"').fetchone()[0] for name in names}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("database", type=Path)
    args = parser.parse_args()
    source_path = args.database.resolve()
    if not source_path.is_file():
        parser.error("Banco não encontrado")
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp:
        copy_path = Path(temp.name)
    try:
        with closing(sqlite3.connect(f"file:{source_path.as_posix()}?mode=ro", uri=True)) as source:
            with closing(sqlite3.connect(copy_path)) as target:
                source.backup(target)
                before = snapshot(target)
                before_fk = target.execute("PRAGMA foreign_key_check").fetchall()
        with patch.object(Config, "SQLALCHEMY_DATABASE_URI", f"sqlite:///{copy_path.as_posix()}"):
            app = create_app()
            ensure_schema(app)
            ensure_schema(app)  # idempotência
            with app.app_context():
                db.session.remove()
                db.engine.dispose()
        with closing(sqlite3.connect(copy_path)) as target:
            after = snapshot(target)
            after_fk = target.execute("PRAGMA foreign_key_check").fetchall()
            integrity = target.execute("PRAGMA integrity_check").fetchone()[0]
        assert all(after.get(name) == count for name, count in before.items()), "Contagem de tabela legada mudou"
        assert before_fk == after_fk, "Relacionamentos legados mudaram"
        assert integrity == "ok", integrity
        print(f"Upgrade idempotente validado em cópia: {len(before)} tabelas antigas, contagens e FKs preservadas.")
    finally:
        copy_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
