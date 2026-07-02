import os
import secrets
from dataclasses import dataclass
from pathlib import Path

from werkzeug.security import check_password_hash


def load_dotenv_file():
    base_dir = Path(__file__).resolve().parent
    env_path = base_dir / ".env"
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


load_dotenv_file()


def env_int(name, default):
    return int(os.getenv(name, str(default)))


def env_float(name, default):
    return float(os.getenv(name, str(default)))


def env_bool(name, default=False):
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def _write_private_file(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{value}\n", encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _read_or_create_secret(path):
    if path.exists():
        return path.read_text(encoding="utf-8").strip()

    secret_key = secrets.token_hex(32)
    _write_private_file(path, secret_key)
    print(f"[auth] Secret key generada en {path}")
    return secret_key


def _resolve_auth_password(password_file):
    password_hash = os.getenv("WEB_AUTH_PASSWORD_HASH", "").strip()
    if password_hash:
        return "hash", password_hash

    password = os.getenv("WEB_AUTH_PASSWORD", "").strip()
    if password:
        return "plain", password

    if password_file.exists():
        stored_password = password_file.read_text(encoding="utf-8").strip()
        if stored_password:
            return "plain", stored_password

    generated_password = secrets.token_urlsafe(24)
    _write_private_file(password_file, generated_password)
    print(f"[auth] Password generada en {password_file}")
    return "plain", generated_password


@dataclass(frozen=True)
class Settings:
    local_tz_offset_hours: int
    db_host: str
    db_port: int
    db_user: str
    db_password: str
    db_name: str
    db_connect_timeout: int
    db_connect_retries: int
    db_connect_backoff: float
    web_host: str
    web_port: int
    max_log_entries: int
    start_lookback_seconds: int
    poll_interval_seconds: float
    profile_title: str
    user_host_filter: str
    secret_key: str
    session_days: int
    api_key: str
    auth_username: str
    auth_password_mode: str
    auth_password_value: str
    login_window_seconds: int
    login_max_attempts: int
    login_lockout_seconds: int
    trusted_proxy_hops: int
    force_secure_cookies: bool

    def verify_password(self, candidate):
        if self.auth_password_mode == "hash":
            return check_password_hash(self.auth_password_value, candidate)
        return secrets.compare_digest(self.auth_password_value, candidate)


def load_settings():
    base_dir = Path(__file__).resolve().parent
    data_dir = Path(os.getenv("DATA_DIR", str(base_dir / "data"))).resolve()
    secret_file = Path(
        os.getenv("APP_SECRET_FILE", str(data_dir / "session-secret"))
    ).resolve()
    password_file = Path(
        os.getenv("WEB_AUTH_PASSWORD_FILE", str(data_dir / "admin-password.txt"))
    ).resolve()
    auth_password_mode, auth_password_value = _resolve_auth_password(password_file)

    return Settings(
        local_tz_offset_hours=env_int("LOCAL_TZ_OFFSET_HOURS", -5),
        db_host=os.getenv("DB_HOST", "192.168.50.32"),
        db_port=env_int("DB_PORT", 33061),
        db_user=os.getenv("DB_USER", "root"),
        db_password=os.getenv("DB_PASSWORD", "sql2016."),
        db_name=os.getenv("DB_NAME", "exphadis"),
        db_connect_timeout=env_int("DB_CONNECT_TIMEOUT", 5),
        db_connect_retries=env_int("DB_CONNECT_RETRIES", 10),
        db_connect_backoff=env_float("DB_CONNECT_BACKOFF", 1.5),
        web_host=os.getenv("WEB_HOST", "0.0.0.0"),
        web_port=env_int("WEB_PORT", 38110),
        max_log_entries=env_int("MAX_LOG_ENTRIES", 500),
        start_lookback_seconds=env_int("START_LOOKBACK_SECONDS", 300),
        poll_interval_seconds=env_float("POLL_INTERVAL_SECONDS", 1),
        profile_title=os.getenv("PROFILE_TITLE", "MySQL Profiler"),
        user_host_filter=os.getenv("USER_HOST_FILTER", "%wgutierrez%"),
        secret_key=_read_or_create_secret(secret_file),
        session_days=env_int("SESSION_DAYS", 30),
        api_key=os.getenv("API_KEY", "").strip(),
        auth_username=os.getenv("WEB_AUTH_USERNAME", "admin"),
        auth_password_mode=auth_password_mode,
        auth_password_value=auth_password_value,
        login_window_seconds=env_int("LOGIN_WINDOW_SECONDS", 900),
        login_max_attempts=env_int("LOGIN_MAX_ATTEMPTS", 8),
        login_lockout_seconds=env_int("LOGIN_LOCKOUT_SECONDS", 900),
        trusted_proxy_hops=env_int("TRUSTED_PROXY_HOPS", 1),
        force_secure_cookies=env_bool("FORCE_SECURE_COOKIES", False),
    )
