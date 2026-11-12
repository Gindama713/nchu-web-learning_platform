"""Flask entry point. Business blueprints own their routes and tables."""

import os
import secrets
import sqlite3
import time
from pathlib import Path
from urllib.parse import urlparse

import click
from flask import Flask, g, jsonify, request, send_from_directory
from werkzeug.exceptions import HTTPException
from werkzeug.security import generate_password_hash

from backend.apis import (
    alu,
    analytics,
    attempts,
    attendance,
    circuit_lab,
    classroom,
    courses,
    demo,
    experiments,
    grading,
    identity,
    logs,
    meta,
    papers,
    practices,
    preparations,
    questions,
    quizzes,
    recognition,
    recommendations,
    resources,
    seat_swap,
    warnings,
    wiring,
)
from backend.apis.knowledge import blueprint as knowledge_blueprint
from backend.apis.qa import blueprint as qa_blueprint
from backend.models.qa import IndexCache
from backend.shared.api import ApiError, request_id, result, stamp
from backend.shared.auth import COOKIE, check_csrf
from backend.shared.catalog import MODULES
from backend.shared.db import close_db, connect, database_ready, migrate


def development_secret(directory):
    """开发环境把 SECRET_KEY 固定下来，存在数据库旁边。

    CSRF 值是 hmac(SECRET_KEY, session_token)：原来每次启动都随机生成 KEY，
    重启一次后端，页面手里那个值就和 session 里存的哈希对不上——读接口照常 200，
    所有写操作却 403 CSRF_FAILED，看起来就是「按钮点了没反应」。
    这里把生成的 KEY 写到库同级的 dev_secret_key 复用（跟着这份数据走，不跟着代码走）；
    生产仍然强制走环境变量。
    """
    path = os.path.join(directory or "instance", "dev_secret_key")
    try:
        with open(path, encoding="utf-8") as handle:
            saved = handle.read().strip()
        if len(saved) >= 32:
            return saved
    except OSError:
        pass
    generated = secrets.token_hex(32)
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(generated)
    except OSError:
        pass
    return generated


def create_app(config=None):
    app = Flask(__name__)
    environment = os.environ.get("APP_ENV", "development")
    secret = os.environ.get("SECRET_KEY")
    origin = os.environ.get("APP_ORIGIN", "http://127.0.0.1:5173")
    database = os.environ.get("DATABASE_PATH", "instance/app.db")
    # 配置里已经给了密钥（测试就是这么做的）就不要再去落文件
    provided_secret = secret or (config or {}).get("SECRET_KEY")
    if environment == "production" and (not secret or len(secret) < 32 or not origin.startswith("https://")):
        raise RuntimeError("Production requires a strong SECRET_KEY and HTTPS APP_ORIGIN")
    app.config.update(
        APP_ENV=environment,
        SECRET_KEY=provided_secret or development_secret(os.path.dirname(database)),
        APP_ORIGIN=origin,
        COOKIE_SECURE=environment == "production",
        DATABASE_PATH=database,
        UPLOAD_ROOT=os.environ.get("UPLOAD_ROOT", "instance/uploads"),
    )
    if config:
        app.config.update(config)
    app.teardown_appcontext(close_db)
    for blueprint in (identity.bp, courses.bp, attendance.bp, analytics.bp, warnings.bp,
                      recognition.bp, questions.bp, papers.bp, attempts.bp, practices.bp, quizzes.bp,
                      resources.bp, experiments.bp, preparations.bp, demo.bp, wiring.bp, alu.bp, logs.bp,
                      recommendations.bp, grading.bp, classroom.bp, seat_swap.bp, circuit_lab.bp):
        app.register_blueprint(blueprint, url_prefix="/api/v1")
    if not app.config.get("TESTING"):
        # SPEC-018：Web 进程每5秒扫描过期运行/排队超时（DBD 第7节）。
        from backend.engines.grading import start_scanner
        start_scanner(app)
    app.register_blueprint(knowledge_blueprint)
    # SPEC-019：/help 与 /who 按任务书挂在站点根路径，供互测方公开访问。
    app.register_blueprint(meta.bp)
    app.extensions["qa_cache"] = IndexCache()
    app.register_blueprint(qa_blueprint)

    @app.before_request
    def mark_start():
        g.request_started = time.perf_counter()

    def trusted_origin(origin):
        """课堂部署时 IP 不固定，Origin 除白名单外，与本次请求 Host 同源也放行。

        跨站页面发出的请求带的是它自己的 Origin，不会等于我们的 Host，
        因此这条放宽不会削弱 CSRF 防护。
        """
        if not origin:
            return False
        if origin == app.config["APP_ORIGIN"]:
            return True
        return urlparse(origin).netloc == request.host

    @app.before_request
    def protect_writes():
        if request.path.startswith("/api/v1/") and request.method in ("POST", "PATCH", "PUT", "DELETE"):
            if not trusted_origin(request.headers.get("Origin")):
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
        started = getattr(g, "request_started", None)
        logs.write_access(response.status_code,
                          (time.perf_counter() - started) * 1000 if started else 0.0)
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
        # SPEC-018：固定 JAR 存在且身份可校验才视为评测就绪；清理失败禁止新任务。
        from backend.engines.grading import grader_ready
        ready = grader_ready()
        status = "ready" if db_ready and ready else "degraded"
        return result({"web_ready": True, "db_ready": db_ready, "grader_ready": ready,
                       "status": status},
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

    serve_frontend(app)
    return app


def serve_frontend(app):
    """SERVE_DIST=1 时由 Flask 直接托管前端构建产物。

    课堂和教师沙箱往往只给一个 Python 环境，没有 Node，也就跑不了 Vite。
    构建一次后把 frontend/dist 一起带走，用这个开关就能单进程打开完整界面，
    不必再起第二个服务、也不会因为跨端口而触发 Origin/CSRF 校验。
    """
    if os.environ.get("SERVE_DIST") != "1":
        return
    dist = Path(__file__).resolve().parents[1] / "frontend" / "dist"
    index = dist / "index.html"
    if not index.is_file():
        app.logger.warning("SERVE_DIST=1 但 %s 不存在，请先在 frontend 目录执行 npm run build", index)
        return

    @app.get("/")
    def frontend_index():
        return send_from_directory(dist, "index.html")

    @app.get("/assets/<path:name>")
    def frontend_asset(name):
        return send_from_directory(dist / "assets", name)

    @app.get("/favicon.ico")
    def frontend_favicon():
        if (dist / "favicon.ico").is_file():
            return send_from_directory(dist, "favicon.ico")
        return ("", 204)

    app.logger.info("SERVE_DIST=1：已托管 %s", dist)


app = create_app()


if __name__ == "__main__":
    # 课堂演示要让同学用手机访问：HOST=0.0.0.0 对外监听（默认仍只本机）。
    # threaded 必须开：不开的话 Werkzeug 单线程，一个请求处理完才接下一个，
    # 全班同时刷新会在 socket 层排长队，跟数据库无关也会「卡住」。
    app.run(host=os.environ.get("HOST", "127.0.0.1"),
            port=int(os.environ.get("PORT", "5000")),
            debug=False, threaded=True)
