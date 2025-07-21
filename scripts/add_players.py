# scripts/add_players.py

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app
from extensions import db
from models import Player
from werkzeug.security import generate_password_hash


app = create_app()

with app.app_context():
    db.create_all()  # Ensure tables exist

    # Define sample users
    users = [
        ("Josh", "josh@example.com", "123", True),   # is_admin = True
        ("Alice", "alice@example.com", "123", False),
        ("Bob", "bob@example.com", "123", False),
        ("Charlie", "charlie@example.com", "123", False),
        ("Tom", "tom@example.com", "123", False)
    ]

    for username, email, pw, is_admin in users:
        player = Player(
            username=username,
            email=email,
            password=generate_password_hash(pw),
            is_admin=is_admin,
            can_be_targeted_multiple_times=True,
            max_times_targeted=3,
            can_have_multiple_contracts=True,
            max_contracts_per_round=2
        )
        db.session.add(player)
        print(f"✅ Added {username} {'(Admin)' if is_admin else ''}")

    db.session.commit()
    print("🎯 All players added.")
