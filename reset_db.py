from flask import Flask
from extensions import db
from models import Player  # ✅ this is correct for a single models.py file

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///assassins.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)

with app.app_context():
    db.drop_all()
    db.create_all()
    print("✅ Database reset.")
   
    print("Database reset.\nTables:")
    for table in db.metadata.tables.values():
        print(f" - {table.name}")
# Print column names for the Player model
    print("\nPlayer table structure:")
    for column in Player.__table__.columns:
        print(f" - {column.name} ({column.type})")

