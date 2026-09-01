from datetime import date
import os

from sqlalchemy import text

os.environ["NERFLASK_DATABASE_URI"] = "sqlite:///northern_exposure_test.db"

from app import Event, Member, app, db

with app.app_context():
    cols = db.session.execute(text("PRAGMA table_info(event)")).fetchall()
    event_members_cols = db.session.execute(text("PRAGMA table_info(event_members)")).fetchall()
    print("event_columns:", cols)
    print("event_has_member_id:", any(column[1] == "member_id" for column in cols))
    print("event_members_columns:", event_members_cols)

    member = Member.query.filter_by(email="schema_validation@example.com").first()
    if member is None:
        member = Member(
            first_name="Schema",
            last_name="Validation",
            email="schema_validation@example.com",
            membership_type="Standard",
            status="Active",
        )
        db.session.add(member)
        db.session.commit()

    event = Event(
        name="Migration validation",
        date_from=date(2026, 1, 10),
        boats_needed=2,
        notes="validation",
    )
    db.session.add(event)
    db.session.flush()
    event.members.append(member)
    db.session.commit()
    print("created_event_id:", event.id)
    print("member_count:", len(event.members))
