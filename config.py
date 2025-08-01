import os

basedir = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "devkey")
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", f"sqlite:///{os.path.join(basedir, 'instance', 'assassins.db')}")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = "static/uploads"


# config.py or directly in app
    MAIL_SERVER = 'smtp.gmail.com'
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USERNAME = 'jiggerobinson17@gmail.com'
    MAIL_PASSWORD = 'qmwz snxp gsnz ipgh'
    MAIL_DEFAULT_SENDER = 'jiggerobinson17@gmail.com'