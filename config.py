import os

basedir = os.path.abspath(os.path.dirname(__file__))

class BaseConfig:
    SECRET_KEY = os.environ.get("SECRET_KEY", "devkey")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = os.path.join(basedir, "static", "uploads")

    # Email settings
    MAIL_SERVER = 'smtp.gmail.com'
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USERNAME = 'jiggerobinson17@gmail.com'
    MAIL_PASSWORD = 'qmwz snxp gsnz ipgh'
    MAIL_DEFAULT_SENDER = 'jiggerobinson17@gmail.com'

class DevConfig(BaseConfig):
    ENV = "development"
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{os.path.join(basedir, 'instance', 'assassins.db')}"

class ProdConfig(BaseConfig):
    ENV = "production"
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL")

# ✅ Make sure this is not indented and is at the top level of the file
config_by_name = {
    'dev': DevConfig,
    'development': DevConfig,
    'prod': ProdConfig,
    'production': ProdConfig
}

