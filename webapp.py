from collections import deque
from datetime import timedelta
from functools import wraps
from threading import Lock
from time import time
from urllib.parse import urlparse
import secrets

from flask import (
    Flask,
    abort,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask.sessions import SecureCookieSessionInterface
from werkzeug.middleware.proxy_fix import ProxyFix

from config import load_settings
from profiler_core import ProfilerService


class ProxyAwareSessionInterface(SecureCookieSessionInterface):
    def __init__(self, force_secure=False):
        super().__init__()
        self.force_secure = force_secure

    def get_cookie_secure(self, _app):
        return self.force_secure or request.is_secure


class LoginRateLimiter:
    def __init__(self, window_seconds, max_attempts, lockout_seconds):
        self.window_seconds = window_seconds
        self.max_attempts = max_attempts
        self.lockout_seconds = lockout_seconds
        self.records = {}
        self.lock = Lock()

    def status(self, client_id):
        now = time()
        with self.lock:
            record = self.records.get(client_id)
            if not record:
                return False, 0

            attempts = record["attempts"]
            while attempts and now - attempts[0] > self.window_seconds:
                attempts.popleft()

            locked_until = record.get("locked_until", 0)
            if locked_until > now:
                return True, max(0, int(locked_until - now))

            if not attempts and locked_until <= now:
                self.records.pop(client_id, None)

            return False, 0

    def record_failure(self, client_id):
        now = time()
        with self.lock:
            record = self.records.setdefault(
                client_id,
                {"attempts": deque(), "locked_until": 0},
            )
            attempts = record["attempts"]
            while attempts and now - attempts[0] > self.window_seconds:
                attempts.popleft()
            attempts.append(now)
            if len(attempts) >= self.max_attempts:
                record["locked_until"] = now + self.lockout_seconds

    def reset(self, client_id):
        with self.lock:
            self.records.pop(client_id, None)


def create_app():
    settings = load_settings()
    service = ProfilerService(settings)
    limiter = LoginRateLimiter(
        settings.login_window_seconds,
        settings.login_max_attempts,
        settings.login_lockout_seconds,
    )

    app = Flask(__name__)
    app.wsgi_app = ProxyFix(
        app.wsgi_app,
        x_for=settings.trusted_proxy_hops,
        x_proto=settings.trusted_proxy_hops,
        x_host=settings.trusted_proxy_hops,
    )
    app.session_interface = ProxyAwareSessionInterface(settings.force_secure_cookies)
    app.config.update(
        SECRET_KEY=settings.secret_key,
        PERMANENT_SESSION_LIFETIME=timedelta(days=settings.session_days),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_REFRESH_EACH_REQUEST=True,
    )
    app.extensions["mysql_profiler_service"] = service
    service.start()

    def client_id():
        forwarded_ip = request.headers.get("CF-Connecting-IP", "").strip()
        if forwarded_ip:
            return forwarded_ip
        return (
            request.headers.get("X-Forwarded-For", request.remote_addr or "unknown")
            .split(",")[0]
            .strip()
        )

    def is_safe_next_url(target):
        if not target:
            return False
        parsed = urlparse(target)
        return not parsed.netloc and parsed.path.startswith("/")

    def issue_csrf_token():
        token = session.get("csrf_token")
        if token:
            return token
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
        return token

    def validate_csrf():
        sent_token = request.form.get("csrf_token", "")
        expected_token = session.get("csrf_token", "")
        if (
            not sent_token
            or not expected_token
            or not secrets.compare_digest(sent_token, expected_token)
        ):
            abort(400)

    def is_authenticated():
        return bool(session.get("authenticated"))

    def login_required(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if is_authenticated():
                return view(*args, **kwargs)
            if request.path.startswith("/api/"):
                return jsonify({"error": "authentication_required"}), 401
            next_url = request.full_path if request.query_string else request.path
            return redirect(url_for("login", next=next_url))

        return wrapped

    @app.after_request
    def apply_security_headers(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = (
            "geolocation=(), camera=(), microphone=()"
        )
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "base-uri 'self'; "
            "connect-src 'self'; "
            "form-action 'self'; "
            "frame-ancestors 'none'; "
            "img-src 'self' data:; "
            "script-src 'self'; "
            "style-src 'self';"
        )
        if request.is_secure:
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
        return response

    @app.get("/login")
    def login():
        if is_authenticated():
            return redirect(url_for("index"))
        locked, retry_after = limiter.status(client_id())
        return render_template(
            "login.html",
            title=settings.profile_title,
            username=settings.auth_username,
            csrf_token=issue_csrf_token(),
            error=None,
            locked=locked,
            retry_after=retry_after,
            session_days=settings.session_days,
        )

    @app.post("/login")
    def login_post():
        validate_csrf()
        locked, retry_after = limiter.status(client_id())
        if locked:
            return (
                render_template(
                    "login.html",
                    title=settings.profile_title,
                    username=settings.auth_username,
                    csrf_token=issue_csrf_token(),
                    error=f"Acceso temporalmente bloqueado. Intenta de nuevo en {retry_after}s.",
                    locked=True,
                    retry_after=retry_after,
                    session_days=settings.session_days,
                ),
                429,
            )

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if username != settings.auth_username or not settings.verify_password(password):
            limiter.record_failure(client_id())
            return (
                render_template(
                    "login.html",
                    title=settings.profile_title,
                    username=settings.auth_username,
                    csrf_token=issue_csrf_token(),
                    error="Credenciales inválidas.",
                    locked=False,
                    retry_after=0,
                    session_days=settings.session_days,
                ),
                401,
            )

        limiter.reset(client_id())
        session.clear()
        session["authenticated"] = True
        session["username"] = settings.auth_username
        session.permanent = True
        session["csrf_token"] = secrets.token_urlsafe(32)
        next_url = request.args.get("next", "")
        if not is_safe_next_url(next_url):
            next_url = url_for("index")
        return redirect(next_url)

    @app.post("/logout")
    @login_required
    def logout():
        validate_csrf()
        session.clear()
        return redirect(url_for("login"))

    @app.get("/")
    @login_required
    def index():
        return render_template(
            "index.html",
            title=settings.profile_title,
            db_host=settings.db_host,
            db_port=settings.db_port,
            db_name=settings.db_name,
            user_host_filter=settings.user_host_filter,
            csrf_token=issue_csrf_token(),
            refresh_ms=2000,
            max_log_entries=settings.max_log_entries,
            session_days=settings.session_days,
        )

    @app.get("/api/logs")
    @login_required
    def api_logs():
        limit = request.args.get("limit", default=settings.max_log_entries, type=int)
        return jsonify(service.snapshot(limit))

    @app.get("/healthz")
    def healthz():
        ok = service.health()
        return jsonify({"ok": ok}), 200 if ok else 503

    return app, settings
