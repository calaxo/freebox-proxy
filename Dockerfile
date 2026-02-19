FROM python:3.12-alpine

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

RUN mkdir -p /data

ENV LISTEN_PORT=5656
EXPOSE ${LISTEN_PORT}

CMD ["sh", "-c", "gunicorn -b 0.0.0.0:${LISTEN_PORT} -w 1 --timeout 30 main:app"]
