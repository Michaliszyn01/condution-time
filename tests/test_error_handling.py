import logging
import re


def test_internal_error_uses_layout_logs_traceback_and_keeps_health(
    app,
    client,
    caplog,
):
    endpoint = "test_sensitive_page_failure"

    def fail():
        raise ValueError("falha controlada de regressão")

    app.add_url_rule("/_test/failure", endpoint, fail)
    app.config["PROPAGATE_EXCEPTIONS"] = False

    with caplog.at_level(logging.ERROR, logger=app.logger.name):
        response = client.get("/_test/failure")

    assert response.status_code == 500
    assert "Esta página encontrou um problema." in response.text
    assert re.search(r"CT-\d{14}-[0-9A-F]{6}", response.text)
    assert "falha controlada de regressão" not in response.text
    assert "ValueError: falha controlada de regressão" in caplog.text
    assert "GET /_test/failure" in caplog.text

    health = client.get("/health")
    assert health.status_code == 200
    assert health.get_json()["status"] == "ok"
