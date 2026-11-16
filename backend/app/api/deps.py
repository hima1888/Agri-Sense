from typing import Annotated

from fastapi import Depends, Query, Response
from sqlalchemy.orm import Session

from app.db.session import get_db

DbSession = Annotated[Session, Depends(get_db)]


def no_content() -> Response:
    return Response(status_code=204)


class PageParams:
    def __init__(
        self,
        limit: Annotated[int, Query(ge=1, le=200, description="Max items to return")] = 50,
        offset: Annotated[int, Query(ge=0, description="Items to skip")] = 0,
    ) -> None:
        self.limit = limit
        self.offset = offset


Paging = Annotated[PageParams, Depends()]
