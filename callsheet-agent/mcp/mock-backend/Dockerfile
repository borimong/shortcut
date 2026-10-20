FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY mock_backend ./mock_backend
EXPOSE 8080
CMD ["uvicorn", "mock_backend.app:app", "--host", "0.0.0.0", "--port", "8080"]
