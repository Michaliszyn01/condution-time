import shutil
import uuid
from pathlib import Path

import pytest

from app import create_app
from app.extensions import db


@pytest.fixture()
def tmp_path():
    """Pasta temporária compatível com ambientes Windows/OneDrive restritos."""
    root = (Path.cwd() / ".test-runtime").resolve()
    root.mkdir(parents=True, exist_ok=True)
    target = (root / uuid.uuid4().hex).resolve()
    if root not in target.parents:
        raise RuntimeError("Pasta temporária fora da raiz de testes.")
    target.mkdir()
    try:
        yield target
    finally:
        shutil.rmtree(target, ignore_errors=True)


@pytest.fixture()
def app():
    application = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-key",
            "SQLALCHEMY_DATABASE_URI": "sqlite://",
        }
    )
    with application.app_context():
        db.create_all()
        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()
