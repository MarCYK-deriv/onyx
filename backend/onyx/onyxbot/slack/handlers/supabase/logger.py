import json
import logging
import os
import sys
import uuid
import datetime
from typing import Dict, Any, Optional

# Global variables for bot identity
BOT_ID = None
BOT_NAME = None


def set_bot_identity(bot_id, bot_name):
    """Set bot identity information for logging"""
    global BOT_ID, BOT_NAME
    BOT_ID = bot_id
    BOT_NAME = bot_name


class JsonFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging"""

    def format(self, record):
        # Standard fields
        log_record = {
            "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "service": BOT_NAME,  # Human-readable bot name as service identifier
            "logger_name": record.name,
            "file": record.pathname,
            "line_number": record.lineno,
            "message": record.getMessage(),
            "bot_id": BOT_ID     # Machine-processable unique identifier
            # bot_name removed as it's redundant with service
        }

        # Add all extra fields from record
        for key, value in record.__dict__.items():
            if key not in ["args", "exc_info", "exc_text", "msg", "message",
                           "levelname", "levelno", "pathname", "filename",
                           "module", "lineno", "funcName", "created",
                           "msecs", "relativeCreated", "thread", "threadName",
                           "processName", "process", "name"]:
                log_record[key] = value

        # Handle exceptions
        if record.exc_info:
            log_record["error_type"] = record.exc_info[0].__name__
            log_record["error_message"] = str(record.exc_info[1])
            log_record["traceback"] = self.formatException(
                record.exc_info).split('\n')

        return json.dumps(log_record)


def get_logger():
    """Set up and configure the centralized logger"""
    # Create logs directory if it doesn't exist
    log_file = os.environ.get("LOG_FILE", "logs/bot.log")
    if log_file:
        os.makedirs(os.path.dirname(log_file), exist_ok=True)

    # Create logger
    logger = logging.getLogger("bot_logger")
    log_level = os.environ.get("LOG_LEVEL", "INFO")
    logger.setLevel(getattr(logging, log_level))
    logger.propagate = False

    # Clear existing handlers
    if logger.handlers:
        logger.handlers.clear()

    # Create JSON formatter
    formatter = JsonFormatter()

    # Add console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # Add file handler if log file is specified
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


# Create a single logger instance to be used throughout the application
logger = get_logger()

# Helper function to generate request IDs


def generate_request_id():
    """Generate a unique request ID"""
    return str(uuid.uuid4())
