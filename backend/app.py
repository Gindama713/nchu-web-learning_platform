"""Flask entry point. Business blueprints own their routes and tables."""

import os
import secrets
import sqlite3
from pathlib import Path

import click
from flask import Flask, g, jsonify, request
from werkzeug.exceptions import HTTPException
from werkzeug.security import generate_password_hash

from backend.apis import (
    analytics,
    attempts,
    attendance,
    courses,
    experiments,
    identity,
    papers,
    practices,
    questions,
    quizzes,
    recognition,
    resources,
    warnings,
)
from backend.apis.knowledge import blueprint as knowledge_blueprint
from backend.shared.api import ApiError, request_id, result, stamp
from backend.shared.auth import COOKIE, check_csrf
from backend.shared.catalog import MODULES
from backend.shared.db import close_db, connect, database_ready, migrate


def create_app(config=None):
    app = Flask(__name__)
    environment = os.environ.get("APP_ENV", "development")
    secret = os.environ.get("SECRET_KEY")
    origin = os.environ.get("APP_ORIGIN", "http://127.0.0.1:5173")
    if environment == "production" and (not secret or len(secret) < 32 or not origin.startswith("https://")):
        raise RuntimeError("Production requires a strong SECRET_KEY and HTTPS APP_ORIGIN")
    app.config.update(
        APP_ENV=environment,
        SECRET_KEY=secret or secrets.token_hex(32),
        APP_ORIGIN=origin,
        COOKIE_SECURE=environment == "production",
        DATABASE_PATH=os.environ.get("DATABASE_PATH", "instance/app.db"),
        UPLOAD_ROOT=os.environ.get("UPLOAD_ROOT", "instance/uploads"),
    )
    if config:
        app.config.update(config)
    app.teardown_appcontext(close_db)
    for blueprint in (identity.bp, courses.bp, attendance.bp, analytics.bp, warnings.bp,
                      recognition.bp, questions.bp, papers.bp, attempts.bp, practices.bp, quizzes.bp,
                      resources.bp, experiments.bp):
        app.register_blueprint(blueprint, url_prefix="/api/v1")
    app.register_blueprint(knowledge_blueprint)

    @app.before_request
    def protect_writes():
        if request.path.startswith("/api/v1/") and request.method in ("POST", "PATCH", "PUT", "DELETE"):
            if request.headers.get("Origin") != app.config["APP_ORIGIN"]:
                raise ApiError(403, "CSRF_FAILED", "Untrusted origin")
            if request.path not in ("/api/v1/auth/register", "/api/v1/auth/login"):
                check_csrf()

    @app.after_request
    def security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        if getattr(g, "session_token", None) and not getattr(g, "logged_out", False):
            response.set_cookie(COOKIE, g.session_token, httponly=True,
                                secure=app.config["COOKIE_SECURE"], samesite="Lax", path="/", max_age=7200)
        return response

    @app.errorhandler(ApiError)
    def api_error(error):
        response = jsonify(error={"code": error.code, "message": error.message, "details": error.details},
                           request_id=request_id())
        if error.status == 429:
            response.headers["Retry-After"] = "60"
        return response, error.status

    @app.errorhandler(sqlite3.OperationalError)
    def sqlite_error(error):
        busy = "locked" in str(error).lower() or "busy" in str(error).lower()
        code = "DB_BUSY" if busy else "INTERNAL_ERROR"
        response = jsonify(error={"code": code, "message": "Database temporarily unavailable" if busy else "Internal error",
                                  "details": {}}, request_id=request_id())
        return response, 503 if busy else 500

    @app.errorhandler(sqlite3.IntegrityError)
    def integrity_error(_error):
        return jsonify(error={"code": "DATA_CONFLICT", "message": "Data conflict", "details": {}},
                       request_id=request_id()), 409

    @app.errorhandler(Exception)
    def unexpected_error(error):
        if isinstance(error, HTTPException):
            status = error.code or 500
            return jsonify(error={"code": "NOT_FOUND" if status == 404 else "HTTP_ERROR",
                                  "message": error.description, "details": {}}, request_id=request_id()), status
        app.logger.exception("Unhandled request error")
        return jsonify(error={"code": "INTERNAL_ERROR", "message": "Internal error", "details": {}},
                       request_id=request_id()), 500

    @app.get("/api/v1/health")
    def health():
        db_ready = database_ready(app.config["DATABASE_PATH"])
        jar = os.environ.get("LOGISIM_JAR_PATH")
        # The grader and sandbox are separate work; a JAR path alone is not readiness.
        grader_ready = False
        status = "ready" if db_ready and grader_ready else "degraded"
        return result({"web_ready": True, "db_ready": db_ready, "grader_ready": grader_ready,
                       "status": status, "grader_configured": bool(jar and Path(jar).is_file())},
                      200 if status == "ready" else 503)

    @app.get("/api/v1/modules")
    def modules():
        return result(MODULES)

    @app.cli.command("db-upgrade")
    def db_upgrade():
        migrate(app.config["DATABASE_PATH"])
        click.echo("Database migrations applied")

    @app.cli.command("admin-create")
    @click.option("--student-no", prompt=True)
    @click.option("--name", prompt=True)
    @click.password_option()
    def admin_create(student_no, name, password):
        from backend.apis.identity import password as validate_password
        from backend.apis.identity import student_no as validate_number

        with app.app_context():
            validate_number(student_no)
            name = name.strip()
            if not 1 <= len(name) <= 50:
                raise click.BadParameter("name must be 1–50 characters")
            validate_password(password)
            db = connect(app.config["DATABASE_PATH"])
            try:
                db.execute("BEGIN IMMEDIATE")
                db.execute("INSERT INTO user(student_no,name,password_hash,role,active,created_at,updated_at) "
                           "VALUES(?,?,?,'admin',1,?,?)",
                           (student_no, name, generate_password_hash(password), stamp(), stamp()))
                db.commit()
            except BaseException:
                db.rollback()
                raise
            finally:
                db.close()
        click.echo("Administrator created")

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
