# Test runner for the project (D-050). Same Python and libraries on every machine.
FROM python:3.12-slim
WORKDIR /repo
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
CMD ["pytest", "-q", "--tb=short", "tests"]
