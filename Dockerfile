FROM python:3.12-alpine

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

RUN mkdir -p /data

EXPOSE 5656

CMD ["gunicorn", "-b", "0.0.0.0:5656", "-w", "1", "--timeout", "30", "main:app"]
