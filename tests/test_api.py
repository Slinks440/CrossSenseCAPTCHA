import json

def test_index_route(client, mocker):
    # Mocking the send_file behavior to avoid missing index.html during testing
    mocker.patch('src.backend.app.send_file', return_value="Mocked index.html")
    response = client.get('/')
    assert response.status_code == 200
    assert b"Mocked index.html" in response.data

def test_api_init(client, mocker):
    # Mock redis connection
    mock_redis = mocker.patch('src.backend.app.redis_conn')
    mock_redis.set.return_value = True
    mock_redis.get.return_value = b'1'

    response = client.get('/api/init')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert "init_seed" in data
    assert "difficulty" in data
    assert data["difficulty"] == 1

import pytest
import base64

def test_get_captcha(client, mocker):
    mock_redis = mocker.patch('src.backend.app.redis_conn')
    def mock_redis_get(key):
        if b'pow:' in str(key).encode() or 'pow:' in str(key):
            return b'test_seed'
        return None
    mock_redis.get.side_effect = mock_redis_get
    mock_redis.llen.return_value = 10
    # Mock brpop returning a generated challenge JSON
    mock_challenge = {
        "challenge_id": "test_chall_123",
        "answer": {"target": {"bbox": [10, 10, 20, 20]}, "question_text": "Click target"},
        "asset_dir": "/tmp/test"
    }
    mock_redis.brpop.return_value = (b'pool_key', json.dumps(mock_challenge).encode())
    
    # Mock validate_pow bypass if needed
    mock_pow = mocker.patch('src.backend.app.pow_ext', None)
    
    # Set dummy session cookie
    client.set_cookie('csc_session', 'dummy_session_id_for_testing_purposes', domain='localhost')

    response = client.post('/api/captcha', json={'pow_result': 'test_hash'})
    assert response.status_code == 200
    data = json.loads(response.data)
    assert "challenge_id" in data
    assert data["challenge_id"] == "test_chall_123"
    assert "server_pub_key" in data

def test_verify_captcha_replay(client, mocker):
    client.set_cookie('csc_session', 'dummy_session_id_for_testing_purposes', domain='localhost')
    
    # If redis returns None for crypto material, it's treated as replay
    mock_getdel = mocker.patch('src.backend.app.getdel_script')
    mock_getdel.return_value = None
    
    response = client.post('/api/verify', json={
        'challenge_id': 'test_chall_123',
        'js_entropy': 'entropy',
        'client_pub': 'pub',
        'ciphertext': 'cipher'
    })
    
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["success"] is False
    assert "Verification failed" in data["msg"]
