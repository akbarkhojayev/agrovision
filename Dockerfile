FROM python:3.12-slim

WORKDIR /app
COPY req.txt .
RUN pip install -r req.txt

COPY . .

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]