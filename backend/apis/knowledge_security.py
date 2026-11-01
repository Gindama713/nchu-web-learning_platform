"""Consume SPEC-001 authentication without implementing identity or sessions."""

from importlib import import_module

from flask import current_app, request

from backend.models.knowledge import KnowledgeError


class SharedSessionSecurity:
    def __init__(self, require_user, check_csrf, api_error):
        self.require_user = require_user
        self.check_csrf = check_csrf
        self.api_error = api_error

    def current_user_id(self):
        try:
            return self.require_user()["id"]
        except self.api_error as error:
            raise KnowledgeError(error.status, error.code, error.message) from error

    def verify_write_request(self):
        expected = current_app.config.get("APP_ORIGIN")
        if not expected or request.headers.get("Origin") != expected:
            raise KnowledgeError(403, "CSRF_FAILED", "来源不受信任")
        try:
            self.check_csrf()
        except self.api_error as error:
            raise KnowledgeError(error.status, error.code, error.message) from error

    def verify_transaction(self, connection, user):
        # Shared require_user checks the live session/version even with g.user
        # cached. BEGIN IMMEDIATE prevents revocation from racing the write.
        if self.current_user_id() != user["id"]:
            raise KnowledgeError(401, "UNAUTHENTICATED", "登录状态已变化")


def security_for_request():
    security = current_app.extensions.get("course_security")
    if security is not None:
        if not callable(getattr(security, "verify_transaction", None)):
            raise KnowledgeError(503, "MAINTENANCE", "鉴权适配器缺少事务内会话复核")
        return security
    try:
        auth = import_module("backend.shared.auth")
        api = import_module("backend.shared.api")
    except ModuleNotFoundError as error:
        if error.name not in {"backend.shared.auth", "backend.shared.api"}:
            raise
        raise KnowledgeError(503, "MAINTENANCE", "等待 SPEC-001 会话鉴权接入") from error
    return SharedSessionSecurity(auth.require_user, auth.check_csrf, api.ApiError)
