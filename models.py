from extensions import db
from flask_login import UserMixin
from datetime import datetime, timedelta

now = datetime.utcnow()
end_time = now + timedelta(hours=72)




class Player(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    profile_pic = db.Column(db.String(200), nullable=True)
    status = db.Column(db.String(20), default="active")
    is_admin = db.Column(db.Boolean, default=False)
    can_be_targeted_multiple_times = db.Column(db.Boolean, default=False)
    max_times_targeted = db.Column(db.Integer, default=1)
    can_have_multiple_contracts = db.Column(db.Boolean, default=False)
    max_contracts_per_round = db.Column(db.Integer, default=1)
    untouchable_count = db.Column(db.Integer, default=0)
    times_kia = db.Column(db.Integer, default=0) 
    actual_name = db.Column(db.String(120), nullable=True)

    


class Contract(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    assassin_id = db.Column(db.Integer, db.ForeignKey("player.id"))
    target_id = db.Column(db.Integer, db.ForeignKey("player.id"))
    status = db.Column(db.String(50), default="assigned")
    round = db.Column(db.Integer, nullable=False, default=1)
    
    assassin = db.relationship("Player", foreign_keys=[assassin_id])
    target = db.relationship("Player", foreign_keys=[target_id])

class Settings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    round_duration = db.Column(db.Integer, default=72)
    repeat_target_delay = db.Column(db.Integer, default=1)
    current_round = db.Column(db.Integer, default=1)
    auto_start_next_round = db.Column(db.Boolean, default=False)
    auto_start_delay_hours = db.Column(db.Integer, default=0) 
    next_round_start_time = db.Column(db.DateTime, nullable=True)


class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey("player.id"))
    message = db.Column(db.String(300))
    is_read = db.Column(db.Boolean, default=False)

class Round(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=False)
    is_active = db.Column(db.Boolean, default=True)

    def duration_in_hours(self):
        return int((self.end_time - self.start_time).total_seconds() / 3600)

class Score(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey("player.id"))
    round_number = db.Column(db.Integer)
    completed_contracts = db.Column(db.Integer, default=0)
    unfinished_contracts = db.Column(db.Integer, default=0)
    eliminations = db.Column(db.Integer, default=0)


class MessageBoard(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class GameRules(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)


class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    author_id = db.Column(db.Integer, db.ForeignKey("player.id"), nullable=False)
    target_id = db.Column(db.Integer, db.ForeignKey("player.id"), nullable=False)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    author = db.relationship("Player", foreign_keys=[author_id], backref="sent_messages")
    target = db.relationship("Player", foreign_keys=[target_id], backref="received_messages")
