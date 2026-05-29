import pytest
import os
import sys

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Set dummy environment variables required by app.py
os.environ["JWT_SECRET"] = "dummy_test_secret"
os.environ["REDIS_HOST"] = "127.0.0.1"

from src.backend.app import app

@pytest.fixture
def client():
    app.config["TESTING"] = True
    app.config["JWT_SECRET"] = "dummy_test_secret"
    with app.test_client() as client:
        yield client
