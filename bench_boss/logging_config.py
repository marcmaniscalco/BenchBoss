"""
Logging configuration shared across server and stream poller.

Provides a formatter that collapses newlines so multi-line tracebacks
are emitted as a single CloudWatch Logs event.
"""

import logging

_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


class SingleLineFormatter(logging.Formatter):
    """Replaces newlines with \\n so each log record is one CloudWatch event."""

    def format(self, record: logging.LogRecord) -> str:
        return super().format(record).replace("\n", "\\n")


def configure_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(SingleLineFormatter(_FORMAT))
    logging.basicConfig(level=level, handlers=[handler], force=True)