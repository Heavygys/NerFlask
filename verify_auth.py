import os

os.environ["NERFLASK_DATABASE_URI"] = "sqlite:///northern_exposure_test.db"

from app import Member, User, app, db

with app.app_context():
    User.query.delete()
    Member.query.delete()
    db.session.commit()

    admin = User(email='admin@noreply.local', role='admin')
    admin.set_password('admin123')
    db.session.add(admin)
    db.session.commit()

    client = app.test_client()
    login_page = client.get('/login')
    print('LOGIN_STATUS', login_page.status_code)
    print('LOGIN_HAS_CREATE', 'Create account' in login_page.get_data(as_text=True))

    signup_response = client.post(
        '/signup',
        data={
            'first_name': 'Test',
            'last_name': 'User',
            'email': 'testuser@example.com',
            'password': 'pass123',
            'confirm_password': 'pass123',
        },
        follow_redirects=False,
    )
    print('SIGNUP_STATUS', signup_response.status_code)
    print('SIGNUP_LOCATION', signup_response.headers.get('Location'))
    print('USER_COUNT', User.query.filter_by(email='testuser@example.com').count())
    print('MEMBER_COUNT', Member.query.filter_by(email='testuser@example.com').count())

    login_response = client.post(
        '/login',
        data={'email': 'admin@noreply.local', 'password': 'admin123'},
        follow_redirects=False,
    )
    print('ADMIN_LOGIN_LOCATION', login_response.headers.get('Location'))
