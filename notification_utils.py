from extensions import db
from models import Notification

def send_notification(player_id, message):
    note = Notification(player_id=player_id, message=message)
    db.session.add(note)
    db.session.commit()
