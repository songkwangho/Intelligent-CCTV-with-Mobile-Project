# backend/app.py
from fastapi import FastAPI
from backend.websocket import ws_router


def create_app() -> FastAPI:
    app = FastAPI()
    # 헬스체크(선택)
    @app.get("/ping")
    def ping():
        return {"msg": "pong"}
    
    # WebSocket 라우터 등록
    app.include_router(ws_router)

    return app


app = create_app()
