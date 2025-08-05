from flask import Flask
from extensions import db, login_manager, mail
from config import config_by_name
from auth import auth_bp
from routes import routes_bp
from flask_mail import Mail
from flask_migrate import Migrate
from itsdangerous import URLSafeTimedSerializer
import os

mail = Mail()
serializer = None
migrate = Migrate()

def create_app():
    app = Flask(__name__)

    config_name = os.getenv("FLASK_ENV", "dev").lower()

    if config_name not in config_by_name:
        raise ValueError(f"❌ Invalid FLASK_ENV: '{config_name}'. Must be one of {list(config_by_name.keys())}")

    print(f"🔁 Loading config for: {config_name}")
    app.config.from_object(config_by_name[config_name])


    # Logging environment and DB info for verification
    
    print("✅ Config loaded:", config_by_name[config_name].__name__)
    print("🔧 ENVIRONMENT:", app.config.get("ENV", "unknown"))
    print("🗃️ DB URI:", app.config.get("SQLALCHEMY_DATABASE_URI", "not set"))

    db.init_app(app)
    login_manager.init_app(app)
    mail.init_app(app)
    migrate.init_app(app, db)

    global serializer
    serializer = URLSafeTimedSerializer(app.config["SECRET_KEY"])

    app.register_blueprint(auth_bp)
    app.register_blueprint(routes_bp, url_prefix="/")

    return app

# Only used when running directly, not in production via gunicorn
if __name__ == "__main__":
    app = create_app()
    app.run(debug=True)
