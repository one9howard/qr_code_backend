import logging
import json
import uuid
from flask import request, has_request_context, g
from datetime import datetime
import sys

# Define usage of Gunicorn logger if available
class JSONFormatter(logging.Formatter):
    """
    Formatter to output logs in JSON format.
    Includes request_id if available in Flask context.
    """
    def format(self, record):
        log_record = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "module": record.module,
            "lineno": record.lineno,
        }

        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)

        # Add Request ID if in request context
        if has_request_context():
            log_record["method"] = request.method
            log_record["path"] = request.path
            log_record["remote_ip"] = request.remote_addr
            if hasattr(g, "request_id"):
                log_record["request_id"] = g.request_id

        return json.dumps(log_record)

def setup_logger(app):
    """
    Configures the application logger to use JSON formatting
    and output to stdout (for container logging).
    """
    # Remove default handlers
    app.logger.handlers.clear()
    
    # Create stdout handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    
    app.logger.addHandler(handler)
    app.logger.setLevel(logging.INFO)
    
    # Also attach to werkzeug logger to capture request logs
    logging.getLogger('werkzeug').handlers = [handler]
    
    # Setup Gunicorn logger binding if running under Gunicorn
    gunicorn_logger = logging.getLogger('gunicorn.error')
    if gunicorn_logger.handlers:
        app.logger.handlers = gunicorn_logger.handlers
        app.logger.setLevel(gunicorn_logger.level)

    # Add Request ID Middleware
    @app.before_request
    def add_request_id():
        g.request_id = request.headers.get("X-Request-Id", str(uuid.uuid4()))

    app.logger.info("Logger setup complete. JSON formatted logs enabled.")
