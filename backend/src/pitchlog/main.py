"""FastAPI アプリケーションのエントリポイント。"""

from fastapi import FastAPI

app = FastAPI()


@app.get("/health")
async def health() -> dict[str, str]:
    """ヘルスチェックの応答を返す。"""
    return {"status": "ok"}
