from collections import deque
from datetime import datetime, timedelta, timezone
from threading import Event, Lock, Thread
import time

import mysql.connector
from colorama import Fore, Style


class ProfilerService:
    def __init__(self, settings):
        self.settings = settings
        self.state_lock = Lock()
        self.worker_lock = Lock()
        self.stop_event = Event()
        self.log_buffer = deque(maxlen=settings.max_log_entries)
        self.worker = None
        local_tz = timezone(timedelta(hours=settings.local_tz_offset_hours))
        latest_event_time = datetime.now(local_tz) - timedelta(
            seconds=settings.start_lookback_seconds
        )
        self.state = {
            "connected": False,
            "last_error": None,
            "last_poll": None,
            "latest_event_time": latest_event_time.isoformat(),
        }

    def start(self):
        with self.worker_lock:
            if self.worker and self.worker.is_alive():
                return
            self.worker = Thread(
                target=self._loop, daemon=True, name="mysql-profiler-worker"
            )
            self.worker.start()

    def snapshot(self, limit):
        bounded_limit = max(1, min(limit, self.settings.max_log_entries))
        with self.state_lock:
            entries = list(self.log_buffer)[-bounded_limit:]
            current_state = dict(self.state)
        return {"entries": entries, "state": current_state}

    def health(self):
        with self.state_lock:
            return bool(self.state["connected"])

    def _connect_to_database(self):
        db_config = {
            "user": self.settings.db_user,
            "password": self.settings.db_password,
            "host": self.settings.db_host,
            "port": self.settings.db_port,
            "database": self.settings.db_name,
            "connection_timeout": self.settings.db_connect_timeout,
        }

        attempt = 0
        delay = 1.0
        while True:
            attempt += 1
            try:
                return mysql.connector.connect(**db_config)
            except mysql.connector.Error as err:
                if attempt >= self.settings.db_connect_retries:
                    raise
                print(
                    f"{Style.BRIGHT}{Fore.YELLOW}[retry {attempt}/{self.settings.db_connect_retries}] MySQL connect failed: {err}{Style.RESET_ALL}"
                )
                time.sleep(delay)
                delay = min(delay * self.settings.db_connect_backoff, 30)

    def _fetch_general_log(self, latest_event_time):
        connection = self._connect_to_database()
        cursor = connection.cursor()

        try:
            local_tz = timezone(timedelta(hours=self.settings.local_tz_offset_hours))
            query = """
                WITH general_log_filtered AS (
                    SELECT
                        event_time,
                        user_host,
                        thread_id,
                        command_type,
                        CONVERT(argument USING utf8) as argument
                    FROM mysql.general_log
                    WHERE user_host LIKE %s
                        AND command_type = 'Query'
                        AND CONVERT(argument USING utf8) NOT LIKE '%utf8mb4%'
                        AND CONVERT(argument USING utf8) NOT LIKE '%transaction%'
                        AND CONVERT(argument USING utf8) NOT LIKE '%SAVEPOINT%'
                        AND CONVERT(argument USING utf8) NOT LIKE '%commit%'
                        AND CONVERT(argument USING utf8) NOT LIKE '%information_schema.routines%'
                    ORDER BY event_time DESC
                    LIMIT 1000
                )
                SELECT event_time, argument
                FROM general_log_filtered
                ORDER BY event_time ASC;
            """

            cursor.execute(query, (self.settings.user_host_filter,))
            rows = cursor.fetchall()
            last_seen = latest_event_time.astimezone(local_tz)
            events = []

            for row in rows:
                if isinstance(row, dict):
                    event_time = row.get("event_time")
                    argument_value = row.get("argument")
                else:
                    row_values = tuple(row)
                    if len(row_values) < 2:
                        continue
                    event_time = row_values[0]
                    argument_value = row_values[1]

                if isinstance(event_time, str):
                    event_time = datetime.strptime(event_time, "%Y-%m-%d %H:%M:%S.%f")

                if not isinstance(event_time, datetime):
                    continue

                event_time = event_time.replace(tzinfo=local_tz)
                argument = str(argument_value)

                if event_time <= latest_event_time.astimezone(local_tz):
                    continue

                payload = {
                    "event_time": event_time.isoformat(),
                    "argument": argument,
                }
                events.append(payload)
                print(
                    f"{Style.BRIGHT}{Fore.RED}{payload['event_time']}{Style.RESET_ALL}\n{argument}\n"
                )

                if event_time > last_seen:
                    last_seen = event_time

            return last_seen, events
        finally:
            cursor.close()
            connection.close()

    def _loop(self):
        local_tz = timezone(timedelta(hours=self.settings.local_tz_offset_hours))
        latest_event_time = datetime.now(local_tz) - timedelta(
            seconds=self.settings.start_lookback_seconds
        )
        print(
            f"{Style.BRIGHT}{Fore.CYAN}Starting mysql-profiler against {self.settings.db_host}:{self.settings.db_port}, DB={self.settings.db_name}, filter={self.settings.user_host_filter}{Style.RESET_ALL}"
        )

        while not self.stop_event.is_set():
            try:
                latest_event_time, events = self._fetch_general_log(latest_event_time)
                with self.state_lock:
                    self.state["connected"] = True
                    self.state["last_error"] = None
                    self.state["last_poll"] = datetime.now(local_tz).isoformat()
                    self.state["latest_event_time"] = latest_event_time.isoformat()
                    for event in events:
                        self.log_buffer.append(event)
            except mysql.connector.Error as err:
                with self.state_lock:
                    self.state["connected"] = False
                    self.state["last_error"] = str(err)
                    self.state["last_poll"] = datetime.now(local_tz).isoformat()
                print(f"MySQL Connection Error: {err}")

            self.stop_event.wait(self.settings.poll_interval_seconds)
