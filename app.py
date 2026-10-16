import os
import secrets
import time
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, g, jsonify, request, send_from_directory
from pydantic import ValidationError

from fitness.llm import LLMError
from fitness.service import Service
from fitness.store import Store

load_dotenv()


def create_app(store=None, service=None):
    app = Flask(__name__, static_folder="web", static_url_path="/assets")
    app.config["MAX_CONTENT_LENGTH"] = 32 * 1024
    store = store or Store()
    service = service or Service(store)
    app.extensions["fitness"] = service

    @app.before_request
    def identify():
        g.new_session = None
        if not request.path.startswith("/api/"):
            return
        token = request.cookies.get("fitness_session", "")
        with store.connect() as db:
            db.execute("DELETE FROM sessions WHERE expires < ?", (time.time(),))
            session = db.execute("SELECT * FROM sessions WHERE token=?", (token,)).fetchone()
            if not session:
                token, owner, csrf = secrets.token_urlsafe(32), "web:"+secrets.token_urlsafe(24), secrets.token_urlsafe(32)
                db.execute("INSERT INTO sessions VALUES (?,?,?,?)", (token, owner, csrf, time.time()+30*86400))
                g.new_session = token
            else:
                owner, csrf = session["owner"], session["csrf"]
        g.owner, g.csrf = owner, csrf
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            if not secrets.compare_digest(request.headers.get("X-CSRF-Token", ""), csrf):
                return jsonify(error="Обновите страницу и повторите действие"), 403
            if not request.is_json:
                return jsonify(error="Ожидаются данные JSON"), 415

    @app.after_request
    def headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        if getattr(g, "new_session", None):
            response.set_cookie("fitness_session", g.new_session, httponly=True,
                secure=os.getenv("COOKIE_SECURE", "false").lower() == "true", samesite="Strict", max_age=30*86400)
        return response

    @app.errorhandler(ValidationError)
    def invalid(error):
        # Never include input values in validation responses/logs.
        fields = ", ".join(".".join(map(str, e["loc"])) for e in error.errors(include_input=False))
        return jsonify(error="Проверьте поля анкеты: "+fields), 400

    @app.errorhandler(ValueError)
    def bad_request(error):
        return jsonify(error=str(error)), 400

    @app.errorhandler(LLMError)
    def provider_error(error):
        return jsonify(error=str(error)), 503

    @app.get("/")
    def index():
        return send_from_directory(app.static_folder, "index.html")

    @app.get("/api/state")
    def state():
        username = os.getenv("TELEGRAM_BOT_USERNAME", "").lstrip("@")
        return jsonify(csrf=g.csrf, profile=store.get_json("profiles", g.owner),
            programs=store.programs(g.owner), feedback=store.feedback(g.owner),
            configured=service.llm.configured, telegram_url="https://t.me/"+username if username and username.replace("_", "").isalnum() else None)

    @app.post("/api/profile")
    def profile():
        return jsonify(profile=service.save_profile(g.owner, request.get_json()))

    @app.post("/api/generate")
    def generate():
        raw = request.get_json()
        changes = raw.get("changes", "")
        if not isinstance(changes, str) or len(changes) > 1500:
            raise ValueError("Опишите изменения не более чем в 1500 символах")
        return jsonify(service.generate(g.owner, changes))

    @app.post("/api/programs/<int:pid>/confirm")
    def confirm(pid):
        store.confirm(g.owner, pid)
        return jsonify(ok=True)

    @app.post("/api/explain")
    def explain():
        raw = request.get_json()
        try:
            indices = [int(raw[k]) for k in ("program_id", "workout_index", "exercise_index")]
        except (KeyError, TypeError, ValueError):
            raise ValueError("Выберите упражнение") from None
        return jsonify(service.explain(g.owner, *indices))

    @app.post("/api/feedback")
    def feedback():
        return jsonify(feedback=service.feedback(g.owner, request.get_json()))

    @app.get("/health")
    def health():
        return jsonify(status="ok")

    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=int(os.getenv("PORT", "8000")), debug=False)
