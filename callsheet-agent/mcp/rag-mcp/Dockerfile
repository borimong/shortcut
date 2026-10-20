FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY rag_mcp ./rag_mcp
# 문서는 compose에서 /data/docs로 마운트한다. 색인은 첫 실행 때 /index에 만든다.
ENV HOST=0.0.0.0 PORT=9102 PYTHONUNBUFFERED=1 RAG_DOCS_DIR=/data/docs RAG_INDEX_DIR=/index
EXPOSE 9102
CMD ["python", "-m", "rag_mcp.server"]
