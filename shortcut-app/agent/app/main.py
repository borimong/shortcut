"""Agent 서버입니다. 그래프를 체크포인트와 함께 준비하고 작업 큐 소비를 시작합니다."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.postgres.aio import AsyncPostgresStore

from app.config import Settings
from app.graph.builder import build_replan_graph
from app.graph.qa import build_qa_graph
from app.harness.model import ModelGateway
from app.worker import TaskRunner, consume

logging.basicConfig(level=logging.INFO, format="%(message)s")
STATUS = {"consumer": "starting"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings.from_env()
    async with (
        AsyncPostgresSaver.from_conn_string(settings.checkpoint_dsn) as saver,
        AsyncPostgresStore.from_conn_string(settings.checkpoint_dsn) as store,
        httpx.AsyncClient(
            base_url=settings.backend_url, headers={"X-Internal-Token": settings.internal_token}, timeout=10
        ) as http,
    ):
        await saver.setup()
        await store.setup()
        runner = TaskRunner(
            settings,
            build_replan_graph(settings.limits).compile(checkpointer=saver, store=store),
            build_qa_graph().compile(checkpointer=saver, store=store),
            ModelGateway.openai(settings.openai_model, settings.fallback_model),
            http,
        )
        stop = asyncio.Event()

        async def run_consumer() -> None:
            # backend가 큐를 아직 선언하지 않았거나 RabbitMQ가 늦게 뜨면 연결이 실패하므로 기다렸다 다시 붙는다.
            while not stop.is_set():
                try:
                    STATUS["consumer"] = "running"
                    await consume(settings, runner, http, stop)
                except Exception as error:
                    STATUS["consumer"] = f"reconnecting: {error!r}"
                    await asyncio.sleep(3)

        consumer = asyncio.create_task(run_consumer())
        yield
        stop.set()
        await asyncio.wait_for(consumer, timeout=10)


app = FastAPI(title="ShortCut Agent", lifespan=lifespan)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok" if STATUS["consumer"] == "running" else "degraded", **STATUS}
