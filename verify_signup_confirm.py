import os

os.environ["NERFLASK_DATABASE_URI"] = "sqlite:///northern_exposure_test.db"

from app import app, db


def main():
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)

    with app.app_context():
        db.drop_all()
        db.create_all()

    client = app.test_client()

    success_response = client.post(
        "/signup",
        data={
            "first_name": "Test",
            "last_name": "User",
            "email": "test@example.com",
            "password": "abc123",
            "confirm_password": "abc123",
        },
        follow_redirects=True,
    )
    print("SUCCESS_STATUS", success_response.status_code)
    print("SUCCESS_TEXT", "Account created successfully." in success_response.get_data(as_text=True))

    failure_response = client.post(
        "/signup",
        data={
            "first_name": "Test2",
            "last_name": "User2",
            "email": "test@example.com",
            "password": "abc123",
            "confirm_password": "abc123",
        },
        follow_redirects=True,
    )
    print("FAIL_STATUS", failure_response.status_code)
    print(
        "FAIL_TEXT",
        "Account creation failed: that email is already registered." in failure_response.get_data(as_text=True),
    )


if __name__ == "__main__":
    main()
