"""
Integration logging utility.
Logs all API calls to Metrika, Webmaster, and AI agent into DB.
"""
import time
import json
import traceback
from datetime import datetime
from app import db
from app.models import IntegrationLog


def log_integration(source, method, level="info", project_id=None,
                    request_url=None, request_params=None, 
                    status_code=None, response_snippet=None,
                    error_message=None, duration_ms=None):
    """Create an integration log entry."""
    params_str = json.dumps(request_params, ensure_ascii=False)[:2000] if request_params else None
    snippet = (response_snippet or "")[:1000]

    entry = IntegrationLog(
        project_id=project_id,
        source=source,
        level=level,
        method=method,
        request_url=request_url,
        request_params=params_str,
        status_code=status_code,
        response_snippet=snippet,
        error_message=error_message,
        duration_ms=duration_ms,
    )
    db.session.add(entry)
    db.session.commit()
    return entry


def logged_request(source, method, project_id=None):
    """
    Decorator-like context: wraps an API call with logging.
    Usage:
        with logged_request("metrika", "report_search_queries", project_id=1) as log:
            resp = requests.get(...)
            log.set_response(resp)
    """
    class LogContext:
        def __init__(self):
            self.start = None
            self.entry = None

        def __enter__(self):
            self.start = time.time()
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            duration = int((time.time() - self.start) * 1000)
            if exc_type:
                error_msg = f"{exc_type.__name__}: {str(exc_val)}"
                tb = traceback.format_exc()[-500:]
                log_integration(
                    source=source, method=method, level="error",
                    project_id=project_id, duration_ms=duration,
                    error_message=f"{error_msg}\n{tb}",
                )
            return False  # don't suppress exceptions

        def ok(self, request_url=None, request_params=None,
               status_code=None, response_snippet=None):
            """Log a successful call."""
            duration = int((time.time() - self.start) * 1000)
            log_integration(
                source=source, method=method, level="info",
                project_id=project_id, request_url=request_url,
                request_params=request_params, status_code=status_code,
                response_snippet=response_snippet, duration_ms=duration,
            )

        def fail(self, error_message, request_url=None, status_code=None):
            """Log a failed call."""
            duration = int((time.time() - self.start) * 1000)
            log_integration(
                source=source, method=method, level="error",
                project_id=project_id, request_url=request_url,
                status_code=status_code, error_message=error_message,
                duration_ms=duration,
            )

    return LogContext()
