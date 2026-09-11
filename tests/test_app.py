"""Модульные тесты приложения.

Выполняются внутри контейнера, собранного по ступени `test` Dockerfile.
Отчёт в формате JUnit XML забирается пайплайном и публикуется в Jenkins.
"""

import pytest

from app import create_app


@pytest.fixture
def client():
    """Тестовый клиент Flask: позволяет слать запросы без реального сервера."""
    app = create_app({"TESTING": True})
    return app.test_client()


def test_health_returns_ok(client):
    """Эндпоинт /health отвечает 200 и сообщает статус ok."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json()["status"] == "ok"


def test_health_reports_build_number(client, monkeypatch):
    """Номер сборки берётся из окружения — на этом держится проверка версии."""
    monkeypatch.setenv("BUILD_NUMBER", "42")
    response = client.get("/health")
    assert response.get_json()["build"] == "42"


def test_env_endpoint_defaults_to_local(client, monkeypatch):
    """Без APP_ENV приложение считает себя локальным."""
    monkeypatch.delenv("APP_ENV", raising=False)
    response = client.get("/env")
    assert response.get_data(as_text=True) == "local"


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_env_endpoint_follows_variable(client, monkeypatch, environment):
    """Один и тот же образ становится нужной средой через переменную APP_ENV."""
    monkeypatch.setenv("APP_ENV", environment)
    response = client.get("/env")
    assert response.get_data(as_text=True) == environment


def test_index_page_renders(client, monkeypatch):
    """Главная страница отдаётся и содержит подпись окружения."""
    monkeypatch.setenv("APP_ENV", "staging")
    response = client.get("/")
    assert response.status_code == 200
    assert "STAGING" in response.get_data(as_text=True)


def test_api_info_contains_all_fields(client):
    """Паспорт экземпляра содержит все поля, ожидаемые пайплайном."""
    payload = client.get("/api/info").get_json()
    for field in ("env", "label", "color", "version", "build", "commit", "hostname"):
        assert field in payload


def test_unknown_route_returns_404(client):
    """Несуществующий маршрут возвращает 404, а не ошибку сервера."""
    assert client.get("/no-such-page").status_code == 404
