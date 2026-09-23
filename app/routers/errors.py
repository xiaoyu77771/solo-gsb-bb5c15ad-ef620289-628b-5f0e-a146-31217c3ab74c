from fastapi import Request
from fastapi.responses import JSONResponse

from app.exceptions import EventConflictError
from app.schemas import ErrorOut


def register_exception_handlers(app) -> None:  # noqa: ANN001
    @app.exception_handler(EventConflictError)
    async def _conflict_handler(_request: Request, exc: EventConflictError) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content=ErrorOut(detail=str(exc)).model_dump(),
        )
