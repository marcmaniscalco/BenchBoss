FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt flask gunicorn

COPY bench_boss/ bench_boss/
COPY server.py stream_poller.py gunicorn.conf.py ./

EXPOSE 8080

CMD ["gunicorn", "--config", "gunicorn.conf.py", "server:app"]