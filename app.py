from flask import Flask
from extensions import db, login_manager, mail
from config import Config
from auth import auth_bp
from routes import routes_bp
from flask_mail import Mail
from flask_migrate import Migrate
from itsdangerous import URLSafeTimedSerializer

mail = Mail()
serializer = None
migrate = Migrate()

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    login_manager.init_app(app)
    mail.init_app(app)
    migrate.init_app(app, db)

    global serializer
    serializer = URLSafeTimedSerializer(app.config["SECRET_KEY"])

    # ✅ DO NOT do wildcard import here
    # ❌ from models import *

    app.register_blueprint(auth_bp)
    app.register_blueprint(routes_bp, url_prefix="/")

    return app

