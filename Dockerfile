FROM python:3.12-slim

WORKDIR /silo

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /data

EXPOSE 7123

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7123"]
