FROM python:3.12-slim
WORKDIR /app
COPY defender-agent/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY /defender-agent/defender.py .
CMD ["python", "-u", "defender.py"]
