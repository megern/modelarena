from fastapi.testclient import TestClient
from app.main import app

def test_request_size_limit():
    response = TestClient(app).post('/analyze', content=b' ' * 2097153, headers={'content-type': 'application/json'})
    assert response.status_code == 413

def test_nonfinite_and_nested_json_rejected_before_calculation():
    client = TestClient(app)
    for content in ['{"x":1e400}', '{"x":NaN}', '[' * 40 + '0' + ']' * 40]:
        assert client.post('/analyze', content=content, headers={'content-type': 'application/json'}).status_code == 422
