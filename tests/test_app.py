import io
import os
from datetime import date
from decimal import Decimal
from unittest.mock import patch

os.environ["NERFLASK_DATABASE_URI"] = "sqlite:///northern_exposure_test.db"

from app import Boat, Certification, Event, EventDocument, EventExpense, EventParticipation, LookupItem, Member, Qualification, User, app, db, get_event_participation


app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)


def setup_function():
    with app.app_context():
        db.drop_all()
        db.create_all()
        member = Member(
            first_name="Alice",
            last_name="Brown",
            email="alice@example.com",
            membership_type="Premier",
            status="Active",
        )
        db.session.add(member)
        db.session.commit()


def test_login_required_redirect():
    client = app.test_client()
    response = client.get('/')
    assert response.status_code == 302
    assert '/login' in response.headers['Location']


def test_login_clears_stale_member_session():
    client = app.test_client()
    with client.session_transaction() as session:
        session['user_id'] = 999999
        session['username'] = 'removed-member@example.com'
        session['role'] = 'member'

    response = client.get('/login', follow_redirects=True)
    assert response.status_code == 200
    assert 'Login' in response.get_data(as_text=True)


def test_staff_can_open_add_member_modal_and_create_member():
    with app.app_context():
        staff = User(email='add-member-staff@example.com', role='staff')
        staff.set_password('Password123!')
        db.session.add(staff)
        db.session.commit()

    client = app.test_client()
    client.post('/login', data={'email': 'add-member-staff@example.com', 'password': 'Password123!'})
    response = client.get('/')
    assert 'data-bs-target="#addMemberModal"' in response.get_data(as_text=True)
    response = client.post('/members/add', data={
        'first_name': 'New', 'last_name': 'Member', 'email': 'new-member@example.com',
    }, follow_redirects=True)
    assert 'Member added successfully.' in response.get_data(as_text=True)
    with app.app_context():
        assert Member.query.filter_by(email='new-member@example.com').count() == 1


def test_event_month_navigator_links_to_calendar_months():
    with app.app_context():
        admin = User(email='events-admin@example.com', role='admin')
        admin.set_password('Password123!')
        db.session.add_all([
            admin,
            Event(
                name='Spring Training',
                date_from=date(2026, 3, 15),
                what3words_location_1='filled.count.soap',
            ),
            Event(
                name='Summer Regatta',
                date_from=date(2026, 6, 20),
                latitude=54.9783,
                longitude=-1.6178,
            ),
        ])
        db.session.commit()

    client = app.test_client()
    client.post('/login', data={'email': 'events-admin@example.com', 'password': 'Password123!'})
    response = client.get('/events?month=3&year=2026')
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'Event Months' in html
    assert 'March 2026' in html
    assert 'June 2026' in html
    assert 'month=6&amp;year=2026' in html
    assert 'Summer Regatta' in html
    assert 'Event Locations' in html
    assert '///filled.count.soap' in html
    assert 'data-w3w-url="https://what3words.com/filled.count.soap"' in html
    assert 'id="w3wLocationFrame"' in html
    assert 'Location 1:' not in html
    assert 'class="event-pill event-select-link"' in html
    assert 'async function selectEvent(event)' in html
    assert 'async function selectEventMonth(event)' in html
    assert 'event-month-link event-month-select-link' in html
    assert 'event-calendar-day' in html
    assert 'eventCalendarContextMenu' in html
    assert 'Create event for ' in html
    assert 'window.location.assign(link.href)' in html

    create_response = client.get('/events/new?date_from=2026-03-15')
    assert create_response.status_code == 200
    assert 'name="date_from" value="2026-03-15"' in create_response.get_data(as_text=True)

    no_w3w_response = client.get('/events?month=6&year=2026&selected_event_id=2')
    assert 'Tide Times' in no_w3w_response.get_data(as_text=True)
    assert 'id="w3wLocationFrame"' not in no_w3w_response.get_data(as_text=True)


def test_member_can_unsubscribe_from_event():
    with app.app_context():
        user = User(email='unsubscribe@example.com', first_name='Unsub', last_name='Member', role='member')
        user.set_password('Password123!')
        event = Event(name='Unsubscribe Test', date_from=date(2026, 8, 10))
        db.session.add_all([user, event])
        db.session.commit()
        event_id = event.id

    client = app.test_client()
    client.post('/login', data={'email': 'unsubscribe@example.com', 'password': 'Password123!'})
    join_response = client.post(f'/event/{event_id}/join', follow_redirects=True)
    assert 'You have joined Unsubscribe Test.' in join_response.get_data(as_text=True)
    assert 'Unsubscribe' in join_response.get_data(as_text=True)

    unsubscribe_response = client.post(f'/event/{event_id}/unsubscribe', follow_redirects=True)
    assert 'You have unsubscribed from Unsubscribe Test.' in unsubscribe_response.get_data(as_text=True)
    assert 'Join This Event' in unsubscribe_response.get_data(as_text=True)
    with app.app_context():
        member = Member.query.filter_by(email='unsubscribe@example.com').one()
        event = db.session.get(Event, event_id)
        assert member not in event.members
        assert get_event_participation(event_id, member.id) is None


def test_staff_can_upload_event_documents_and_members_can_view_them():
    with app.app_context():
        staff = User(email='document-staff@example.com', role='staff')
        staff.set_password('Password123!')
        member = User(email='document-member@example.com', role='member')
        member.set_password('Password123!')
        event = Event(name='Document Test', date_from=date(2026, 8, 12))
        db.session.add_all([staff, member, event])
        db.session.commit()
        event_id = event.id

    client = app.test_client()
    client.post('/login', data={'email': 'document-staff@example.com', 'password': 'Password123!'})
    event_page = client.get(f'/events?selected_event_id={event_id}')
    assert 'Upload Document' not in event_page.get_data(as_text=True)
    edit_page = client.get(f'/event/{event_id}/edit')
    assert edit_page.status_code == 200
    assert 'Event Documents' in edit_page.get_data(as_text=True)
    assert 'Upload Document' in edit_page.get_data(as_text=True)
    response = client.post(
        f'/event/{event_id}/documents/add',
        data={'description': 'Event safety plan', 'document': (io.BytesIO(b'safety-plan'), 'safety-plan.pdf')},
        content_type='multipart/form-data',
        follow_redirects=True,
    )
    assert 'Event document added successfully.' in response.get_data(as_text=True)
    with app.app_context():
        document = EventDocument.query.filter_by(event_id=event_id).one()
        assert document.description == 'Event safety plan'
        assert document.document_data == b'safety-plan'
        document_id = document.id

    client.get('/logout')
    client.post('/login', data={'email': 'document-member@example.com', 'password': 'Password123!'})
    response = client.get(f'/event-document/{document_id}/file')
    assert response.status_code == 200
    assert response.data == b'safety-plan'
    assert response.mimetype == 'application/pdf'


def test_event_tides_are_cached_on_create_and_refresh_without_page_fetch():
    with app.app_context():
        admin = User(email='tides-admin@example.com', role='admin')
        admin.set_password('Password123!')
        db.session.add(admin)
        db.session.commit()

    client = app.test_client()
    client.post('/login', data={'email': 'tides-admin@example.com', 'password': 'Password123!'})
    cached_tides = {'station': 'Harbour', 'extremes': [{'type': 'High', 'time': '08:15', 'height': 3.2}]}

    with patch('app.get_event_tides', return_value=(cached_tides, None)) as fetch_tides:
        response = client.post('/events/new', data={
            'name': 'Tide Training',
            'date_from': '2026-07-14',
            'latitude': '54.9783',
            'longitude': '-1.6178',
        })

    assert response.status_code == 302
    assert fetch_tides.call_count == 1
    with app.app_context():
        event = Event.query.filter_by(name='Tide Training').one()
        assert event.tide_data == cached_tides
        event_id = event.id

    refreshed_tides = {'station': 'Harbour', 'extremes': [{'type': 'Low', 'time': '14:40', 'height': 0.8}]}
    with patch('app.get_event_tides', return_value=(refreshed_tides, None)) as fetch_tides:
        response = client.post(f'/event/{event_id}/edit', data={
            'name': 'Tide Training',
            'date_from': '2026-07-15',
            'latitude': '54.9783',
            'longitude': '-1.6178',
        })

    assert response.status_code == 302
    assert fetch_tides.call_count == 1
    with app.app_context():
        event = db.session.get(Event, event_id)
        assert event.tide_data == refreshed_tides

    with patch('app.get_event_tides', side_effect=AssertionError('page render fetched tides')):
        response = client.get(f'/events?selected_event_id={event_id}')

    assert response.status_code == 200
    assert 'Harbour' in response.get_data(as_text=True)
    assert '14:40' in response.get_data(as_text=True)


def test_signup_success_and_failure_messages():
    client = app.test_client()

    success_response = client.post('/signup', data={
        'first_name': 'New',
        'last_name': 'User',
        'email': 'newuser@example.com',
        'password': 'Password123!',
        'confirm_password': 'Password123!',
    }, follow_redirects=True)
    assert success_response.status_code == 200
    assert 'Account created successfully.' in success_response.get_data(as_text=True)

    weak_password_response = client.post('/signup', data={
        'first_name': 'Weak',
        'last_name': 'Password',
        'email': 'weak@example.com',
        'password': 'weak',
        'confirm_password': 'weak',
    }, follow_redirects=True)
    assert weak_password_response.status_code == 200
    assert 'password must be at least 8 characters' in weak_password_response.get_data(as_text=True).lower()

    fail_response = client.post('/signup', data={
        'first_name': 'Duplicate',
        'last_name': 'User',
        'email': 'newuser@example.com',
        'password': 'Password123!',
        'confirm_password': 'Password123!',
    }, follow_redirects=True)
    assert fail_response.status_code == 200
    assert 'Account creation failed: that email is already registered.' in fail_response.get_data(as_text=True)


def test_admin_login_and_search_filter():
    client = app.test_client()
    client.post('/login', data={'email': 'admin@noreply.local', 'password': 'admin123'}, follow_redirects=True)

    response = client.get('/?q=alice&status=Active&membership_type=Premier')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'Alice Brown' in html


def test_edit_and_delete_member():
    client = app.test_client()
    client.post('/login', data={'email': 'admin@noreply.local', 'password': 'admin123'})

    member = Member.query.filter_by(email='alice@example.com').first()
    response = client.post(f'/member/{member.id}/edit', data={
        'first_name': 'Alicia',
        'last_name': 'Brown',
        'email': 'alice@example.com',
        'phone': '555-1111',
        'membership_type': 'Family',
        'status': 'Inactive',
        'notes': 'Updated profile'
    }, follow_redirects=True)
    assert response.status_code == 200
    assert 'Alicia Brown' in response.get_data(as_text=True)

    delete_response = client.post(f'/member/{member.id}/delete', follow_redirects=True)
    assert delete_response.status_code == 200
    assert Member.query.filter_by(email='alice@example.com').count() == 0


def test_add_certification_with_db_qualification_and_upload():
    with app.app_context():
        member = Member.query.filter_by(email='alice@example.com').one()
        admin = User(email='certificate-admin@example.com', role='admin')
        admin.set_password('Password123!')
        qualification = Qualification(name='RYA Powerboat Level 2', category='Powerboat')
        db.session.add_all([admin, qualification])
        db.session.commit()
        member_id = member.id

    client = app.test_client()
    client.post('/login', data={'email': 'certificate-admin@example.com', 'password': 'Password123!'})
    response = client.post(
        f'/member/{member_id}/certification/add',
        data={
            'name': 'RYA Powerboat Level 2',
            'certification_number': 'PB-100',
            'issue_date': '2024-01-15',
            'expiry_date': '2028-01-15',
            'status': 'Valid',
            'certificate_copy': (io.BytesIO(b'certificate-data'), 'certificate.pdf'),
        },
        content_type='multipart/form-data',
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert 'Certification added successfully.' in response.get_data(as_text=True)

    with app.app_context():
        certification = Certification.query.filter_by(member_id=member_id).one()
        assert certification.name == 'RYA Powerboat Level 2'
        assert certification.certificate_copy is None
        assert certification.certificate_data == b'certificate-data'
        assert certification.certificate_filename == 'certificate.pdf'
        certification_id = certification.id

    certificate_response = client.get(f'/certification/{certification_id}/file')
    assert certificate_response.status_code == 200
    assert certificate_response.data == b'certificate-data'
    assert certificate_response.mimetype == 'application/pdf'

    response = client.post(
        f'/member/{member_id}/certification/{certification_id}/edit',
        data={
            'name': 'RYA Powerboat Level 2',
            'certification_number': 'PB-101',
            'issue_date': '2024-01-15',
            'expiry_date': '2029-01-15',
            'status': 'Valid',
            'certificate_copy': (io.BytesIO(b'replacement-certificate'), 'replacement.pdf'),
        },
        content_type='multipart/form-data',
        follow_redirects=True,
    )
    assert 'Certification updated successfully.' in response.get_data(as_text=True)
    assert 'id="certifications-tab" data-bs-toggle="tab" data-bs-target="#certifications" type="button" role="tab">Certifications</button>' in response.get_data(as_text=True)
    with app.app_context():
        certification = db.session.get(Certification, certification_id)
        assert certification.certification_number == 'PB-101'
        assert certification.expiry_date == date(2029, 1, 15)
        assert certification.certificate_data == b'replacement-certificate'
        assert certification.certificate_filename == 'replacement.pdf'

    response = client.post(f'/member/{member_id}/certification/{certification_id}/delete', follow_redirects=True)
    assert 'Certification deleted successfully.' in response.get_data(as_text=True)
    with app.app_context():
        assert db.session.get(Certification, certification_id) is None


def test_boat_crud_includes_radio_and_registration_fields():
    with app.app_context():
        member = Member.query.filter_by(email='alice@example.com').one()
        admin = User(email='boat-admin@example.com', role='admin')
        admin.set_password('Password123!')
        db.session.add(admin)
        db.session.commit()
        member_id = member.id

    client = app.test_client()
    client.post('/login', data={'email': 'boat-admin@example.com', 'password': 'Password123!'})
    response = client.post(f'/member/{member_id}/boat/add', data={
        'name': 'Northern Star', 'mmsi_number': '235123456', 'ssr_number': 'SSR-42', 'vhf': 'on', 'ais': 'on',
    }, follow_redirects=True)
    assert 'Boat added successfully.' in response.get_data(as_text=True)
    with app.app_context():
        boat = Boat.query.filter_by(member_id=member_id).one()
        assert (boat.mmsi_number, boat.ssr_number, boat.vhf, boat.ais) == ('235123456', 'SSR-42', True, True)
        boat_id = boat.id

    response = client.post(f'/member/{member_id}/boat/{boat_id}/edit', data={
        'name': 'Northern Star', 'mmsi_number': '235654321', 'ssr_number': 'SSR-99', 'vhf': 'on',
    }, follow_redirects=True)
    assert 'Boat updated successfully.' in response.get_data(as_text=True)
    assert 'id="boats-tab" data-bs-toggle="tab" data-bs-target="#boats" type="button" role="tab">Boats</button>' in response.get_data(as_text=True)
    with app.app_context():
        boat = db.session.get(Boat, boat_id)
        assert (boat.mmsi_number, boat.ssr_number, boat.vhf, boat.ais) == ('235654321', 'SSR-99', True, False)

    response = client.post(f'/member/{member_id}/boat/{boat_id}/delete', follow_redirects=True)
    assert 'Boat deleted successfully.' in response.get_data(as_text=True)
    with app.app_context():
        assert db.session.get(Boat, boat_id) is None


def test_add_event_expense_for_assigned_member_with_receipt():
    with app.app_context():
        member = Member.query.filter_by(email='alice@example.com').first()
        member_user = User(email='alice@example.com', role='member')
        member_user.set_password('Password123!')
        admin = User(email='expense-admin@example.com', role='admin')
        admin.set_password('Password123!')
        staff = User(email='expense-staff@example.com', role='staff')
        staff.set_password('Password123!')
        event = Event(name='Training Day', date_from=date(2026, 9, 1))
        event.members.append(member)
        db.session.add_all([
            member_user,
            admin,
            staff,
            event,
            EventParticipation(event=event, member=member),
            LookupItem(category='expense_type', value='Vehicle Fuel'),
        ])
        db.session.commit()
        member_id = member.id
        event_id = event.id
        staff_id = staff.id
        admin_id = admin.id

    client = app.test_client()
    client.post('/login', data={'email': 'alice@example.com', 'password': 'Password123!'})
    member_page = client.get(f'/member/{member_id}')
    assert 'Pending approval' in member_page.get_data(as_text=True)
    assert f'expenseModal{event_id}' not in member_page.get_data(as_text=True)
    pending_response = client.post(
        f'/member/{member_id}/expenses/add',
        data={
            'event_id': str(event_id),
            'expense_type': 'Vehicle Fuel',
            'expense_date': '2026-09-01',
            'amount': '42.50',
            'approved_by_user_id': str(staff_id),
            'receipt_image': (io.BytesIO(b'image-data'), 'receipt.png'),
        },
        content_type='multipart/form-data',
        follow_redirects=True,
    )
    assert 'participation must be approved' in pending_response.get_data(as_text=True).lower()

    client.get('/logout')
    client.post('/login', data={'email': 'expense-staff@example.com', 'password': 'Password123!'})
    approval_response = client.post(f'/event/{event_id}/member/{member_id}/approve', follow_redirects=True)
    assert 'is approved for Training Day.' in approval_response.get_data(as_text=True)

    client.get('/logout')
    client.post('/login', data={'email': 'alice@example.com', 'password': 'Password123!'})
    approved_member_page = client.get(f'/member/{member_id}')
    assert f'expenseModal{event_id}' in approved_member_page.get_data(as_text=True)
    assert 'Add Expense: Training Day' in approved_member_page.get_data(as_text=True)
    assert 'Select a reviewer' not in approved_member_page.get_data(as_text=True)
    assert 'Approved By' not in approved_member_page.get_data(as_text=True)
    response = client.post(
        f'/member/{member_id}/expenses/add',
        data={
            'event_id': str(event_id),
            'expense_type': 'Vehicle Fuel',
            'expense_date': '2026-09-01',
            'amount': '42.50',
            'receipt_image': (io.BytesIO(b'image-data'), 'receipt.png'),
        },
        content_type='multipart/form-data',
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert 'Event expense added successfully.' in response.get_data(as_text=True)
    with app.app_context():
        expense = EventExpense.query.filter_by(member_id=member_id, event_id=event_id).one()
        assert expense.expense_type == 'Vehicle Fuel'
        assert expense.amount == Decimal('42.50')
        assert expense.approved_by_user_id != staff_id
        assert expense.status == 'Pending'
        assert expense.receipt_image is None
        assert expense.receipt_data == b'image-data'
        assert expense.receipt_filename == 'receipt.png'
        expense_id = expense.id

    receipt_response = client.get(f'/expense/{expense_id}/receipt')
    assert receipt_response.status_code == 200
    assert receipt_response.data == b'image-data'
    assert receipt_response.mimetype == 'image/png'

    unselected_event_page = client.get(f'/member/{member_id}')
    unselected_event_html = unselected_event_page.get_data(as_text=True)
    assert 'member-event-expenses d-none' in unselected_event_html
    selected_event_page = client.get(f'/member/{member_id}?selected_event_id={event_id}')
    selected_event_html = selected_event_page.get_data(as_text=True)
    assert selected_event_page.status_code == 200
    assert 'window.location=' not in selected_event_html
    assert 'function selectMemberEvent(eventId)' in selected_event_html
    assert 'id="events-tab" data-bs-toggle="tab" data-bs-target="#events" type="button" role="tab">Events</button>' in selected_event_html
    assert 'id="events" role="tabpanel" aria-labelledby="events-tab"' in selected_event_html
    assert 'Expense Records: Training Day' in selected_event_html
    assert 'Vehicle Fuel' in selected_event_html

    client.get('/logout')
    client.post('/login', data={'email': 'expense-staff@example.com', 'password': 'Password123!'})
    staff_review = client.get(f'/expenses?event_id={event_id}')
    assert staff_review.status_code == 200
    assert 'Event Expenses' in staff_review.get_data(as_text=True)
    assert 'Vehicle Fuel' in staff_review.get_data(as_text=True)
    assert '42.50' in staff_review.get_data(as_text=True)

    client.get('/logout')
    client.post('/login', data={'email': 'expense-admin@example.com', 'password': 'Password123!'})
    approve_response = client.post(f'/expense/{expense_id}/approve', follow_redirects=True)
    assert 'Expense approved successfully.' in approve_response.get_data(as_text=True)
    pay_response = client.post(f'/expense/{expense_id}/pay', follow_redirects=True)
    assert 'Expense marked as paid successfully.' in pay_response.get_data(as_text=True)
    undo_paid_response = client.post(f'/expense/{expense_id}/undo_paid', follow_redirects=True)
    assert 'Paid status removed. The expense is approved again.' in undo_paid_response.get_data(as_text=True)
    undo_approved_response = client.post(f'/expense/{expense_id}/undo_approved', follow_redirects=True)
    assert 'Approval removed. The expense is pending again.' in undo_approved_response.get_data(as_text=True)
    print_response = client.get(f'/expenses/{event_id}/print')
    assert print_response.status_code == 200
    assert 'Expense Review' in print_response.get_data(as_text=True)

    with app.app_context():
        expense = db.session.get(EventExpense, expense_id)
        assert expense.status == 'Pending'
        assert expense.reviewed_by_user_id is None
        assert expense.reviewed_at is None
        assert expense.paid_by_user_id is None
        assert expense.paid_at is None
