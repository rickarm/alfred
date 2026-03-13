from fastapi import FastAPI
from fastapi.responses import JSONResponse

from .routes import router

app = FastAPI(
    title="Things Agent API",
    description="REST gateway for Things 3 via MCP",
    version="0.1.0",
    docs_url="/docs",
    redoc_url=None,
)

app.include_router(router)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request, exc):  # noqa: ANN001
    return JSONResponse(
        status_code=500,
        content={
            "ok": False,
            "error": f"Internal server error: {exc}",
            "meta": {},
        },
    )
