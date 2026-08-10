import sys
import traceback as tb_module
from loguru import logger
from app.core.database import SessionLocal
from app.models.models import LogErro


def postgres_sink(message):
    try:
        record = message.record
        log_erro = LogErro(
            level=record["level"].name,
            message=record["message"],
            correlation_id=record["extra"].get("correlation_id"),
            endpoint=record["extra"].get("endpoint"),
            method=record["extra"].get("method"),
            status_code=record["extra"].get("status_code"),
            traceback=record["extra"].get("traceback_str"),
            module=record["extra"].get("module", record["module"]),
        )
        db = SessionLocal()
        try:
            db.add(log_erro)
            db.commit()
        except Exception as e:
            db.rollback()
            print(f"[postgres_sink] Falha ao gravar log no banco: {e}", file=sys.stderr)
        finally:
            db.close()
    except Exception as e:
        print(f"[postgres_sink] Erro inesperado: {e}", file=sys.stderr)


def setup_logging():
    logger.remove()

    logger.add(
        sys.stdout,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | {extra.get('correlation_id', '-')} | {message}",
        level="INFO",
    )

    logger.add(
        postgres_sink,
        level="WARNING",
    )
