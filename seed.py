'''
from app import create_app
from extensions import db
from models import Player  # Make sure this is your user model
from werkzeug.security import generate_password_hash

app = create_app()

with app.app_context():
    existing_admin = Player.query.filter_by(username="AdMiN").first()

    if not existing_admin:
        admin = Player(
            username="AdMiN",
            email="jiggerobinson17@gmail.com",
            is_admin=True
        )
        admin.set_password("Lander13@")  # assuming you have a set_password method
        db.session.add(admin)
        db.session.commit()
        print("✅ Admin user created.")
    else:
        print("ℹ️ Admin user already exists.")
'''