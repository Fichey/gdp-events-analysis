FROM python:3.11-slim
WORKDIR /tests
COPY tests/performance/requirements.txt /tests/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY tests/performance/locustfile.py /tests/performance/locustfile.py
CMD ["locust", "-f", "/tests/performance/locustfile.py", "--headless", "-u", "10", "-r", "2", "--run-time", "30s", "--only-summary"]
