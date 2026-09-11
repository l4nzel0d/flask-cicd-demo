"""Демонстрационное Flask-приложение для практической работы №4 (CI/CD).

Приложение намеренно простое: его задача — наглядно показать, в каком
окружении и какая именно сборка сейчас работает. Именно эти сведения
проверяет Jenkins Pipeline на стадиях smoke-теста и верификации.
"""

import os
import socket

from flask import Flask, jsonify, render_template

# Оформление страницы зависит от окружения: цвет и подпись задаются здесь,
# а конкретное окружение приходит из переменной APP_ENV при запуске контейнера.
ENV_STYLES = {
    "production": {"color": "#16a34a", "label": "PRODUCTION"},
    "staging": {"color": "#f59e0b", "label": "STAGING"},
    "smoke": {"color": "#0ea5e9", "label": "SMOKE TEST"},
    "test": {"color": "#6366f1", "label": "TEST"},
    "local": {"color": "#64748b", "label": "LOCAL"},
}

DEFAULT_STYLE = {"color": "#dc2626", "label": "UNKNOWN"}


def build_info() -> dict:
    """Собрать сведения о текущей сборке и окружении.

    Переменные читаются из os.environ при каждом вызове, а не один раз при
    импорте модуля. Это позволяет тестам подменять их через monkeypatch.setenv.
    """
    env = os.environ.get("APP_ENV", "local")
    style = ENV_STYLES.get(env, DEFAULT_STYLE)
    return {
        "env": env,
        "label": style["label"],
        "color": style["color"],
        "version": os.environ.get("APP_VERSION", "0.0.0"),
        "build": os.environ.get("BUILD_NUMBER", "0"),
        "commit": os.environ.get("GIT_COMMIT", "unknown"),
        "hostname": socket.gethostname(),
    }


def create_app(config: dict | None = None) -> Flask:
    """Фабрика приложения (application factory).

    Создание приложения внутри функции, а не на уровне модуля, позволяет
    тестам получать изолированный экземпляр со своей конфигурацией.
    """
    app = Flask(__name__)
    if config:
        app.config.update(config)

    @app.get("/")
    def index():
        """Страница для человека: её открывают в браузере и снимают скриншот."""
        return render_template("index.html", info=build_info())

    @app.get("/health")
    def health():
        """Машинная проверка живости. Используется пайплайном и HEALTHCHECK."""
        info = build_info()
        return jsonify(
            status="ok",
            env=info["env"],
            build=info["build"],
            version=info["version"],
            commit=info["commit"],
            hostname=info["hostname"],
        )

    @app.get("/env")
    def env_plain():
        """Окружение простым текстом — удобно сравнивать в shell-скрипте."""
        return build_info()["env"], 200, {"Content-Type": "text/plain; charset=utf-8"}

    @app.get("/api/info")
    def api_info():
        """Полный «паспорт» экземпляра. Архивируется как артефакт сборки."""
        return jsonify(build_info())

    return app


# Точка входа для gunicorn: команда `gunicorn app:app` берёт этот объект.
app = create_app()


if __name__ == "__main__":
    # Путь для локального запуска без контейнера. В контейнере работает gunicorn.
    app.run(host="0.0.0.0", port=int(os.environ.get("APP_PORT", "8000")))
