# AUTO-PARK — single image for all three services.
#
#   web     -> python manage.py runserver 0.0.0.0:8000
#   fee     -> python flask_services/fee_service/app.py
#   barrier -> python flask_services/barrier_service/app.py
#
# docker/docker-compose.yml picks the command per service.

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000 5000 5001

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
