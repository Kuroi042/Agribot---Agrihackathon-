FROM python:3.11-slim

WORKDIR /app

# Ensure output is sent straight to terminal without buffering
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "bot.py"]
