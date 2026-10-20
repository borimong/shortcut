-- 업무 데이터(app), 문서 임베딩(rag), Agent 체크포인트(agent)를 한 DB 안에서 스키마로 나눈다.
CREATE EXTENSION IF NOT EXISTS vector;
CREATE SCHEMA IF NOT EXISTS app;
CREATE SCHEMA IF NOT EXISTS rag;
CREATE SCHEMA IF NOT EXISTS agent;
