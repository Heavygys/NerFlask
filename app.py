import calendar
import io
import mimetypes
import os
import re
import secrets
import smtplib
from decimal import Decimal, InvalidOperation
from datetime import date, datetime, timedelta
from email.message import EmailMessage
from functools import wraps
from urllib.parse import urlencode

import requests
from dotenv import load_dotenv
from flask import Flask, abort, flash, redirect, render_template, request, send_file, session, url_for
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import or_, text
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename


db = SQLAlchemy()

load_dotenv()


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    first_name = db.Column(db.String(80), nullable=True)
    last_name = db.Column(db.String(80), nullable=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="member")
    provider = db.Column(db.String(50), nullable=True, default="local")
    provider_user_id = db.Column(db.String(120), nullable=True)
    reset_token = db.Column(db.String(255), nullable=True)
    reset_token_expires = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Member(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(80), nullable=False)
    last_name = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone = db.Column(db.String(20), nullable=True)
    mobile = db.Column(db.String(30), nullable=True)
    home_phone = db.Column(db.String(30), nullable=True)
    address_1 = db.Column(db.String(255), nullable=True)
    address_2 = db.Column(db.String(255), nullable=True)
    town = db.Column(db.String(120), nullable=True)
    city = db.Column(db.String(120), nullable=True)
    postcode = db.Column(db.String(20), nullable=True)
    membership_type = db.Column(db.String(50), default="Standard")
    status = db.Column(db.String(20), default="Active")
    join_date = db.Column(db.DateTime, default=datetime.utcnow)
    notes = db.Column(db.Text, nullable=True)

    certifications = db.relationship(
        "Certification", backref="member", lazy=True, cascade="all, delete-orphan"
    )
    boats = db.relationship("Boat", backref="member", lazy=True, cascade="all, delete-orphan")
    events = db.relationship("Event", secondary="event_members", backref="members", lazy=True)


class Qualification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    category = db.Column(db.String(80), nullable=False)
    description = db.Column(db.Text, nullable=True)


class LookupItem(db.Model):
    """Admin-managed dropdown values, grouped by category (e.g. membership_type, member_status)."""

    id = db.Column(db.Integer, primary_key=True)
    category = db.Column(db.String(80), nullable=False)
    value = db.Column(db.String(120), nullable=False)
    sort_order = db.Column(db.Integer, default=0)

    __table_args__ = (db.UniqueConstraint("category", "value", name="uq_lookup_category_value"),)


class Certification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey("member.id"), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    certification_number = db.Column(db.String(80), nullable=True)
    issue_date = db.Column(db.Date, nullable=False)
    expiry_date = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(30), default="Valid")
    certificate_copy = db.Column(db.String(255), nullable=True)
    certificate_data = db.Column(db.LargeBinary, nullable=True)
    certificate_filename = db.Column(db.String(255), nullable=True)
    certificate_content_type = db.Column(db.String(120), nullable=True)


class Boat(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey("member.id"), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    registration = db.Column(db.String(80), nullable=True)
    boat_type = db.Column(db.String(50), nullable=True)
    length = db.Column(db.String(20), nullable=True)
    year = db.Column(db.Integer, nullable=True)
    engine = db.Column(db.String(80), nullable=True)
    mmsi_number = db.Column(db.String(20), nullable=True)
    ssr_number = db.Column(db.String(80), nullable=True)
    vhf = db.Column(db.Boolean, nullable=False, default=False)
    ais = db.Column(db.Boolean, nullable=False, default=False)
    notes = db.Column(db.Text, nullable=True)


event_members = db.Table(
    "event_members",
    db.Column("event_id", db.Integer, db.ForeignKey("event.id"), primary_key=True),
    db.Column("member_id", db.Integer, db.ForeignKey("member.id"), primary_key=True),
)


class Event(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    date_from = db.Column(db.Date, nullable=False)
    date_to = db.Column(db.Date, nullable=True)
    boats_needed = db.Column(db.Integer, nullable=True, default=0)
    notes = db.Column(db.Text, nullable=True)
    what3words_location_1 = db.Column(db.String(120), nullable=True)
    what3words_location_2 = db.Column(db.String(120), nullable=True)
    what3words_location_3 = db.Column(db.String(120), nullable=True)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    tide_data = db.Column(db.JSON, nullable=True)
    tide_error = db.Column(db.String(255), nullable=True)


class EventDocument(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey("event.id"), nullable=False)
    description = db.Column(db.String(255), nullable=False)
    document_data = db.Column(db.LargeBinary, nullable=False)
    document_filename = db.Column(db.String(255), nullable=False)
    document_content_type = db.Column(db.String(120), nullable=False)
    uploaded_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    event = db.relationship("Event", backref=db.backref("documents", lazy=True, cascade="all, delete-orphan"))
    uploaded_by = db.relationship("User", foreign_keys=[uploaded_by_user_id])


class EventExpense(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey("event.id"), nullable=False)
    member_id = db.Column(db.Integer, db.ForeignKey("member.id"), nullable=False)
    expense_type = db.Column(db.String(120), nullable=False)
    expense_date = db.Column(db.Date, nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    approved_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    receipt_image = db.Column(db.String(255), nullable=True)
    receipt_data = db.Column(db.LargeBinary, nullable=True)
    receipt_filename = db.Column(db.String(255), nullable=True)
    receipt_content_type = db.Column(db.String(120), nullable=True)
    status = db.Column(db.String(20), nullable=False, default="Pending")
    reviewed_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    paid_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    paid_at = db.Column(db.DateTime, nullable=True)

    event = db.relationship("Event", backref=db.backref("expenses", lazy=True, cascade="all, delete-orphan"))
    member = db.relationship("Member", backref=db.backref("event_expenses", lazy=True, cascade="all, delete-orphan"))
    approved_by = db.relationship("User", foreign_keys=[approved_by_user_id])
    reviewed_by = db.relationship("User", foreign_keys=[reviewed_by_user_id])
    paid_by = db.relationship("User", foreign_keys=[paid_by_user_id])


class EventParticipation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey("event.id"), nullable=False)
    member_id = db.Column(db.Integer, db.ForeignKey("member.id"), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="Pending")
    approved_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    approved_at = db.Column(db.DateTime, nullable=True)

    event = db.relationship("Event", backref=db.backref("participations", lazy=True, cascade="all, delete-orphan"))
    member = db.relationship("Member", backref=db.backref("event_participations", lazy=True, cascade="all, delete-orphan"))
    approved_by = db.relationship("User", foreign_keys=[approved_by_user_id])

    __table_args__ = (db.UniqueConstraint("event_id", "member_id", name="uq_event_participation"),)


def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if not session.get("user_id"):
            flash("Please log in to access the dashboard.")
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped_view


def is_strong_password(password):
    if len(password) < 8:
        return False
    if not re.search(r"[a-z]", password):
        return False
    if not re.search(r"[A-Z]", password):
        return False
    if not re.search(r"\d", password):
        return False
    if not re.search(r"[^A-Za-z0-9]", password):
        return False
    return True


def normalize_what3words(value):
    address = value.strip().lower()
    if not address:
        return None
    address = address.removeprefix("https://what3words.com/").removeprefix("http://what3words.com/")
    address = address.lstrip("/").split("?", 1)[0].rstrip("/")
    if not re.fullmatch(r"[a-z0-9-]+\.[a-z0-9-]+\.[a-z0-9-]+", address):
        raise ValueError
    return address


def parse_coordinates(latitude_value, longitude_value):
    if not latitude_value.strip() and not longitude_value.strip():
        return None, None
    try:
        latitude = float(latitude_value)
        longitude = float(longitude_value)
    except ValueError:
        raise ValueError
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise ValueError
    return latitude, longitude


def get_event_participation(event_id, member_id):
    return EventParticipation.query.filter_by(event_id=event_id, member_id=member_id).first()


def get_event_tides(event):
    api_key = os.getenv("TIDECHECK_API_KEY")
    if event.latitude is None or event.longitude is None:
        return None, "Add latitude and longitude to this event to view tide times."
    if not api_key:
        return None, "Tide times are unavailable until TIDECHECK_API_KEY is configured."

    headers = {"X-API-Key": api_key}
    try:
        station_response = requests.get(
            "https://tidecheck.com/api/stations/nearest",
            params={"lat": event.latitude, "lng": event.longitude},
            headers=headers,
            timeout=10,
        )
        station_response.raise_for_status()
        stations = station_response.json()
        if not stations:
            return None, "No TideCheck station was found near this event."

        station = stations[0]
        tide_response = requests.get(
            f"https://tidecheck.com/api/station/{station['id']}/tides",
            params={"start": event.date_from.isoformat(), "days": 1, "datum": "LAT"},
            headers=headers,
            timeout=10,
        )
        tide_response.raise_for_status()
        tide_data = tide_response.json()
    except (requests.RequestException, KeyError, ValueError):
        return None, "Tide times could not be loaded from TideCheck."

    extremes = []
    for extreme in tide_data.get("extremes", []):
        if extreme.get("localDate") != event.date_from.isoformat():
            continue
        try:
            time = datetime.fromisoformat(extreme["localTime"]).strftime("%H:%M")
            height = float(extreme["height"])
        except (KeyError, TypeError, ValueError):
            continue
        extremes.append({"type": extreme.get("type", "").title(), "time": time, "height": height})

    return {"station": station.get("name", "Nearest station"), "extremes": extremes}, None


def refresh_event_tides(event):
    event.tide_data, event.tide_error = get_event_tides(event)


def ensure_member_for_user(user):
    if not user or not user.email:
        return None

    member = Member.query.filter_by(email=user.email).first()
    if not member:
        member = Member(
            first_name=user.first_name or "",
            last_name=user.last_name or "",
            email=user.email,
            membership_type="Standard",
            status="Active",
        )
        db.session.add(member)
    else:
        if user.first_name and not member.first_name:
            member.first_name = user.first_name
        if user.last_name and not member.last_name:
            member.last_name = user.last_name
        if member.email != user.email:
            member.email = user.email
        if not member.status:
            member.status = "Active"

    db.session.flush()
    return member


LOOKUP_CATEGORIES = {
    "membership_type": "Membership Types",
    "member_status": "Member Statuses",
    "certification_status": "Certification Statuses",
    "expense_type": "Expense Types",
}


def get_lookup_values(category):
    items = (
        LookupItem.query.filter_by(category=category)
        .order_by(LookupItem.sort_order, LookupItem.value)
        .all()
    )
    return [item.value for item in items]


def role_required(*allowed_roles):
    def decorator(view):
        @wraps(view)
        def wrapped_view(*args, **kwargs):
            if session.get("role") not in allowed_roles:
                flash("You do not have permission to access this page.")
                return redirect(url_for("home"))
            return view(*args, **kwargs)

        return wrapped_view

    return decorator


def ensure_database_schema():
    db.create_all()

    try:
        user_columns = db.session.execute(text("PRAGMA table_info(user)")).fetchall()
        user_names = {row[1] for row in user_columns}

        if "username" in user_names:
            db.session.execute(text("ALTER TABLE user RENAME TO user_old"))
            db.session.execute(
                text(
                    """
                    CREATE TABLE user (
                        id INTEGER NOT NULL PRIMARY KEY,
                        email VARCHAR(120) NOT NULL UNIQUE,
                        first_name VARCHAR(80),
                        last_name VARCHAR(80),
                        password_hash VARCHAR(255) NOT NULL,
                        role VARCHAR(20) NOT NULL,
                        provider VARCHAR(50),
                        provider_user_id VARCHAR(120),
                        reset_token VARCHAR(255),
                        reset_token_expires DATETIME,
                        created_at DATETIME
                    )
                    """
                )
            )
            db.session.execute(
                text(
                    """
                    INSERT INTO user (
                        id, email, first_name, last_name, password_hash, role,
                        provider, provider_user_id, reset_token, reset_token_expires, created_at
                    )
                    SELECT id, email, first_name, last_name, password_hash, role,
                           provider, provider_user_id, reset_token, reset_token_expires, created_at
                    FROM user_old
                    """
                )
            )
            db.session.execute(text("DROP TABLE user_old"))

        user_columns = db.session.execute(text("PRAGMA table_info(user)")).fetchall()
        user_names = {row[1] for row in user_columns}
        for column_name, column_def in {
            "email": "VARCHAR(120)",
            "first_name": "VARCHAR(80)",
            "last_name": "VARCHAR(80)",
            "provider": "VARCHAR(50)",
            "provider_user_id": "VARCHAR(120)",
            "reset_token": "VARCHAR(255)",
            "reset_token_expires": "DATETIME",
        }.items():
            if column_name not in user_names:
                db.session.execute(text(f"ALTER TABLE user ADD COLUMN {column_name} {column_def}"))
                if column_name == "email":
                    db.session.execute(text("UPDATE user SET email = '' WHERE email IS NULL"))
    except Exception:
        pass

    try:
        qualification_columns = db.session.execute(text("PRAGMA table_info(qualification)")).fetchall()
        qualification_names = {row[1] for row in qualification_columns}
        if "qualification" not in db.metadata.tables:
            return
        if "id" not in qualification_names or "name" not in qualification_names:
            db.create_all()
    except Exception:
        pass

    try:
        member_columns = db.session.execute(text("PRAGMA table_info(member)")).fetchall()
        member_names = {row[1] for row in member_columns}
        for column_name, column_def in {
            "mobile": "VARCHAR(30)",
            "home_phone": "VARCHAR(30)",
            "address_1": "VARCHAR(255)",
            "address_2": "VARCHAR(255)",
            "town": "VARCHAR(120)",
            "city": "VARCHAR(120)",
            "postcode": "VARCHAR(20)",
        }.items():
            if column_name not in member_names:
                db.session.execute(text(f"ALTER TABLE member ADD COLUMN {column_name} {column_def}"))
    except Exception:
        pass

    try:
        boat_columns = db.session.execute(text("PRAGMA table_info(boat)")).fetchall()
        boat_names = {row[1] for row in boat_columns}
        for column_name, column_type in {
            "mmsi_number": "VARCHAR(20)",
            "ssr_number": "VARCHAR(80)",
            "vhf": "BOOLEAN NOT NULL DEFAULT 0",
            "ais": "BOOLEAN NOT NULL DEFAULT 0",
        }.items():
            if column_name not in boat_names:
                db.session.execute(text(f"ALTER TABLE boat ADD COLUMN {column_name} {column_type}"))
    except Exception:
        pass

    try:
        certification_columns = db.session.execute(text("PRAGMA table_info(certification)")).fetchall()
        certification_names = {row[1] for row in certification_columns}
        for column_name, column_type in {
            "certificate_copy": "VARCHAR(255)",
            "certificate_data": "BLOB",
            "certificate_filename": "VARCHAR(255)",
            "certificate_content_type": "VARCHAR(120)",
        }.items():
            if column_name not in certification_names:
                db.session.execute(text(f"ALTER TABLE certification ADD COLUMN {column_name} {column_type}"))
    except Exception:
        pass

    try:
        expense_columns = db.session.execute(text("PRAGMA table_info(event_expense)")).fetchall()
        expense_names = {row[1] for row in expense_columns}
        for column_name, column_type in {
            "status": "VARCHAR(20) NOT NULL DEFAULT 'Pending'",
            "reviewed_by_user_id": "INTEGER",
            "reviewed_at": "DATETIME",
            "paid_by_user_id": "INTEGER",
            "paid_at": "DATETIME",
            "receipt_data": "BLOB",
            "receipt_filename": "VARCHAR(255)",
            "receipt_content_type": "VARCHAR(120)",
        }.items():
            if column_name not in expense_names:
                db.session.execute(text(f"ALTER TABLE event_expense ADD COLUMN {column_name} {column_type}"))
    except Exception:
        pass

    try:
        event_columns = db.session.execute(text("PRAGMA table_info(event)")).fetchall()
        if event_columns:
            event_names = {row[1] for row in event_columns}
            if "member_id" in event_names:
                db.session.execute(text("ALTER TABLE event RENAME TO event_old"))
                db.session.execute(
                    text(
                        """
                        CREATE TABLE event (
                            id INTEGER NOT NULL PRIMARY KEY,
                            name VARCHAR(150) NOT NULL,
                            date_from DATE NOT NULL,
                            date_to DATE,
                            boats_needed INTEGER,
                            notes TEXT
                        )
                        """
                    )
                )
                db.session.execute(
                    text(
                        """
                        INSERT INTO event (id, name, date_from, date_to, boats_needed, notes)
                        SELECT id, name, date_from, date_to, boats_needed, notes
                        FROM event_old
                        """
                    )
                )
                db.session.execute(text("DROP TABLE event_old"))
            event_columns = db.session.execute(text("PRAGMA table_info(event)")).fetchall()
            event_names = {row[1] for row in event_columns}
            for column_name, column_type in {
                "what3words_location_1": "VARCHAR(120)",
                "what3words_location_2": "VARCHAR(120)",
                "what3words_location_3": "VARCHAR(120)",
                "latitude": "FLOAT",
                "longitude": "FLOAT",
                "tide_data": "JSON",
                "tide_error": "VARCHAR(255)",
            }.items():
                if column_name not in event_names:
                    db.session.execute(text(f"ALTER TABLE event ADD COLUMN {column_name} {column_type}"))
        else:
            db.session.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS event (
                        id INTEGER NOT NULL PRIMARY KEY,
                        name VARCHAR(150) NOT NULL,
                        date_from DATE NOT NULL,
                        date_to DATE,
                        boats_needed INTEGER,
                        notes TEXT
                    )
                    """
                )
            )

        event_members_columns = db.session.execute(text("PRAGMA table_info(event_members)")).fetchall()
        if not event_members_columns:
            db.session.execute(
                text(
                    """
                    CREATE TABLE event_members (
                        event_id INTEGER NOT NULL,
                        member_id INTEGER NOT NULL,
                        PRIMARY KEY (event_id, member_id),
                        FOREIGN KEY(event_id) REFERENCES event(id),
                        FOREIGN KEY(member_id) REFERENCES member(id)
                    )
                    """
                )
            )
    except Exception:
        pass

    db.session.commit()


def migrate_legacy_uploads(upload_folder):
    uploads = (
        (Certification, "certificate_copy", "certificate_data", "certificate_filename", "certificate_content_type"),
        (EventExpense, "receipt_image", "receipt_data", "receipt_filename", "receipt_content_type"),
    )
    for model, path_field, data_field, filename_field, content_type_field in uploads:
        for record in model.query.filter(getattr(model, data_field).is_(None)).all():
            relative_path = getattr(record, path_field)
            if not relative_path:
                continue
            filename = os.path.basename(relative_path)
            file_path = os.path.join(upload_folder, filename)
            if not os.path.isfile(file_path):
                continue
            with open(file_path, "rb") as upload_file:
                setattr(record, data_field, upload_file.read())
            setattr(record, filename_field, filename)
            setattr(record, content_type_field, mimetypes.guess_type(filename)[0] or "application/octet-stream")
    db.session.commit()


def generate_reset_token(user):
    token = secrets.token_urlsafe(32)
    user.reset_token = generate_password_hash(token)
    user.reset_token_expires = datetime.utcnow() + timedelta(hours=1)
    db.session.commit()
    return token


def send_reset_email(recipient_email, reset_url):
    # Defaults to Brevo's SMTP relay; set MAIL_USERNAME/MAIL_PASSWORD to your Brevo login and SMTP key.
    mail_server = os.getenv("MAIL_SERVER", "smtp-relay.brevo.com")
    mail_username = os.getenv("MAIL_USERNAME")
    mail_password = os.getenv("MAIL_PASSWORD")

    if not mail_username or not mail_password:
        print(f"Password reset link for {recipient_email}: {reset_url}")
        return True

    sender_email = os.getenv("MAIL_DEFAULT_SENDER", "noreply@northernextremity.local")
    message = EmailMessage()
    message["Subject"] = "Northern Exposure password reset"
    message["From"] = sender_email
    message["To"] = recipient_email
    message.set_content(
        "Use the following link to reset your password:\n\n"
        f"{reset_url}\n\n"
        "If you did not request this email, you can ignore it."
    )

    try:
        with smtplib.SMTP(mail_server, int(os.getenv("MAIL_PORT", "587"))) as smtp:
            if os.getenv("MAIL_USE_TLS", "true").lower() == "true":
                smtp.starttls()
            smtp.login(mail_username, mail_password)
            smtp.send_message(message)
        return True
    except Exception as exc:
        print(f"Email send failed for {recipient_email}: {exc}")
        return False


def create_app():
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
        "NERFLASK_DATABASE_URI", "sqlite:///northern_exposure.db"
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SECRET_KEY"] = "northern-exposure-secret"
    app.config["UPLOAD_FOLDER"] = os.path.join(app.root_path, "static", "uploads")
    app.config["MAIL_SERVER"] = os.getenv("MAIL_SERVER", "")
    app.config["MAIL_PORT"] = int(os.getenv("MAIL_PORT", "587"))
    app.config["MAIL_USE_TLS"] = os.getenv("MAIL_USE_TLS", "true").lower() == "true"
    app.config["MAIL_USERNAME"] = os.getenv("MAIL_USERNAME", "")
    app.config["MAIL_PASSWORD"] = os.getenv("MAIL_PASSWORD", "")
    app.config["MAIL_DEFAULT_SENDER"] = os.getenv("MAIL_DEFAULT_SENDER", "noreply@northernextremity.local")
    app.config["GOOGLE_CLIENT_ID"] = os.getenv("GOOGLE_CLIENT_ID", "")
    app.config["GOOGLE_CLIENT_SECRET"] = os.getenv("GOOGLE_CLIENT_SECRET", "")
    app.config["GOOGLE_REDIRECT_URI"] = os.getenv("GOOGLE_REDIRECT_URI", "http://127.0.0.1:5000/oauth/google/callback")

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    db.init_app(app)

    with app.app_context():
        ensure_database_schema()
        migrate_legacy_uploads(app.config["UPLOAD_FOLDER"])

        rya_qualifications = [
            ("RYA Powerboat Level 2", "Powerboat"),
            ("RYA Powerboat Level 1", "Powerboat"),
            ("RYA Advanced Powerboat", "Powerboat"),
            ("RYA Day Skipper", "Sailing"),
            ("RYA Coastal Skipper", "Sailing"),
            ("RYA Yachtmaster Offshore", "Sailing"),
            ("RYA Yachtmaster Ocean", "Sailing"),
            ("RYA First Aid", "Associated"),
            ("RYA Radar Course", "Associated"),
            ("RYA VHF Radio Certificate", "Associated"),
            ("RYA Sea Survival", "Associated"),
            ("RYA Diesel Engine Course", "Associated"),
        ]

        for qualification_name, category in rya_qualifications:
            if not Qualification.query.filter_by(name=qualification_name).first():
                qualification = Qualification(name=qualification_name, category=category)
                db.session.add(qualification)

        default_lookups = {
            "membership_type": ["Standard", "Premier", "Family", "Associate"],
            "member_status": ["Active", "Pending", "Inactive"],
            "certification_status": ["Valid", "Expired", "Pending"],
            "expense_type": [
                "Vehicle Fuel",
                "Boat Fuel",
                "Accommodation",
                "Food",
                "Congestion Charge",
            ],
        }
        for category, values in default_lookups.items():
            if not LookupItem.query.filter_by(category=category).first():
                for order, value in enumerate(values):
                    db.session.add(LookupItem(category=category, value=value, sort_order=order))

        if not User.query.filter_by(email="admin@noreply.local").first():
            admin_user = User(email="admin@noreply.local", role="admin")
            admin_user.set_password("admin123")
            db.session.add(admin_user)

        if not User.query.filter_by(email="staff@noreply.local").first():
            staff_user = User(email="staff@noreply.local", role="staff")
            staff_user.set_password("staff123")
            db.session.add(staff_user)

        db.session.commit()

    @app.before_request
    def enforce_login():
        user_id = session.get("user_id")
        if user_id and not db.session.get(User, user_id):
            session.clear()

        allowed_routes = {
            "login",
            "logout",
            "static",
            "signup",
            "forgot_password",
            "reset_password",
            "oauth_login",
        }
        if request.endpoint in allowed_routes:
            return None
        if not session.get("user_id"):
            return redirect(url_for("login"))

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if session.get("user_id"):
            return redirect(url_for("home"))

        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            user = User.query.filter_by(email=email).first()

            if user and user.check_password(password):
                ensure_member_for_user(user)
                db.session.commit()
                session["user_id"] = user.id
                session["username"] = user.email
                session["role"] = user.role
                flash(f"Welcome back, {user.email}.")
                if user.role == "member":
                    return redirect(url_for("my_profile"))
                return redirect(url_for("home"))

            flash("Invalid email or password.")
            return redirect(url_for("login"))

        return render_template("login.html")

    @app.route("/certification/<int:certification_id>/file")
    @login_required
    def view_certificate_file(certification_id):
        certification = Certification.query.get_or_404(certification_id)
        if session.get("role") == "member" and certification.member.email != session.get("username"):
            flash("You can only view your own certification files.")
            return redirect(url_for("my_profile"))
        if certification.certificate_data:
            return send_file(
                io.BytesIO(certification.certificate_data),
                mimetype=certification.certificate_content_type or "application/octet-stream",
                download_name=certification.certificate_filename or "certificate",
            )
        if certification.certificate_copy:
            return redirect(url_for("static", filename=certification.certificate_copy))
        abort(404)

    @app.route("/expense/<int:expense_id>/receipt")
    @login_required
    def view_expense_receipt(expense_id):
        expense = EventExpense.query.get_or_404(expense_id)
        if session.get("role") == "member" and expense.member.email != session.get("username"):
            flash("You can only view your own expense receipts.")
            return redirect(url_for("my_profile"))
        if expense.receipt_data:
            return send_file(
                io.BytesIO(expense.receipt_data),
                mimetype=expense.receipt_content_type or "application/octet-stream",
                download_name=expense.receipt_filename or "receipt",
            )
        if expense.receipt_image:
            return redirect(url_for("static", filename=expense.receipt_image))
        abort(404)

    @app.route("/event-document/<int:document_id>/file")
    @login_required
    def view_event_document_file(document_id):
        document = EventDocument.query.get_or_404(document_id)
        return send_file(
            io.BytesIO(document.document_data),
            mimetype=document.document_content_type,
            download_name=document.document_filename,
        )

    @app.route("/signup", methods=["GET", "POST"])
    def signup():
        if session.get("user_id"):
            return redirect(url_for("home"))

        if request.method == "POST":
            first_name = request.form.get("first_name", "").strip()
            last_name = request.form.get("last_name", "").strip()
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            confirm_password = request.form.get("confirm_password", "")

            if not first_name or not last_name or not email or not password:
                flash("Account creation failed: first name, last name, email, and password are required.")
                return redirect(url_for("login"))

            if password != confirm_password:
                flash("Account creation failed: passwords do not match.")
                return redirect(url_for("login"))

            if not is_strong_password(password):
                flash("Account creation failed: password must be at least 8 characters and include uppercase, lowercase, a number, and a symbol.")
                return redirect(url_for("login"))

            if User.query.filter_by(email=email).first() or Member.query.filter_by(email=email).first():
                flash("Account creation failed: that email is already registered.")
                return redirect(url_for("login"))

            user = User(
                email=email,
                first_name=first_name,
                last_name=last_name,
                role="member",
                provider="local",
            )
            user.set_password(password)
            db.session.add(user)
            db.session.flush()
            ensure_member_for_user(user)
            db.session.commit()

            flash("Account created successfully. You can now log in.")
            return redirect(url_for("login"))

        return redirect(url_for("login"))

    @app.route("/forgot-password", methods=["GET", "POST"])
    def forgot_password():
        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            user = User.query.filter_by(email=email).first()
            if user:
                token = generate_reset_token(user)
                reset_url = url_for("reset_password", token=token, _external=True)
                send_reset_email(email, reset_url)
            flash("If an account exists for that email, a password reset link has been sent.")
            return redirect(url_for("login"))

        return render_template("forgot_password.html")

    @app.route("/reset-password/<token>", methods=["GET", "POST"])
    def reset_password(token):
        user = None
        for candidate in User.query.filter(User.reset_token.isnot(None)).all():
            if check_password_hash(candidate.reset_token, token):
                user = candidate
                break

        if not user:
            flash("This reset link is invalid.")
            return redirect(url_for("login"))

        if user.reset_token_expires and user.reset_token_expires < datetime.utcnow():
            flash("This reset link has expired.")
            return redirect(url_for("login"))

        if request.method == "POST":
            password = request.form.get("password", "")
            confirm_password = request.form.get("confirm_password", "")
            if password != confirm_password:
                flash("Passwords do not match.")
                return redirect(url_for("reset_password", token=token))

            if not is_strong_password(password):
                flash("Password must be at least 8 characters and include uppercase, lowercase, a number, and a symbol.")
                return redirect(url_for("reset_password", token=token))

            user.set_password(password)
            user.reset_token = None
            user.reset_token_expires = None
            db.session.commit()
            flash("Your password has been reset. You can now log in.")
            return redirect(url_for("login"))

        return render_template("reset_password.html", token=token)

    @app.route("/oauth/<provider>")
    def oauth_login(provider):
        provider_name = provider.lower()
        if provider_name not in {"google", "github", "microsoft"}:
            flash("That OAuth provider is not supported.")
            return redirect(url_for("login"))

        if provider_name == "google":
            client_id = app.config.get("GOOGLE_CLIENT_ID")
            if not client_id:
                flash("Google OAuth is not configured yet. Please use email login or create an account.")
                return redirect(url_for("login"))

            params = {
                "client_id": client_id,
                "redirect_uri": app.config["GOOGLE_REDIRECT_URI"],
                "response_type": "code",
                "scope": "openid email profile",
                "access_type": "online",
                "prompt": "select_account",
            }
            google_auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)
            return redirect(google_auth_url)

        provider_env = {
            "github": "GITHUB_CLIENT_ID",
            "microsoft": "MICROSOFT_CLIENT_ID",
        }
        if os.getenv(provider_env[provider_name]):
            flash(f"{provider_name.title()} sign-in is configured and ready for provider setup.")
        else:
            flash(f"{provider_name.title()} sign-in is not configured yet. Please use email login or create an account.")
        return redirect(url_for("login"))

    @app.route("/oauth/google/callback")
    def google_oauth_callback():
        error = request.args.get("error")
        if error:
            flash("Google sign-in was cancelled or denied.")
            return redirect(url_for("login"))

        code = request.args.get("code")
        if not code:
            flash("Google sign-in did not return an authorisation code.")
            return redirect(url_for("login"))

        client_id = app.config.get("GOOGLE_CLIENT_ID")
        client_secret = app.config.get("GOOGLE_CLIENT_SECRET")
        redirect_uri = app.config.get("GOOGLE_REDIRECT_URI")

        if not client_id or not client_secret:
            flash("Google OAuth is not configured.")
            return redirect(url_for("login"))

        token_response = requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
            timeout=30,
        )

        if token_response.status_code != 200:
            flash("Google authentication failed while exchanging the code.")
            return redirect(url_for("login"))

        token_data = token_response.json()
        access_token = token_data.get("access_token")
        if not access_token:
            flash("Google did not return an access token.")
            return redirect(url_for("login"))

        userinfo_response = requests.get(
            "https://openidconnect.googleapis.com/v1/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=30,
        )

        if userinfo_response.status_code != 200:
            flash("Google user information could not be loaded.")
            return redirect(url_for("login"))

        userinfo = userinfo_response.json()
        email = (userinfo.get("email") or "").strip().lower()
        google_sub = userinfo.get("sub")
        if not email:
            flash("Google account email was not returned.")
            return redirect(url_for("login"))

        user = User.query.filter((User.email == email) | (User.provider_user_id == google_sub)).first()
        if not user:
            local_name = (userinfo.get("given_name") or email.split("@", 1)[0]).strip()
            user = User(
                email=email,
                first_name=local_name,
                last_name=userinfo.get("family_name") or "",
                role="member",
                provider="google",
                provider_user_id=google_sub,
            )
            user.set_password(secrets.token_urlsafe(24))
            db.session.add(user)
            db.session.flush()

            member = Member(
                first_name=user.first_name,
                last_name=user.last_name,
                email=email,
                membership_type="Standard",
                status="Active",
            )
            db.session.add(member)

        if not user.first_name and userinfo.get("given_name"):
            user.first_name = userinfo.get("given_name")
        if not user.last_name and userinfo.get("family_name"):
            user.last_name = userinfo.get("family_name")
        if user.provider != "google":
            user.provider = "google"
        user.provider_user_id = google_sub
        db.session.commit()

        session["user_id"] = user.id
        session["username"] = user.email
        session["role"] = user.role
        flash(f"Welcome back, {user.email}.")
        return redirect(url_for("home"))

    @app.route("/logout")
    def logout():
        session.clear()
        flash("You have been logged out.")
        return redirect(url_for("login"))

    @app.route("/")
    @login_required
    def home():
        if session.get("role") == "member":
            return redirect(url_for("my_profile"))

        search_term = request.args.get("q", "").strip()
        status_filter = request.args.get("status", "").strip()
        membership_filter = request.args.get("membership_type", "").strip()

        query = Member.query

        if search_term:
            query = query.filter(
                or_(
                    Member.first_name.ilike(f"%{search_term}%"),
                    Member.last_name.ilike(f"%{search_term}%"),
                    Member.email.ilike(f"%{search_term}%"),
                )
            )

        if status_filter:
            query = query.filter(Member.status == status_filter)

        if membership_filter:
            query = query.filter(Member.membership_type == membership_filter)

        members = query.order_by(Member.last_name, Member.first_name).all()
        member_total = Member.query.count()
        active_total = Member.query.filter_by(status="Active").count()
        pending_total = Member.query.filter_by(status="Pending").count()
        admin_total = User.query.filter_by(role="admin").count()

        current_member = None
        if session.get("role") == "member":
            current_user_record = User.query.get(session.get("user_id"))
            if current_user_record:
                current_member = ensure_member_for_user(current_user_record)

        return render_template(
            "index.html",
            members=members,
            q=search_term,
            status=status_filter,
            membership_type=membership_filter,
            statuses=get_lookup_values("member_status"),
            membership_types=get_lookup_values("membership_type"),
            current_user=session.get("username"),
            current_role=session.get("role"),
            current_member=current_member,
            member_total=member_total,
            active_total=active_total,
            pending_total=pending_total,
            admin_total=admin_total,
        )

    @app.route("/events")
    @login_required
    def events():
        month = request.args.get("month", type=int, default=datetime.utcnow().month)
        year = request.args.get("year", type=int, default=datetime.utcnow().year)
        selected_event_id = request.args.get("selected_event_id", type=int)

        if month < 1 or month > 12:
            month = datetime.utcnow().month
        if year < 2000:
            year = datetime.utcnow().year

        event_list = Event.query.order_by(Event.date_from.asc()).all()
        events_by_date = {}
        event_months = []
        current_month_group = None
        for event in event_list:
            key = event.date_from.isoformat()
            events_by_date.setdefault(key, []).append(event)
            month_key = (event.date_from.year, event.date_from.month)
            if not current_month_group or current_month_group["key"] != month_key:
                current_month_group = {
                    "key": month_key,
                    "label": event.date_from.strftime("%B %Y"),
                    "year": event.date_from.year,
                    "month": event.date_from.month,
                    "events": [],
                }
                event_months.append(current_month_group)
            current_month_group["events"].append(event)

        selected_event = None
        if selected_event_id:
            selected_event = Event.query.get(selected_event_id)
        if not selected_event and event_list:
            selected_event = event_list[0]
        selected_event_locations = []
        selected_event_participations = {}
        if selected_event:
            for position in range(1, 4):
                address = getattr(selected_event, f"what3words_location_{position}")
                if address:
                    selected_event_locations.append({"label": f"Location {position}", "address": address})
            selected_event_participations = {
                participation.member_id: participation for participation in selected_event.participations
            }
        tide_data = selected_event.tide_data if selected_event else None
        tide_error = selected_event.tide_error if selected_event else None

        current_member = None
        if session.get("role") == "member":
            current_user_record = User.query.get(session.get("user_id"))
            if current_user_record:
                current_member = ensure_member_for_user(current_user_record)

        prev_month = month - 1
        prev_year = year
        if prev_month == 0:
            prev_month = 12
            prev_year -= 1

        next_month = month + 1
        next_year = year
        if next_month == 13:
            next_month = 1
            next_year += 1

        month_weeks = calendar.monthcalendar(year, month)

        return render_template(
            "events.html",
            events=event_list,
            all_members=Member.query.order_by(Member.last_name, Member.first_name).all(),
            current_user=session.get("username"),
            current_role=session.get("role"),
            current_member=current_member,
            calendar_weeks=month_weeks,
            day_names=["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
            current_month=month,
            current_year=year,
            prev_month=prev_month,
            prev_year=prev_year,
            next_month=next_month,
            next_year=next_year,
            events_by_date=events_by_date,
            event_months=event_months,
            selected_event=selected_event,
            selected_event_locations=selected_event_locations,
            selected_event_participations=selected_event_participations,
            tide_data=tide_data,
            tide_error=tide_error,
            date_ref=date,
        )

    @app.route("/certifications/expired")
    @role_required("admin", "staff")
    def expired_certifications():
        today = date.today()
        expired = (
            Certification.query.filter(Certification.expiry_date.isnot(None))
            .filter(Certification.expiry_date < today)
            .join(Member)
            .order_by(Certification.expiry_date.asc())
            .all()
        )

        return render_template(
            "expired_certifications.html",
            certifications=expired,
            today=today,
            current_user=session.get("username"),
            current_role=session.get("role"),
        )

    @app.route("/admin/lookups")
    @role_required("admin")
    def admin_lookups():
        lookups = {
            category: LookupItem.query.filter_by(category=category)
            .order_by(LookupItem.sort_order, LookupItem.value)
            .all()
            for category in LOOKUP_CATEGORIES
        }
        return render_template(
            "admin_lookups.html",
            lookups=lookups,
            lookup_categories=LOOKUP_CATEGORIES,
            current_user=session.get("username"),
            current_role=session.get("role"),
        )

    @app.route("/admin/lookups/add", methods=["POST"])
    @role_required("admin")
    def add_lookup_item():
        category = request.form.get("category", "").strip()
        value = request.form.get("value", "").strip()

        if category not in LOOKUP_CATEGORIES or not value:
            flash("A valid category and value are required.")
            return redirect(url_for("admin_lookups"))

        if LookupItem.query.filter_by(category=category, value=value).first():
            flash("That value already exists for this category.")
            return redirect(url_for("admin_lookups"))

        max_order = db.session.query(db.func.max(LookupItem.sort_order)).filter_by(category=category).scalar()
        db.session.add(LookupItem(category=category, value=value, sort_order=(max_order or 0) + 1))
        db.session.commit()
        flash("Lookup value added successfully.")
        return redirect(url_for("admin_lookups"))

    @app.route("/admin/lookups/<int:item_id>/edit", methods=["POST"])
    @role_required("admin")
    def edit_lookup_item(item_id):
        item = LookupItem.query.get_or_404(item_id)
        new_value = request.form.get("value", "").strip()

        if not new_value:
            flash("A value is required.")
            return redirect(url_for("admin_lookups"))

        if LookupItem.query.filter(
            LookupItem.category == item.category,
            LookupItem.value == new_value,
            LookupItem.id != item.id,
        ).first():
            flash("That value already exists for this category.")
            return redirect(url_for("admin_lookups"))

        item.value = new_value
        db.session.commit()
        flash("Lookup value updated successfully.")
        return redirect(url_for("admin_lookups"))

    @app.route("/admin/lookups/<int:item_id>/delete", methods=["POST"])
    @role_required("admin")
    def delete_lookup_item(item_id):
        item = LookupItem.query.get_or_404(item_id)
        db.session.delete(item)
        db.session.commit()
        flash("Lookup value deleted successfully.")
        return redirect(url_for("admin_lookups"))

    @app.route("/event/<int:event_id>/join", methods=["POST"])
    @login_required
    @role_required("member")
    def join_event(event_id):
        event = Event.query.get_or_404(event_id)
        user = User.query.get(session.get("user_id"))
        if not user:
            flash("Your account could not be found.")
            return redirect(url_for("events"))

        member = ensure_member_for_user(user)
        if not member:
            flash("Please complete your member profile before joining an event.")
            return redirect(url_for("events"))

        if member not in event.members:
            event.members.append(member)
            db.session.add(EventParticipation(event_id=event.id, member_id=member.id))
            db.session.commit()
            flash(f"You have joined {event.name}. Your participation is pending approval.")
        else:
            flash("You are already registered for this event.")

        return redirect(url_for("events"))

    @app.route("/event/<int:event_id>/unsubscribe", methods=["POST"])
    @login_required
    @role_required("member")
    def unsubscribe_from_event(event_id):
        event = Event.query.get_or_404(event_id)
        user = User.query.get(session.get("user_id"))
        member = ensure_member_for_user(user)

        if not member or member not in event.members:
            flash("You are not registered for this event.")
            return redirect(url_for("events"))

        event.members.remove(member)
        participation = get_event_participation(event.id, member.id)
        if participation:
            db.session.delete(participation)
        db.session.commit()
        flash(f"You have unsubscribed from {event.name}.")
        return redirect(url_for("events"))

    @app.route("/event/<int:event_id>/documents/add", methods=["POST"])
    @login_required
    @role_required("admin", "staff")
    def add_event_document(event_id):
        event = Event.query.get_or_404(event_id)
        description = request.form.get("description", "").strip()
        document_file = request.files.get("document")
        if not description or not document_file or not document_file.filename:
            flash("A document description and file are required.")
            return redirect(url_for("events", month=event.date_from.month, year=event.date_from.year, selected_event_id=event.id))

        filename = secure_filename(document_file.filename)
        if not filename:
            flash("Choose a valid document file.")
            return redirect(url_for("events", month=event.date_from.month, year=event.date_from.year, selected_event_id=event.id))

        db.session.add(EventDocument(
            event_id=event.id,
            description=description,
            document_data=document_file.read(),
            document_filename=filename,
            document_content_type=document_file.mimetype or mimetypes.guess_type(filename)[0] or "application/octet-stream",
            uploaded_by_user_id=session["user_id"],
        ))
        db.session.commit()
        flash("Event document added successfully.")
        return redirect(url_for("events", month=event.date_from.month, year=event.date_from.year, selected_event_id=event.id))

    @app.route("/events/new", methods=["GET", "POST"])
    @login_required
    @role_required("admin", "staff")
    def new_event():
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            date_from = request.form.get("date_from", "")
            date_to = request.form.get("date_to", "")
            boats_needed = request.form.get("boats_needed", "")
            notes = request.form.get("notes", "").strip()
            what3words_values = [request.form.get(f"what3words_location_{position}", "") for position in range(1, 4)]
            latitude_value = request.form.get("latitude", "")
            longitude_value = request.form.get("longitude", "")
            selected_member_ids = request.form.getlist("member_ids")

            if not name or not date_from:
                flash("Event name and start date are required.")
                return redirect(url_for("new_event"))

            try:
                what3words_locations = [normalize_what3words(value) for value in what3words_values]
                latitude, longitude = parse_coordinates(latitude_value, longitude_value)
            except ValueError:
                flash("Enter valid What3words locations and latitude/longitude coordinates.")
                return redirect(url_for("new_event"))

            event = Event(
                name=name,
                date_from=datetime.strptime(date_from, "%Y-%m-%d").date(),
                date_to=datetime.strptime(date_to, "%Y-%m-%d").date() if date_to else None,
                boats_needed=int(boats_needed) if boats_needed else 0,
                notes=notes or None,
                what3words_location_1=what3words_locations[0],
                what3words_location_2=what3words_locations[1],
                what3words_location_3=what3words_locations[2],
                latitude=latitude,
                longitude=longitude,
            )
            db.session.add(event)
            db.session.flush()

            for member_id_value in selected_member_ids:
                linked_member = Member.query.get(int(member_id_value))
                if linked_member:
                    event.members.append(linked_member)

            refresh_event_tides(event)
            db.session.commit()
            flash("Event created successfully.")
            return redirect(url_for("events"))

        date_from_value = request.args.get("date_from", "")
        try:
            date_from_value = datetime.strptime(date_from_value, "%Y-%m-%d").date().isoformat()
        except ValueError:
            date_from_value = ""

        return render_template(
            "new_event.html",
            all_members=Member.query.order_by(Member.last_name, Member.first_name).all(),
            current_user=session.get("username"),
            current_role=session.get("role"),
            date_from_value=date_from_value,
        )

    @app.route("/event/<int:event_id>/edit", methods=["GET", "POST"])
    @login_required
    @role_required("admin", "staff")
    def edit_event(event_id):
        event = Event.query.get_or_404(event_id)

        if request.method == "POST":
            if session.get("role") != "admin":
                flash("Only administrators can change event details.")
                return redirect(url_for("edit_event", event_id=event.id))
            name = request.form.get("name", "").strip()
            date_from = request.form.get("date_from", "")
            date_to = request.form.get("date_to", "")
            boats_needed = request.form.get("boats_needed", "")
            notes = request.form.get("notes", "").strip()
            what3words_values = [request.form.get(f"what3words_location_{position}", "") for position in range(1, 4)]
            latitude_value = request.form.get("latitude", "")
            longitude_value = request.form.get("longitude", "")
            selected_member_ids = request.form.getlist("member_ids")

            if not name or not date_from:
                flash("Event name and start date are required.")
                return redirect(url_for("edit_event", event_id=event.id))

            try:
                what3words_locations = [normalize_what3words(value) for value in what3words_values]
                latitude, longitude = parse_coordinates(latitude_value, longitude_value)
            except ValueError:
                flash("Enter valid What3words locations and latitude/longitude coordinates.")
                return redirect(url_for("edit_event", event_id=event.id))

            event.name = name
            event.date_from = datetime.strptime(date_from, "%Y-%m-%d").date()
            event.date_to = datetime.strptime(date_to, "%Y-%m-%d").date() if date_to else None
            event.boats_needed = int(boats_needed) if boats_needed else 0
            event.notes = notes or None
            event.what3words_location_1 = what3words_locations[0]
            event.what3words_location_2 = what3words_locations[1]
            event.what3words_location_3 = what3words_locations[2]
            event.latitude = latitude
            event.longitude = longitude
            refresh_event_tides(event)

            event.members.clear()
            selected_member_id_set = {int(member_id_value) for member_id_value in selected_member_ids}
            EventParticipation.query.filter(
                EventParticipation.event_id == event.id,
                EventParticipation.member_id.notin_(selected_member_id_set),
            ).delete(synchronize_session=False)
            for member_id_value in selected_member_ids:
                linked_member = Member.query.get(int(member_id_value))
                if linked_member:
                    event.members.append(linked_member)
                    if not get_event_participation(event.id, linked_member.id):
                        db.session.add(EventParticipation(event_id=event.id, member_id=linked_member.id))

            db.session.commit()
            flash("Event updated successfully.")
            return redirect(url_for("events"))

        return render_template(
            "edit_event.html",
            event=event,
            all_members=Member.query.order_by(Member.last_name, Member.first_name).all(),
            current_user=session.get("username"),
            current_role=session.get("role"),
        )

    @app.route("/my-profile")
    @login_required
    def my_profile():
        user = User.query.get(session.get("user_id"))
        if not user:
            flash("Your account could not be found.")
            return redirect(url_for("login"))
        member = ensure_member_for_user(user)
        if member is None:
            flash("Your member profile could not be found.")
            return redirect(url_for("home"))
        return redirect(url_for("member_detail", member_id=member.id))

    @app.route("/members/add", methods=["POST"])
    @login_required
    @role_required("admin", "staff")
    def add_member():
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()
        email = request.form.get("email", "").strip()
        phone = request.form.get("phone", "").strip()
        mobile = request.form.get("mobile", "").strip()
        home_phone = request.form.get("home_phone", "").strip()
        address_1 = request.form.get("address_1", "").strip()
        address_2 = request.form.get("address_2", "").strip()
        town = request.form.get("town", "").strip()
        city = request.form.get("city", "").strip()
        postcode = request.form.get("postcode", "").strip()
        membership_type = request.form.get("membership_type", "Standard").strip()
        status = request.form.get("status", "Active").strip()
        notes = request.form.get("notes", "").strip()

        if not first_name or not last_name or not email:
            flash("First name, last name, and email are required.")
            return redirect(url_for("home"))

        if Member.query.filter_by(email=email).first() or User.query.filter_by(email=email).first():
            flash("A member account with this email already exists.")
            return redirect(url_for("home"))

        member = Member(
            first_name=first_name,
            last_name=last_name,
            email=email,
            phone=phone or None,
            mobile=mobile or None,
            home_phone=home_phone or None,
            address_1=address_1 or None,
            address_2=address_2 or None,
            town=town or None,
            city=city or None,
            postcode=postcode or None,
            membership_type=membership_type or "Standard",
            status=status or "Active",
            notes=notes or None,
        )
        db.session.add(member)
        db.session.commit()
        flash("Member added successfully.")
        return redirect(url_for("home"))

    @app.route("/member/<int:member_id>")
    @login_required
    def member_detail(member_id):
        member = Member.query.get_or_404(member_id)
        if session.get("role") == "member" and member.email != session.get("username"):
            flash("You can only edit your own profile.")
            return redirect(url_for("my_profile"))
        qualifications = Qualification.query.order_by(Qualification.category, Qualification.name).all()
        member_events = Event.query.filter(Event.members.any(id=member.id)).order_by(Event.date_from.desc()).all()
        member_event_participations = {
            participation.event_id: participation
            for participation in EventParticipation.query.filter_by(member_id=member.id).all()
        }
        selected_event_id = request.args.get("selected_event_id", type=int)
        selected_event = next((event for event in member_events if event.id == selected_event_id), None)
        active_tab = request.args.get("tab", "certifications")
        if selected_event:
            active_tab = "events"
        elif active_tab not in {"certifications", "boats", "events"}:
            active_tab = "certifications"
        event_expenses_by_event = {event.id: [] for event in member_events}
        for expense in EventExpense.query.filter_by(member_id=member.id).order_by(
            EventExpense.expense_date.desc(), EventExpense.id.desc()
        ).all():
            if expense.event_id in event_expenses_by_event:
                event_expenses_by_event[expense.event_id].append(expense)
        return render_template(
            "member_detail.html",
            member=member,
            qualifications=qualifications,
            member_events=member_events,
            member_event_participations=member_event_participations,
            selected_event=selected_event,
            event_expenses_by_event=event_expenses_by_event,
            active_tab=active_tab,
            current_user=session.get("username"),
            current_role=session.get("role"),
            cert_statuses=get_lookup_values("certification_status"),
            expense_types=get_lookup_values("expense_type"),
        )

    @app.route("/member/<int:member_id>/edit", methods=["GET", "POST"])
    @login_required
    def edit_member(member_id):
        member = Member.query.get_or_404(member_id)
        if session.get("role") == "member" and member.email != session.get("username"):
            flash("You can only edit your own profile.")
            return redirect(url_for("my_profile"))

        if request.method == "POST":
            original_email = member.email
            member.first_name = request.form.get("first_name", member.first_name).strip()
            member.last_name = request.form.get("last_name", member.last_name).strip()
            member.email = request.form.get("email", member.email).strip()
            member.phone = request.form.get("phone", "").strip() or None
            member.mobile = request.form.get("mobile", "").strip() or None
            member.home_phone = request.form.get("home_phone", "").strip() or None
            member.address_1 = request.form.get("address_1", "").strip() or None
            member.address_2 = request.form.get("address_2", "").strip() or None
            member.town = request.form.get("town", "").strip() or None
            member.city = request.form.get("city", "").strip() or None
            member.postcode = request.form.get("postcode", "").strip() or None
            member.membership_type = request.form.get("membership_type", member.membership_type).strip()
            member.status = request.form.get("status", member.status).strip()
            member.notes = request.form.get("notes", "").strip() or None

            if not member.first_name or not member.last_name or not member.email:
                flash("First name, last name, and email are required.")
                return redirect(url_for("edit_member", member_id=member.id))

            if Member.query.filter(Member.email == member.email, Member.id != member.id).first():
                flash("A member with this email already exists.")
                return redirect(url_for("edit_member", member_id=member.id))

            user = User.query.filter_by(email=original_email).first()
            if user:
                user.email = member.email
                user.first_name = member.first_name
                user.last_name = member.last_name
                if session.get("role") == "admin":
                    new_role = request.form.get("role", "").strip()
                    if new_role in ("member", "staff", "admin"):
                        user.role = new_role
                        if session.get("username") == original_email:
                            session["role"] = new_role
                if session.get("username") == original_email:
                    session["username"] = member.email

            db.session.commit()
            flash("Member updated successfully.")
            return redirect(url_for("member_detail", member_id=member.id))

        member_user = User.query.filter_by(email=member.email).first()
        return render_template(
            "edit_member.html",
            member=member,
            current_user=session.get("username"),
            current_role=session.get("role"),
            membership_types=get_lookup_values("membership_type"),
            statuses=get_lookup_values("member_status"),
            member_role=member_user.role if member_user else "member",
        )

    @app.route("/member/<int:member_id>/delete", methods=["POST"])
    @login_required
    @role_required("admin")
    def delete_member(member_id):
        member = Member.query.get_or_404(member_id)
        db.session.delete(member)
        db.session.commit()
        flash("Member deleted successfully.")
        return redirect(url_for("home"))

    @app.route("/member/<int:member_id>/expenses/add", methods=["POST"])
    @login_required
    def add_event_expense(member_id):
        member = Member.query.get_or_404(member_id)
        submitting_user = User.query.get(session.get("user_id"))
        if session.get("role") == "member" and (
            not submitting_user or submitting_user.email != member.email
        ):
            flash("You can only add expenses for your own profile.")
            return redirect(url_for("my_profile"))
        event_id = request.form.get("event_id", type=int)
        redirect_url = url_for("member_detail", member_id=member.id, selected_event_id=event_id)
        expense_type = request.form.get("expense_type", "").strip()
        expense_date = request.form.get("expense_date", "")
        amount_value = request.form.get("amount", "").strip()
        receipt_file = request.files.get("receipt_image")

        event = Event.query.get(event_id) if event_id else None
        if not event or member not in event.members:
            flash("Please select an event this member is assigned to.")
            return redirect(url_for("member_detail", member_id=member.id))
        participation = get_event_participation(event.id, member.id)
        if not participation or participation.status != "Approved":
            flash("Your participation must be approved before you can add an expense for this event.")
            return redirect(redirect_url)
        if expense_type not in get_lookup_values("expense_type"):
            flash("Please select a valid expense type.")
            return redirect(redirect_url)
        if not submitting_user:
            flash("Your account could not be found.")
            return redirect(redirect_url)

        try:
            parsed_date = datetime.strptime(expense_date, "%Y-%m-%d").date()
            amount = Decimal(amount_value)
            if amount <= 0:
                raise InvalidOperation
        except (ValueError, InvalidOperation):
            flash("Expense date and a positive amount are required.")
            return redirect(redirect_url)

        receipt_path = None
        if not receipt_file or not receipt_file.filename:
            flash("A receipt image is required.")
            return redirect(redirect_url)

        filename = secure_filename(receipt_file.filename)
        extension = os.path.splitext(filename)[1].lower()
        if extension not in {".png", ".jpg", ".jpeg", ".gif", ".webp"}:
            flash("Receipt must be an image file.")
            return redirect(redirect_url)
        receipt_data = receipt_file.read()

        db.session.add(EventExpense(
            event_id=event.id,
            member_id=member.id,
            expense_type=expense_type,
            expense_date=parsed_date,
            amount=amount,
            approved_by_user_id=submitting_user.id,
            receipt_data=receipt_data,
            receipt_filename=filename,
            receipt_content_type=receipt_file.mimetype or mimetypes.guess_type(filename)[0] or "application/octet-stream",
            status="Pending",
        ))
        db.session.commit()
        flash("Event expense added successfully.")
        return redirect(redirect_url)

    @app.route("/event/<int:event_id>/member/<int:member_id>/approve", methods=["POST"])
    @login_required
    @role_required("admin", "staff")
    def approve_event_participation(event_id, member_id):
        event = Event.query.get_or_404(event_id)
        member = Member.query.get_or_404(member_id)
        if member not in event.members:
            flash("This member is not assigned to the event.")
            return redirect(url_for("events", month=event.date_from.month, year=event.date_from.year, selected_event_id=event.id))

        participation = get_event_participation(event.id, member.id)
        if not participation:
            participation = EventParticipation(event_id=event.id, member_id=member.id)
            db.session.add(participation)
        approver = User.query.get(session.get("user_id"))
        participation.status = "Approved"
        participation.approved_by_user_id = approver.id
        participation.approved_at = datetime.utcnow()
        db.session.commit()
        flash(f"{member.first_name} {member.last_name} is approved for {event.name}.")
        return redirect(url_for("events", month=event.date_from.month, year=event.date_from.year, selected_event_id=event.id))

    def get_expense_review(event_id):
        event = Event.query.get_or_404(event_id)
        expenses = EventExpense.query.filter_by(event_id=event.id).order_by(
            EventExpense.expense_date.desc(), EventExpense.id.desc()
        ).all()
        totals_by_type = (
            db.session.query(EventExpense.expense_type, db.func.sum(EventExpense.amount))
            .filter_by(event_id=event.id)
            .group_by(EventExpense.expense_type)
            .order_by(EventExpense.expense_type)
            .all()
        )
        total_amount = sum((expense.amount for expense in expenses), Decimal("0.00"))
        return event, expenses, totals_by_type, total_amount

    @app.route("/expenses")
    @login_required
    @role_required("admin", "staff")
    def event_expenses():
        event_list = Event.query.order_by(Event.date_from.desc(), Event.name).all()
        selected_event_id = request.args.get("event_id", type=int)
        selected_event_id = selected_event_id or (event_list[0].id if event_list else None)
        review = get_expense_review(selected_event_id) if selected_event_id else None
        return render_template(
            "event_expenses.html",
            event_list=event_list,
            review=review,
            current_user=session.get("username"),
            current_role=session.get("role"),
        )

    @app.route("/expenses/<int:event_id>/print")
    @login_required
    @role_required("admin", "staff")
    def print_event_expenses(event_id):
        event, expenses, totals_by_type, total_amount = get_expense_review(event_id)
        return render_template(
            "print_event_expenses.html",
            event=event,
            expenses=expenses,
            totals_by_type=totals_by_type,
            total_amount=total_amount,
            current_user=session.get("username"),
            current_role=session.get("role"),
        )

    @app.route("/expense/<int:expense_id>/<action>", methods=["POST"])
    @login_required
    @role_required("admin")
    def update_event_expense_status(expense_id, action):
        expense = EventExpense.query.get_or_404(expense_id)
        admin = User.query.get(session.get("user_id"))
        if action == "approve" and expense.status == "Pending":
            expense.status = "Approved"
            expense.reviewed_by_user_id = admin.id
            expense.reviewed_at = datetime.utcnow()
            flash("Expense approved successfully.")
        elif action == "pay" and expense.status == "Approved":
            expense.status = "Paid"
            expense.paid_by_user_id = admin.id
            expense.paid_at = datetime.utcnow()
            flash("Expense marked as paid successfully.")
        elif action == "undo_paid" and expense.status == "Paid":
            expense.status = "Approved"
            expense.paid_by_user_id = None
            expense.paid_at = None
            flash("Paid status removed. The expense is approved again.")
        elif action == "undo_approved" and expense.status == "Approved":
            expense.status = "Pending"
            expense.reviewed_by_user_id = None
            expense.reviewed_at = None
            flash("Approval removed. The expense is pending again.")
        else:
            flash("That expense status change is not allowed.")
        db.session.commit()
        return redirect(url_for("event_expenses", event_id=expense.event_id))

    @app.route("/member/<int:member_id>/certification/add", methods=["POST"])
    @login_required
    def add_certification(member_id):
        member = Member.query.get_or_404(member_id)
        if session.get("role") == "member" and member.email != session.get("username"):
            flash("You can only manage your own certifications.")
            return redirect(url_for("my_profile"))
        name = request.form.get("name", "").strip()
        certification_number = request.form.get("certification_number", "").strip()
        issue_date = request.form.get("issue_date", "")
        expiry_date = request.form.get("expiry_date", "")
        status = request.form.get("status", "Valid").strip()
        certificate_file = request.files.get("certificate_copy")

        if not name or not issue_date:
            flash("Certification name and issue date are required.")
            return redirect(url_for("member_detail", member_id=member.id))

        if not Qualification.query.filter_by(name=name).first():
            flash("Please select a valid qualification from the list.")
            return redirect(url_for("member_detail", member_id=member.id))

        certificate_data = None
        certificate_filename = None
        certificate_content_type = None
        if certificate_file and certificate_file.filename:
            filename = secure_filename(certificate_file.filename)
            if filename:
                certificate_data = certificate_file.read()
                certificate_filename = filename
                certificate_content_type = certificate_file.mimetype or mimetypes.guess_type(filename)[0] or "application/octet-stream"

        certification = Certification(
            member_id=member.id,
            name=name,
            certification_number=certification_number or None,
            issue_date=datetime.strptime(issue_date, "%Y-%m-%d").date(),
            expiry_date=datetime.strptime(expiry_date, "%Y-%m-%d").date() if expiry_date else None,
            status=status or "Valid",
            certificate_data=certificate_data,
            certificate_filename=certificate_filename,
            certificate_content_type=certificate_content_type,
        )
        db.session.add(certification)
        db.session.commit()
        flash("Certification added successfully.")
        return redirect(url_for("member_detail", member_id=member.id, tab="certifications"))

    @app.route("/member/<int:member_id>/certification/<int:certification_id>/edit", methods=["POST"])
    @login_required
    def edit_certification(member_id, certification_id):
        member = Member.query.get_or_404(member_id)
        certification = Certification.query.filter_by(id=certification_id, member_id=member.id).first_or_404()
        if session.get("role") == "member" and member.email != session.get("username"):
            flash("You can only manage your own certifications.")
            return redirect(url_for("my_profile"))

        name = request.form.get("name", "").strip()
        issue_date = request.form.get("issue_date", "")
        if not name or not issue_date or not Qualification.query.filter_by(name=name).first():
            flash("Please provide a valid certification name and issue date.")
            return redirect(url_for("member_detail", member_id=member.id, tab="certifications"))

        certification.name = name
        certification.certification_number = request.form.get("certification_number", "").strip() or None
        certification.issue_date = datetime.strptime(issue_date, "%Y-%m-%d").date()
        expiry_date = request.form.get("expiry_date", "")
        certification.expiry_date = datetime.strptime(expiry_date, "%Y-%m-%d").date() if expiry_date else None
        certification.status = request.form.get("status", "Valid").strip() or "Valid"
        certificate_file = request.files.get("certificate_copy")
        if certificate_file and certificate_file.filename:
            filename = secure_filename(certificate_file.filename)
            if filename:
                certification.certificate_copy = None
                certification.certificate_data = certificate_file.read()
                certification.certificate_filename = filename
                certification.certificate_content_type = certificate_file.mimetype or mimetypes.guess_type(filename)[0] or "application/octet-stream"

        db.session.commit()
        flash("Certification updated successfully.")
        return redirect(url_for("member_detail", member_id=member.id, tab="certifications"))

    @app.route("/member/<int:member_id>/certification/<int:certification_id>/delete", methods=["POST"])
    @login_required
    def delete_certification(member_id, certification_id):
        member = Member.query.get_or_404(member_id)
        certification = Certification.query.filter_by(id=certification_id, member_id=member.id).first_or_404()
        if session.get("role") == "member" and member.email != session.get("username"):
            flash("You can only manage your own certifications.")
            return redirect(url_for("my_profile"))

        db.session.delete(certification)
        db.session.commit()
        flash("Certification deleted successfully.")
        return redirect(url_for("member_detail", member_id=member.id, tab="certifications"))

    @app.route("/member/<int:member_id>/boat/add", methods=["POST"])
    @login_required
    def add_boat(member_id):
        member = Member.query.get_or_404(member_id)
        if session.get("role") == "member" and member.email != session.get("username"):
            flash("You can only manage your own boats.")
            return redirect(url_for("my_profile"))
        name = request.form.get("name", "").strip()
        registration = request.form.get("registration", "").strip()
        boat_type = request.form.get("boat_type", "").strip()
        length = request.form.get("length", "").strip()
        year = request.form.get("year", "")
        engine = request.form.get("engine", "").strip()
        mmsi_number = request.form.get("mmsi_number", "").strip()
        ssr_number = request.form.get("ssr_number", "").strip()
        notes = request.form.get("notes", "").strip()

        if not name:
            flash("Boat name is required.")
            return redirect(url_for("member_detail", member_id=member.id))

        boat = Boat(
            member_id=member.id,
            name=name,
            registration=registration or None,
            boat_type=boat_type or None,
            length=length or None,
            year=int(year) if year else None,
            engine=engine or None,
            mmsi_number=mmsi_number or None,
            ssr_number=ssr_number or None,
            vhf=request.form.get("vhf") == "on",
            ais=request.form.get("ais") == "on",
            notes=notes or None,
        )
        db.session.add(boat)
        db.session.commit()
        flash("Boat added successfully.")
        return redirect(url_for("member_detail", member_id=member.id, tab="boats"))

    @app.route("/member/<int:member_id>/boat/<int:boat_id>/edit", methods=["POST"])
    @login_required
    def edit_boat(member_id, boat_id):
        member = Member.query.get_or_404(member_id)
        boat = Boat.query.filter_by(id=boat_id, member_id=member.id).first_or_404()
        if session.get("role") == "member" and member.email != session.get("username"):
            flash("You can only manage your own boats.")
            return redirect(url_for("my_profile"))

        boat.name = request.form.get("name", "").strip()
        boat.registration = request.form.get("registration", "").strip() or None
        boat.boat_type = request.form.get("boat_type", "").strip() or None
        boat.length = request.form.get("length", "").strip() or None
        year = request.form.get("year", "")
        boat.year = int(year) if year else None
        boat.engine = request.form.get("engine", "").strip() or None
        boat.mmsi_number = request.form.get("mmsi_number", "").strip() or None
        boat.ssr_number = request.form.get("ssr_number", "").strip() or None
        boat.vhf = request.form.get("vhf") == "on"
        boat.ais = request.form.get("ais") == "on"
        boat.notes = request.form.get("notes", "").strip() or None
        if not boat.name:
            flash("Boat name is required.")
            return redirect(url_for("member_detail", member_id=member.id, tab="boats"))

        db.session.commit()
        flash("Boat updated successfully.")
        return redirect(url_for("member_detail", member_id=member.id, tab="boats"))

    @app.route("/member/<int:member_id>/boat/<int:boat_id>/delete", methods=["POST"])
    @login_required
    def delete_boat(member_id, boat_id):
        member = Member.query.get_or_404(member_id)
        boat = Boat.query.filter_by(id=boat_id, member_id=member.id).first_or_404()
        if session.get("role") == "member" and member.email != session.get("username"):
            flash("You can only manage your own boats.")
            return redirect(url_for("my_profile"))

        db.session.delete(boat)
        db.session.commit()
        flash("Boat deleted successfully.")
        return redirect(url_for("member_detail", member_id=member.id, tab="boats"))

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)
