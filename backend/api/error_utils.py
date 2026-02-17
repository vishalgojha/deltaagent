from fastapi import HTTPException

from backend.brokers.base import BrokerError


def broker_http_exception(exc: BrokerError, *, operation: str, broker: str) -> HTTPException:
    return HTTPException(
        status_code=400,
        detail={
            "type": "broker_error",
            "operation": operation,
            "broker": broker,
            "code": exc.code,
            "message": str(exc),
            "retryable": exc.retryable,
            "context": exc.context,
        },
    )

