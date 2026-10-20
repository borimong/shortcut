FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY business_mcp ./business_mcp
EXPOSE 9101
CMD ["python", "-m", "business_mcp.server"]
