import json
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_api_matches_core():
    payload = json.loads((Path(__file__).parents[1]/"examples/synthetic.json").read_text())
    result = client.post("/analyze", json=payload)
    assert result.status_code == 200
    assert isinstance(result.json(), dict)
    assert client.get("/health").json() == {"status":"ok"}
    assert 'ModelArena' in client.get("/").text

def test_bad_payload_is_validation_error():
    assert client.post("/analyze",json={"k":-1,"rows":[],"cases":[],"tools":"not a list"}).status_code==422
