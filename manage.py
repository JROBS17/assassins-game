from flask.cli import FlaskGroup
from app import create_app
from extensions import db
from flask_migrate import Migrate

# ✅ Import models so Alembic can detect them
from models import *

app = create_app()
migrate = Migrate(app, db)
cli = FlaskGroup(app)

if __name__ == "__main__":
    cli()
