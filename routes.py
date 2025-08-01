from flask import Blueprint, render_template, request, redirect, url_for, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from flask import flash
from extensions import db
from models import Contract, Player, Notification, Settings, Round, Message
from notification_utils import send_notification
from models import Score, Player
from extensions import mail
from werkzeug.security import generate_password_hash
from werkzeug.security import check_password_hash
from datetime import datetime, timedelta


import os

routes_bp = Blueprint('routes', __name__)

from datetime import datetime
from models import Round, Contract, Settings, Score, Player

def expire_old_round():
    """If the active round's end_time has passed, end it: expire contracts, log scores, advance/auto-start."""
    current = Round.query.filter_by(is_active=True).first()
    if not current or current.end_time > datetime.utcnow():
        return  # nothing to do

    # mark round as over
    current.is_active = False
    current.end_time = datetime.utcnow()

    # expire any still-assigned contracts
    Contract.query.filter(Contract.status=="assigned").update({"status": "expired"})

    # record scores
    settings = Settings.query.first()
    round_num = settings.current_round if settings else 1
    for p in Player.query.all():
        completed = Contract.query.filter_by(assassin_id=p.id, round=round_num, status="complete").count()
        expired   = Contract.query.filter_by(assassin_id=p.id, round=round_num, status="expired").count()
        eliminated= Contract.query.filter_by(target_id= p.id, round=round_num, status="complete").count()
        db.session.add(Score(
            player_id=p.id,
            round_number=round_num,
            completed_contracts=completed,
            unfinished_contracts=expired,
            eliminations=eliminated
        ))

    # advance settings.current_round and auto-start if desired
    if settings:
        if settings.auto_start_next_round:
            settings.current_round += 1
            # you could immediately create the next Round here,
            # or rely on your existing start_round() to be called somewhere else
        db.session.add(settings)

    db.session.commit()


@routes_bp.route("/")
@login_required
def dashboard():
    expire_old_round() 

    # ❗️Check if current user is being verified (i.e., was tagged)
    is_current_user_being_verified = Contract.query.filter_by(target_id=current_user.id, status="verifying").first()

    # ❗️Only show contracts if user is not under verification
    contracts = []
    if not is_current_user_being_verified:
        contracts = Contract.query.filter_by(assassin_id=current_user.id, status="assigned").all()

    verification_contracts = Contract.query.filter_by(target_id=current_user.id, status="verifying").all()
    notifications = Notification.query.filter_by(player_id=current_user.id).order_by(Notification.id.desc()).all()

    # Get current round number from settings
    settings = Settings.query.first()
    current_round_number = settings.current_round if settings else None

    # Determine if current user has any blocking contract in current round
    is_current_user_locked = Contract.query.filter(
        Contract.target_id == current_user.id,
        Contract.round == current_round_number,
        Contract.status.in_(["verifying"])
    ).first() is not None



    current_round = Round.query.filter_by(is_active=True).first()
    round_end_time = current_round.end_time if current_round else None

    settings = Settings.query.first()
    if (
        settings and
        settings.auto_start_next_round and
        settings.next_round_start_time and
        datetime.utcnow() >= settings.next_round_start_time
    ):
        start_round()  # This should be your existing round-starting function
        settings.next_round_start_time = None
        db.session.commit()
        flash("Next round auto-started.")

    total_completed = Contract.query.filter_by(assassin_id=current_user.id, status="complete").count()
    total_unfinished = Contract.query.filter_by(assassin_id=current_user.id, status="expired").count()
    total_eliminated = Contract.query.filter_by(target_id=current_user.id, status="complete").count()
    kia_count = Contract.query.filter_by(assassin_id=current_user.id, status="KIA").count()
 
    recent_profile_messages = (
        Message.query
        .filter_by(target_id=current_user.id)
        .order_by(Message.timestamp.desc())
        .limit(10)
        .all()
    )

    return render_template(
        "home.html",
        user=current_user,
        contracts=contracts,
        verification_contracts=verification_contracts,
        notifications=notifications,
        total_completed=total_completed,
        total_unfinished=total_unfinished,
        total_eliminated=total_eliminated,
        round_end_time=round_end_time,
        kia_pending_contracts=Contract.query.filter_by(assassin_id=current_user.id, status="kia_pending").all(),
        active_players=Player.query.filter_by(status="active").all(),
        recent_profile_messages=recent_profile_messages,
        is_user_being_verified=bool(is_current_user_being_verified),
        is_current_user_locked=is_current_user_locked,
        kia_count=kia_count

    )





@routes_bp.route("/complete_contract/<int:contract_id>", methods=["POST"])
@login_required
def complete_contract(contract_id):
    contract = Contract.query.get(contract_id)

    if contract and contract.assassin_id == current_user.id and contract.status == "assigned":
        contract.status = "verifying"

        # 🔔 Notify the target that a tag needs their review
        send_notification(contract.target_id, "An Assassination has been submitted. Please confirm or dispute it.")

        db.session.commit()

    return redirect(url_for("routes.dashboard"))



@routes_bp.route("/confirm_tag/<int:contract_id>", methods=["POST"])
@login_required
def confirm_tag(contract_id):
    contract = Contract.query.get(contract_id)

    if contract and contract.target_id == current_user.id:
        action = request.form.get("action")

        if action == "confirm":
            contract.status = "complete"
            send_notification(contract.assassin_id, " Your tag was confirmed!")
            send_notification(contract.target_id, "You were tagged and confirmed.")

            # 🔔 Notify admins
            admins = Player.query.filter_by(is_admin=True).all()
            for admin in admins:
                send_notification(admin.id, f"{contract.assassin.username} confirmed a tag on {contract.target.username}.")

            # ⚠️ ELIMINATION LOGIC — ONLY ON CONFIRM
            Contract.query.filter(
                Contract.assassin_id == contract.target_id,
                Contract.round == contract.round,
                Contract.status == "assigned"
            ).update({"status": "expired"})

            Contract.query.filter(
                Contract.target_id == contract.target_id,
                Contract.round == contract.round,
                Contract.status == "assigned"
            ).update({"status": "expired"})

        elif action == "dispute":
             contract.status = "disputed"
             send_notification(contract.assassin_id, "❌ Your tag was disputed.")

         # 🔔 Notify admins
             admins = Player.query.filter_by(is_admin=True).all()
             for admin in admins:
                 send_notification(admin.id, f"{contract.assassin.username}'s tag on {contract.target.username} was disputed.")

        # ⚠️ Eliminate disputed target from current round
             Contract.query.filter(
                 Contract.target_id == contract.target_id,
                 Contract.round == contract.round,
                  Contract.status == "assigned"
             ).update({"status": "expired"})

             Contract.query.filter(
                 Contract.assassin_id == contract.target_id,
                 Contract.round == contract.round,
                 Contract.status == "assigned"
             ).update({"status": "expired"})


        db.session.commit()

    return redirect(url_for("routes.tag_review"))


@routes_bp.route("/tag_review")
@login_required
def tag_review():
    from models import Contract
    contracts = Contract.query.filter_by(target_id=current_user.id, status="verifying").all()
    return render_template("tag_review.html", contracts=contracts)


@routes_bp.route("/upload_profile_pic", methods=["POST"])
@login_required
def upload_profile_pic():
    if 'pic' not in request.files:
        return redirect(url_for("routes.dashboard"))

    file = request.files['pic']
    if file.filename == '':
        return redirect(url_for("routes.dashboard"))

    filename = secure_filename(file.filename)
    filepath = os.path.join(current_app.config["UPLOAD_FOLDER"], filename)
    file.save(filepath)

    current_user.profile_pic = filename
    db.session.commit()

    return redirect(url_for("routes.dashboard"))


from flask import Blueprint, redirect, url_for
from flask_login import logout_user, login_required

auth_bp = Blueprint("auth", __name__)

@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))


@routes_bp.route("/admin")
@login_required
def admin_panel():
    if not current_user.is_admin:
        return "Unauthorized", 403

    from models import Player, Contract, Round, Settings, MessageBoard


    players = Player.query.all()
    settings = Settings.query.first()
    current_round = Round.query.filter_by(is_active=True).first()
    current_message = MessageBoard.query.order_by(MessageBoard.created_at.desc()).first()


    # Get contracts matching the round number (not the Round.id)
    live_round_number = settings.current_round - 1 if settings else None
    contracts = Contract.query.filter_by(round=live_round_number).all() if live_round_number else []

    return render_template(
        "admin.html",
        players=players,
        contracts=contracts,
        settings=settings,
        current_round=current_round
    )

@routes_bp.route("/toggle_admin", methods=["POST"])
@login_required
def toggle_admin():
    if not current_user.is_admin:
        return "Unauthorized", 403

    from models import Player  # Make sure this is imported at the top

    player_id = request.form.get("player_id")
    is_admin_checkbox = request.form.get("is_admin")  # Will be "on" if checked

    player = Player.query.get(player_id)
    if not player:
        flash("Player not found.")
        return redirect(url_for("routes.admin_panel"))

    # Prevent user from demoting themselves
    if player.id == current_user.id:
        flash("You cannot change your own admin status.")
        return redirect(url_for("routes.admin_panel"))

    player.is_admin = True if is_admin_checkbox else False
    db.session.commit()
    flash(f"{player.username}'s admin status updated.")
    return redirect(url_for("routes.admin_panel"))




@routes_bp.route("/assign_contract", methods=["POST"])
@login_required
def assign_contract():
    if not current_user.is_admin:
        return "Unauthorized", 403

    from models import Contract, Player
    from flask import request

    assassin_id = int(request.form.get("assassin_id"))
    target_id = int(request.form.get("target_id"))

    assassin = Player.query.get(assassin_id)
    target = Player.query.get(target_id)

    # Only assign if both are active and not the same person
    if (
        assassin and target and
        assassin.status == "active" and
        target.status == "active" and
        assassin.id != target.id
    ):
        new_contract = Contract(assassin_id=assassin.id, target_id=target.id)
        db.session.add(new_contract)
        db.session.commit()

    return redirect(url_for("routes.admin_panel"))


@routes_bp.route("/update_contract_status", methods=["POST"])
@login_required
def update_contract_status():
    if not current_user.is_admin:
        return "Unauthorized", 403

    contract_id = request.form.get("contract_id")
    new_status = request.form.get("new_status")

    from models import Contract

    contract = Contract.query.get(contract_id)
    if contract:
        contract.status = new_status
        db.session.commit()
        flash(f"Contract {contract.id} status updated to {new_status}.")
    else:
        flash("Contract not found.")

    return redirect(url_for("routes.admin_panel"))


@routes_bp.route("/toggle_player_status", methods=["POST"])
@login_required
def toggle_player_status():
    if not current_user.is_admin:
        return "Unauthorized", 403

    player_id = int(request.form.get("player_id"))
    player = Player.query.get(player_id)

    if player and not player.is_admin:  # don't suspend admins!
        player.status = "active" if player.status == "suspended" else "suspended"
        db.session.commit()

    return redirect(url_for("routes.admin_panel"))


@routes_bp.route("/update_settings", methods=["POST"])
@login_required
def update_settings():
    if not current_user.is_admin:
        return "Unauthorized", 403

    settings = Settings.query.first()
    if not settings:
        settings = Settings()

    try:
        settings.round_duration = int(request.form.get("round_duration", 72))  # ✅ this line is critical
        settings.repeat_target_delay = int(request.form.get("repeat_target_delay", 1))
        settings.current_round = int(request.form.get("current_round", 1))
        settings.auto_start_next_round = "auto_start_next_round" in request.form
        settings.auto_start_delay_hours = int(request.form.get("auto_start_delay_hours", 0))
    
    except ValueError:
        flash("Invalid values entered. Please use numbers.")
        return redirect(url_for("routes.admin_panel"))

    db.session.add(settings)
    db.session.commit()

    flash("Settings updated successfully.")
    return redirect(url_for("routes.admin_panel"))



@routes_bp.route("/reset_round", methods=["POST"])
@login_required
def reset_round():
    if not current_user.is_admin:
        return "Unauthorized", 403

    from models import Contract, Round, Settings
    from datetime import datetime

    settings = Settings.query.first()
    if not settings:
        flash("Settings not found.")
        return redirect(url_for("routes.admin_panel"))

    # Determine the round number of the current active round
    current_round_number = settings.current_round - 1

    # 🧹 Delete all contracts from the current round only
    Contract.query.filter_by(round=current_round_number).delete()

    # 🟥 Terminate the current round if it's still marked active
    current_round = Round.query.filter_by(is_active=True).first()
    if current_round:
        db.session.delete(current_round)

    # 🚫 Do NOT increment settings.current_round
    db.session.commit()

    flash("🔄 Current round contracts deleted and round reset.")
    return redirect(url_for("routes.admin_panel"))



@routes_bp.route("/qr")
@login_required
def qr_page():
    if not current_user.is_admin:
        return "Unauthorized", 403
    return render_template("qr_page.html")


@routes_bp.route("/update_player_flags", methods=["POST"])
@login_required
def update_player_flags():
    if not current_user.is_admin:
        return "Unauthorized", 403

    players = Player.query.all()
    print("Updating rules for players...")

    for player in players:
        # MULTI CONTRACTS
        multi_contracts_checked = f"multi_contracts_{player.id}" in request.form
        print(f"{player.username}: multi_contracts_checked = {multi_contracts_checked}")
        player.can_have_multiple_contracts = multi_contracts_checked

        max_contracts_str = request.form.get(f"max_contracts_{player.id}", "").strip()
        print(f"{player.username}: max_contracts_str = '{max_contracts_str}'")

        if multi_contracts_checked:
            if not max_contracts_str.isdigit():
                flash(f"Max contracts for {player.username} must be a non-negative number.")
                return redirect(url_for("routes.admin_panel"))
            player.max_contracts_per_round = int(max_contracts_str)
        else:
            player.max_contracts_per_round = 1

        # MULTI TARGETS
        multi_targets_checked = f"multi_targets_{player.id}" in request.form
        print(f"{player.username}: multi_targets_checked = {multi_targets_checked}")
        player.can_be_targeted_multiple_times = multi_targets_checked

        max_targets_str = request.form.get(f"max_targets_{player.id}", "").strip()
        print(f"{player.username}: max_targets_str = '{max_targets_str}'")

        if multi_targets_checked:
            if not max_targets_str.isdigit():
                flash(f"Max targets for {player.username} must be a non-negative number.")
                return redirect(url_for("routes.admin_panel"))
            player.max_times_targeted = int(max_targets_str)  # ✅ Correct attribute here
        else:
            player.max_times_targeted = 1  # ✅ Set fallback if unchecked

    db.session.commit()
    flash("Player rules updated successfully.")
    return redirect(url_for("routes.admin_panel"))

@routes_bp.route("/start_round", methods=["POST"])
@login_required
def start_round():
    if not current_user.is_admin:
        return "Unauthorized", 403

    from datetime import datetime, timedelta
    from models import Settings, Round, Player, Contract
    import random

    # Don't start if a round is already active
    if Round.query.filter_by(is_active=True).first():
        flash("A round is already active.")
        return redirect(url_for("routes.admin_panel"))

    # Ensure settings exist
    settings = Settings.query.first()
    if not settings:
        settings = Settings(round_duration=72, repeat_target_delay=1, current_round=1, auto_start_next_round=False)
        db.session.add(settings)
        db.session.commit()

    # Use settings now safely
    duration = settings.round_duration or 72
    now = datetime.utcnow()

    from models import Notification
    Notification.query.delete()
    
    new_round = Round(
        start_time=now,
        end_time=now + timedelta(hours=duration),
        is_active=True
    )
    db.session.add(new_round)

    # Mark any leftover contracts as expired
    Contract.query.filter(Contract.status == "assigned").update({"status": "expired"})

    players = Player.query.filter_by(status="active").all()
    if len(players) < 2:
        flash("Not enough players to assign contracts.")
        return redirect(url_for("routes.admin_panel"))

    current_round = settings.current_round
    repeat_delay = settings.repeat_target_delay

    remaining_targets = {
        p.id: max(p.max_times_targeted, 0) if p.can_be_targeted_multiple_times else (1 if p.max_times_targeted != 0 else 0)
        for p in players
    }

    contracts = []

    for assassin in players:
        if (not assassin.can_have_multiple_contracts and assassin.max_contracts_per_round == 0) or assassin.max_contracts_per_round == 0:
            continue

        max_contracts = assassin.max_contracts_per_round if assassin.can_have_multiple_contracts else 1

        # Prevent repeat targets
        recent_target_ids = set()
        if repeat_delay > 0:
            recent_contracts = Contract.query.filter(
                Contract.assassin_id == assassin.id,
                Contract.round >= current_round - repeat_delay
            ).all()
            recent_target_ids = {c.target_id for c in recent_contracts}

        possible_targets = [
            p for p in players
            if p.id != assassin.id
            and remaining_targets.get(p.id, 0) > 0
            and (
                (p.can_be_targeted_multiple_times and p.max_times_targeted > 0)
                or (not p.can_be_targeted_multiple_times and p.max_times_targeted != 0)
            )
            and (repeat_delay == 0 or p.id not in recent_target_ids)
        ]

        random.shuffle(possible_targets)
        count = 0

        for target in possible_targets:
            if count >= max_contracts:
                break

            contracts.append(Contract(
                assassin_id=assassin.id,
                target_id=target.id,
                round=current_round,
                status="assigned"
            ))
            remaining_targets[target.id] -= 1
            count += 1

    for contract in contracts:
        db.session.add(contract)

    # Advance round count
    settings.current_round += 1
    db.session.add(settings)

    db.session.commit()
    flash(f"New round started and {len(contracts)} contracts assigned.")
    return redirect(url_for("routes.admin_panel"))


@routes_bp.route("/end_round", methods=["POST"])
@login_required
def end_round():
    if not current_user.is_admin:
        return "Unauthorized", 403

    from models import Round, Contract, Settings, Score, Player
    from datetime import datetime, timedelta
    import time

    current_round = Round.query.filter_by(is_active=True).first()
    if not current_round:
        flash("No active round to end.")
        return redirect(url_for("routes.admin_panel"))

    # End the current round
    current_round.end_time = datetime.utcnow()
    current_round.is_active = False

    # Expire all uncompleted contracts
    Contract.query.filter(Contract.status == "assigned").update({"status": "expired"})

    # Get current round number
    settings = Settings.query.first()
    round_num = settings.current_round if settings else 1

    # Calculate and save scores for each player
    players = Player.query.all()
    for player in players:
        completed = Contract.query.filter_by(
            assassin_id=player.id,
            round=round_num,
            status="complete"
        ).count()

        expired = Contract.query.filter_by(
            assassin_id=player.id,
            round=round_num,
            status="expired"
        ).count()

        eliminated = Contract.query.filter_by(
            target_id=player.id,
            round=round_num,
            status="complete"
        ).count()

        score = Score(
            player_id=player.id,
            round_number=round_num,
            completed_contracts=completed,
            unfinished_contracts=expired,
            eliminations=eliminated
        )
        db.session.add(score)

    db.session.commit()
    flash("Round ended. Contracts expired. Scores logged.")

    
 # Auto-start logic
    if settings and settings.auto_start_next_round:
        delay_hours = settings.auto_start_delay_hours or 0
        if delay_hours > 0:
            flash(f"Next round will start in {delay_hours} hour(s)...")
            settings.next_round_start_time = datetime.utcnow() + timedelta(hours=delay_hours)
            db.session.commit()
        else: 
            start_round()
            flash("Next round auto-started.")
    return redirect(url_for("routes.admin_panel"))


@routes_bp.route("/contract_history")
@login_required
def view_all_contracts():
    if not current_user.is_admin:
        return "Unauthorized", 403

    from models import Contract

    all_contracts = Contract.query.order_by(Contract.round.desc()).all()
    return render_template("contract_history.html", contracts=all_contracts)

@routes_bp.route("/leaderboard")
@login_required
def leaderboard():
    from models import Contract, Player, Round, Settings, MessageBoard
    from sqlalchemy import or_

    current_round = Round.query.filter_by(is_active=True).first()
    round_end_time = current_round.end_time if current_round else None
    message = MessageBoard.query.order_by(MessageBoard.id.desc()).first()
    untouchables = (
    db.session.query(Player.username, Player.untouchable_count)
    .filter(Player.untouchable_count > 0)
    .order_by(Player.untouchable_count.desc())
    .limit(5)
    .all()
)


    # 🔥 LIVE Leaderboard: Completed contracts for current round
    live_leaderboard_query = (
        db.session.query(Player.username, db.func.count(Contract.id))
        .join(Contract, Player.id == Contract.assassin_id)
        .filter(Contract.status == "complete")
    )

    if current_round:
        live_leaderboard_query = live_leaderboard_query.filter(Contract.round == current_round.id)
    else:
        live_leaderboard_query = live_leaderboard_query.filter(False)

    live_leaderboard = (
        live_leaderboard_query
        .group_by(Player.username)
        .order_by(db.func.count(Contract.id).desc())
        .all()
    )

    # 🏆 Overall stats
    most_completions = (
        db.session.query(Player.username, db.func.count(Contract.id).label("total"))
        .join(Contract, Player.id == Contract.assassin_id)
        .filter(Contract.status == "complete")
        .group_by(Player.username)
        .order_by(db.desc("total"))
        .limit(5)
        .all()
    )

    most_eliminated = (
        db.session.query(Player.username, db.func.count(Contract.id).label("elims"))
        .join(Contract, Player.id == Contract.target_id)
        .filter(Contract.status == "complete")
        .group_by(Player.username)
        .order_by(db.desc("elims"))
        .limit(5)
        .all()
    )

    # 📜 Live Killfeed: Show KIA and Complete for this round
    live_killfeed = []
    if current_round:
        live_killfeed = (
            Contract.query
            .filter(
                Contract.round == current_round.id,
                Contract.status.in_(["complete", "KIA"])
            )
            .order_by(Contract.id.desc())
            .all()
        )

    return render_template(
        "leaderboard.html",
        current_round=current_round,
        live_leaderboard=live_leaderboard,
        overall_leaderboard=most_completions,
        most_eliminated=most_eliminated,
        message=message,
        live_killfeed=live_killfeed,  # ✅ Pass to template
        untouchables=untouchables,  # ✅ new
        round_end_time=round_end_time
    )



@routes_bp.route("/update_message", methods=["POST"])
@login_required
def update_message():
    if not current_user.is_admin:
        return "Unauthorized", 403

    from models import MessageBoard
    from datetime import datetime

    content = request.form.get("message")
    if content:
        new_message = MessageBoard(content=content, created_at=datetime.utcnow())
        db.session.add(new_message)
        db.session.commit()
        flash("Admin message updated.")

    return redirect(url_for("routes.admin_panel"))


@routes_bp.route("/rules")
def rules_page():
    from models import GameRules
    rules = GameRules.query.first()
    return render_template("rules.html", rules=rules)



@routes_bp.route("/update_rules", methods=["POST"])
@login_required
def update_rules():
    if not current_user.is_admin:
        return "Unauthorized", 403

    from models import GameRules
    rules = GameRules.query.first()
    if not rules:
        rules = GameRules()

    rules.content = request.form.get("rules_text", "")
    db.session.add(rules)
    db.session.commit()
    flash("Rules updated.")
    return redirect(url_for("routes.admin_panel"))


from flask_mail import Message as MailMessage
from flask import current_app, url_for
from itsdangerous import URLSafeTimedSerializer
from models import Player

def send_reset_email(user):
    serializer = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    token = serializer.dumps(user.email, salt='password-reset')

    reset_url = url_for('routes.reset_with_token', token=token, _external=True)
    msg = MailMessage('Password Reset Request',
                  recipients=[user.email])
    msg.body = f"""Hello {user.username},

To reset your password, click the link below:
{reset_url}

If you did not request this, simply ignore this email.
"""
    mail.send(msg)

@routes_bp.route("/request_reset", methods=["GET", "POST"])
def request_reset():
    if request.method == "POST":
        email = request.form.get("email")
        user = Player.query.filter_by(email=email).first()
        if user:
            send_reset_email(user)
            flash("Password reset email sent!", "info")
        else:
            flash("Email not found.", "danger")
        return redirect(url_for("auth.login"))

    return render_template("request_reset.html")

@routes_bp.route("/reset/<token>", methods=["GET", "POST"])
def reset_with_token(token):
    serializer = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    try:
        email = serializer.loads(token, salt='password-reset', max_age=3600)
    except:
        flash("The reset link is invalid or expired.", "danger")
        return redirect(url_for("auth.login"))

    user = Player.query.filter_by(email=email).first_or_404()

    if request.method == "POST":
        new_password = request.form.get("new_password")
        user.password = generate_password_hash(new_password)
        db.session.commit()
        flash("Password reset successful!", "success")
        return redirect(url_for("auth.login"))

    return render_template("reset_password.html")

from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
import os
from extensions import db
from models import Player
from config import Config

@routes_bp.route("/profile/edit", methods=["GET", "POST"])
@login_required
def edit_profile():
    if request.method == "POST":
        username = request.form.get("username")
        email = request.form.get("email")
        profile_pic = request.files.get("profile_pic")

        if username:
            current_user.username = username

        if email:
            current_user.email = email

        if profile_pic:
            filename = secure_filename(profile_pic.filename)
            filepath = os.path.join(Config.UPLOAD_FOLDER, filename)
            profile_pic.save(filepath)
            current_user.profile_pic = filename

        db.session.commit()
        flash("Profile updated successfully!", "success")
        return redirect(url_for("routes.edit_profile"))

    return render_template("edit_profile.html", user=current_user)

@routes_bp.route("/admin/delete_player/<int:player_id>", methods=["POST"])
@login_required
def delete_player(player_id):
    if not current_user.is_admin:
        abort(403)

    player = Player.query.get_or_404(player_id)

    if player.id == current_user.id:
        flash("You cannot delete your own account.")
        return redirect(url_for("routes.admin_panel"))

    # Delete related messages
    db.session.query(Message).filter_by(author_id=player.id).delete()

    # Delete related contracts
    Contract.query.filter(
        (Contract.assassin_id == player.id) | (Contract.target_id == player.id)
    ).delete()

    # Now delete the player
    db.session.delete(player)
    db.session.commit()
    flash(f"Player {player.username} has been deleted.")
    return redirect(url_for("routes.admin_panel"))



@routes_bp.route('/profile/<username>')
@login_required
def player_profile(username):
    from models import Player, Contract, Message
    from sqlalchemy import desc

    player = Player.query.filter_by(username=username).first_or_404()

    total_completed = Contract.query.filter_by(assassin_id=current_user.id, status="complete").count()
    total_unfinished = Contract.query.filter_by(assassin_id=current_user.id, status="expired").count()
    total_eliminated = Contract.query.filter_by(target_id=current_user.id, status="complete").count()
    kia_count = Contract.query.filter_by(assassin_id=current_user.id, status="KIA").count()

    # Handle message view toggle
    show_all = request.args.get("show_all") == "1"

    all_messages_query = Message.query.filter_by(target_id=player.id).order_by(desc(Message.timestamp))
    
    # Enforce storage limit of 100 messages
    all_messages = all_messages_query.all()
    if len(all_messages) > 100:
        for msg in all_messages[100:]:  # prune oldest
            db.session.delete(msg)
        db.session.commit()

    # Only show 10 if not toggled
    messages = all_messages[:10] if not show_all else all_messages[:100]  # max display 100

    return render_template(
        "player_profile.html",
        player=player,
        messages=messages,
        message_count=len(all_messages),
        show_all=show_all,
        total_completed=total_completed,
        total_unfinished=total_unfinished,
        total_eliminated=total_eliminated,
        kia_count=kia_count

    )


@routes_bp.route('/leave_message', methods=["POST"])
@login_required
def leave_message():
    from models import Message
    target_id = request.form["target_id"]
    content = request.form["message_text"]

    message = Message(author_id=current_user.id, target_id=target_id, content=content)
    db.session.add(message)
    db.session.commit()

    return redirect(request.referrer or url_for("routes.index"))


@routes_bp.route("/admin/resolve_disputes", methods=["POST"])
@login_required
def resolve_disputes():
    if not current_user.is_admin:
        return "Unauthorized", 403

    from models import Contract

    disputed_contracts = Contract.query.filter_by(status="disputed").all()

    for contract in disputed_contracts:
        # Reactivate the disputed contract
        contract.status = "assigned"

        # 🛠 Reactivate the target's own contract if it was expired
        target_contract = Contract.query.filter_by(
            assassin_id=contract.target_id,
            round=contract.round,
            status="expired"
        ).first()

        if target_contract:
            target_contract.status = "assigned"

    db.session.commit()
    flash("All disputed contracts have been resolved and reactivated.")
    return redirect(url_for("routes.admin_panel"))

@routes_bp.route("/submit_kia", methods=["POST"])
@login_required
def submit_kia():
    from models import Contract, Player
    from sqlalchemy import or_
    from notification_utils import send_notification  
    
    suspect_id = int(request.form.get("suspect_id"))

    # Look for an assigned contract where the suspect is the assassin and current_user is the target
    contract = Contract.query.filter_by(
        assassin_id=suspect_id,
        target_id=current_user.id,
        status="assigned"
    ).first()

    if not contract:
        flash("Verifying...")
        return redirect(url_for("routes.dashboard"))

    # 🔁 Instead of marking KIA immediately, set to pending
    contract.status = "kia_pending"

    # 🔔 Notify the assassin to verify or dispute
    send_notification(
        contract.assassin_id,
        f" You've been reported KIA by {current_user.username}. Please confirm or dispute."
    )

    db.session.commit()
    flash("Verifying...")
    return redirect(url_for("routes.dashboard"))



@routes_bp.route("/kia_review")
@login_required
def kia_review():
    contracts = Contract.query.filter_by(assassin_id=current_user.id, status="kia_pending").all()
    return render_template("kia_review.html", contracts=contracts)

@routes_bp.route("/confirm_kia/<int:contract_id>", methods=["POST"])
@login_required
def confirm_kia(contract_id):
    from notification_utils import send_notification 

    contract = Contract.query.get_or_404(contract_id)

    if contract.assassin_id != current_user.id or contract.status != "kia_pending":
        flash("You are not authorized to review this KIA.")
        return redirect(url_for("routes.dashboard"))

    action = request.form.get("action")

    if action == "confirm":
        contract.status = "KIA"

        from sqlalchemy import or_
        related = Contract.query.filter(
            or_(
                Contract.assassin_id == current_user.id,
                Contract.target_id == current_user.id
            ),
            Contract.round == contract.round,
            Contract.status == "assigned"
        ).all()

        for c in related:
            if c.id != contract.id:
                c.status = "expired"

        contract.target.untouchable_count += 1
        # Notify target before commit
        send_notification(contract.target_id, "Your KIA was CONFIRMED.")        

        # Note: untouchable_count increment should have occurred in submit_kia()
        db.session.commit()
        flash("You have been Killed in action. You're out for this round.")
        

    elif action == "dispute":
        contract.status = "kia_disputed"
        db.session.commit()

        # Notify the target
        from notification_utils import send_notification
        send_notification(contract.target_id, " Your KIA claim was DISPUTED.")

        # Notify admins
        admins = Player.query.filter_by(is_admin=True).all()
        for admin in admins:
            send_notification(admin.id, f"KIA dispute: {contract.assassin.username} denied {contract.target.username}'s claim.")

        flash("You disputed the KIA. An admin will review.")

    return redirect(url_for("routes.dashboard"))

@routes_bp.route("/admin/resolve_kia_disputes", methods=["POST"])
@login_required
def resolve_kia_disputes():
    if not current_user.is_admin:
        return "Unauthorized", 403

    from models import Contract
    from sqlalchemy import or_

    kia_disputed_contracts = Contract.query.filter_by(status="kia_disputed").all()

    for contract in kia_disputed_contracts:
        # ✅ Default behavior: reject KIA, restore contract to "assigned"
        contract.status = "assigned"

        # Optionally notify the involved players
        from notification_utils import send_notification
        send_notification(contract.target_id, f"Your KIA claim on {contract.assassin.username} was denied.")
        send_notification(contract.assassin_id, "You have been cleared. KIA claim was rejected.")

    db.session.commit()
    flash("All KIA disputes reviewed. Disputed contracts reset to 'assigned'.")
    return redirect(url_for("routes.admin_panel"))