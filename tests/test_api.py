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
