FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY business_mcp ./business_mcp
ENV HOST=0.0.0.0 PORT=9101 PYTHONUNBUFFERED=1
EXPOSE 9101
CMD ["python", "-m", "business_mcp.server"]
