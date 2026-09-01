import os

os.environ["NERFLASK_DATABASE_URI"] = "sqlite:///northern_exposure_test.db"

from app import app

with app.test_client() as client:
    response = client.get('/')
    print('STATUS', response.status_code)
    print('HAS_TITLE', 'Northern Exposure Reduce' in response.get_data(as_text=True))
    print('CONTENT_TYPE', response.headers.get('Content-Type', ''))
