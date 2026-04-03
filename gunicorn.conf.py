import os
import threading

bind = "0.0.0.0:8080"
workers = 1
threads = 4
timeout = 30


def post_fork(server, worker):
    if os.environ.get("DYNAMODB_ENDPOINT"):
        return  # DynamoDB Local doesn't support streams; skip in local dev

    from stream_poller import poll_stream

    thread = threading.Thread(target=poll_stream, daemon=True)
    thread.start()