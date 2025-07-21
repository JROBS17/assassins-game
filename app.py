from flask import Flask
from extensions import db, login_manager
from config import Config
from auth import auth_bp
from routes import routes_bp
from flask_mail import Mail
from itsdangerous import URLSafeTimedSerializer

mail = Mail()
serializer = None  # This will be initialized with app context

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    login_manager.init_app(app)
    mail.init_app(app)

    global serializer
    serializer = URLSafeTimedSerializer(app.config["SECRET_KEY"])

    with app.app_context():
        db.create_all()

    app.register_blueprint(auth_bp)
    app.register_blueprint(routes_bp, url_prefix="/")

    return app

if __name__ == "__main__":
    app = create_app()
    app.run(debug=True)
