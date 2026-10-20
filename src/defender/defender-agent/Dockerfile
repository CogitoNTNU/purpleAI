FROM python:3.12-slim
WORKDIR /app/defender/defender-agent
COPY defender/defender-agent/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY purpleai_logging.py /app/
COPY defender/defender-agent/defender.py defender/defender-agent/event_logging.py ./
CMD ["python", "-u", "defender.py"]
