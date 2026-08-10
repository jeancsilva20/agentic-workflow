import uuid
import time
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from loguru import logger
from app.core.configs import settings
from app.core.database import engine
from app.models.models import Base
from app.core.logging_config import setup_logging
from app.routers import cliente_router, apolice_router
from app.routers import log_router

#Base.metadata.create_all(bind=engine)

app = FastAPI(
    title=settings.PROJECT_NAME,
    version="1.0.0",
    description="API do Case Sensedia - Gestão de Clientes e Apólices"
)

setup_logging()


# --- REQUISITO: LOGS E CORRELATION ID  ---
@app.middleware("http")
async def add_correlation_id(request: Request, call_next):
    correlation_id = str(uuid.uuid4())

    logger.bind(correlation_id=correlation_id).info(
        f"Iniciando requisição: {request.method} {request.url}"
    )

    start_time = time.time()

    response = await call_next(request)

    response.headers["X-Correlation-ID"] = correlation_id

    logger.bind(correlation_id=correlation_id).info(
        f"Finalizado em {time.time() - start_time:.4f}s - Status: {response.status_code}"
    )

    return response


# --- EXCEPTION HANDLERS GLOBAIS ---
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    status_code = exc.status_code
    level = "ERROR" if status_code >= 500 else "WARNING"

    logger.bind(
        correlation_id=request.headers.get("X-Correlation-ID", "-"),
        endpoint=str(request.url),
        method=request.method,
        status_code=status_code,
        module=request.url.path,
    ).log(level, exc.detail)

    return JSONResponse(
        status_code=status_code,
        content={"detail": exc.detail},
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    import traceback as tb

    full_tb = tb.format_exception(type(exc), exc, exc.__traceback__)
    tb_lines = [line.rstrip() for line in full_tb if line.strip()]

    app_lines = [line for line in tb_lines if "File \"" in line and ("/app/" in line or "\\app\\" in line or "app/" in line)]
    first_line = tb_lines[0] if tb_lines else ""
    last_line = tb_lines[-1] if tb_lines else ""

    if app_lines:
        tb_str = first_line + "\n" + app_lines[-1] + "\n" + last_line
    else:
        file_lines = [line for line in tb_lines if "File \"" in line]
        if file_lines:
            tb_str = first_line + "\n" + file_lines[-1] + "\n" + last_line
        else:
            tb_str = first_line + "\n" + last_line

    max_tb_length = 500
    if len(tb_str) > max_tb_length:
        tb_str = tb_str[:max_tb_length] + "... [truncado]"

    logger.bind(
        correlation_id=request.headers.get("X-Correlation-ID", "-"),
        endpoint=str(request.url),
        method=request.method,
        status_code=500,
        module=request.url.path,
        traceback_str=tb_str,
    ).error(f"Erro interno: {exc}")

    return JSONResponse(
        status_code=500,
        content={"detail": "Erro interno do servidor"},
    )


app.include_router(cliente_router.router, prefix=settings.API_V1_STR)
app.include_router(apolice_router.router, prefix=settings.API_V1_STR)
app.include_router(log_router.router, prefix=settings.API_V1_STR)

@app.get("/")
def home():
    return {"msg": "O servidor está rodando e o banco foi conectado!"}
