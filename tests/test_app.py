import app


def test_home_serves_static_dashboard_without_database_env():
    client = app.app.test_client()
    response = client.get("/")
    assert response.status_code == 200
    assert b"Match Signal" in response.data
