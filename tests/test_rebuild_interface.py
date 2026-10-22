from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_task_interface_and_local_assets_are_served():
    response = client.get("/")
    assert response.status_code == 200
    assert "v0.4.0" in response.text
    assert "sample" in response.text
    assert "/assets/ui.mjs" in response.text
    assert "cdn" not in response.text.lower()
    for name in ["common.mjs", "ui.mjs", "style.css"]:
        asset = client.get("/assets/" + name)
        assert asset.status_code == 200 and len(asset.content) > 100
    assert client.get("/assets/missing.mjs").status_code == 404

def test_served_guide_documents_methods_and_current_version():
    guide = client.get("/guide")
    assert guide.status_code == 200
    assert "0.4.0" in guide.text
    assert "synthetic" in guide.text.lower()
    assert "Troubleshooting" in guide.text or "troubleshooting" in guide.text
    assert app.version == "0.4.0"
