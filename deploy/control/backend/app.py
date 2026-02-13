# backend/app.py
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from backend.websocket import ws_router, prune_runtime_cameras

logger = logging.getLogger("app")
logger.setLevel(logging.INFO)

def create_app() -> FastAPI:   

    async def _prune_loop() -> None:
        """Periodically prune offline runtime cameras.

        Tuning guide:
        - ttl_sec: 카메라가 "온라인"으로 유지되기 위한 마지막 수신 이후 허용 시간
        - interval_sec: prune 체크 주기
        """
        ttl_sec = 5.0
        interval_sec = 1.0
        while True:
            try:
                # removed가 있으면 내부에서 camera_update broadcast까지 수행
                await prune_runtime_cameras(ttl_sec=ttl_sec)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning("prune loop error: %r", e)
            await asyncio.sleep(interval_sec)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.prune_task = asyncio.create_task(_prune_loop())
        logger.info("startup: prune loop started")
        try:
            yield
        finally:
            task = getattr(app.state, "prune_task", None)
            if task is not None:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            logger.info("shutdown: prune loop stopped")

    """Create and configure FastAPI app."""

    app = FastAPI(lifespan=lifespan)
    # 헬스체크(선택)
    @app.get("/ping")
    def ping():
        return {"msg": "pong"}
    
    # WebSocket 라우터 등록
    app.include_router(ws_router)
    return app


app = create_app()
