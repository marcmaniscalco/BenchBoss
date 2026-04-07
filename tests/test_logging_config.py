import logging

from bench_boss.logging_config import SingleLineFormatter, configure_logging


def _format(msg: str, exc_info=None) -> str:
    formatter = SingleLineFormatter("%(message)s")
    record = logging.LogRecord(
        name="test",
        level=logging.ERROR,
        pathname="",
        lineno=0,
        msg=msg,
        args=(),
        exc_info=exc_info,
    )
    return formatter.format(record)


def test_plain_message_unchanged():
    assert _format("hello world") == "hello world"


def test_newlines_in_message_collapsed():
    result = _format("line one\nline two\nline three")
    assert "\n" not in result
    assert "line one" in result
    assert "line two" in result


def test_exception_traceback_collapsed():
    try:
        raise ValueError("boom")
    except ValueError:
        import sys

        result = _format("something failed", exc_info=sys.exc_info())

    assert "\n" not in result
    assert "ValueError" in result
    assert "boom" in result


def test_configure_logging_sets_single_line_formatter():
    configure_logging(level=logging.DEBUG)
    root_logger = logging.getLogger()
    assert root_logger.handlers, "root logger should have at least one handler"
    handler = root_logger.handlers[0]
    assert isinstance(handler.formatter, SingleLineFormatter)