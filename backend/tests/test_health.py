def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "version" in body


def test_root(client):
    r = client.get("/")
    assert r.status_code == 200
    assert r.json()["name"] == "TCAlpha API"


def test_symbol_normalize():
    from app.utils.symbol import normalize

    assert normalize("600000") == "sh600000"
    assert normalize("000001") == "sz000001"
    assert normalize("430047") == "bj430047"
    assert normalize("sh.600000") == "sh600000"
    assert normalize("600000.SH") == "sh600000"
