from types import SimpleNamespace

import pytest
from fastapi import Response

from app.api.v1.data import list_scrape_jobs


class _ScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _Db:
    def __init__(self, rows):
        self._rows = rows

    async def execute(self, _statement):
        return _ScalarResult(self._rows)


@pytest.mark.asyncio
async def test_scrape_jobs_return_selected_page_and_total_headers():
    jobs = [SimpleNamespace(id=index, params={"_created_by_user_id": 7}) for index in range(1, 26)]
    response = Response()

    result = await list_scrape_jobs(
        response=response,
        page=2,
        per_page=10,
        db=_Db(jobs),
        user=SimpleNamespace(id=7, is_admin=False),
    )

    assert [job.id for job in result] == list(range(11, 21))
    assert response.headers["x-total-count"] == "25"
    assert response.headers["x-page"] == "2"
    assert response.headers["x-per-page"] == "10"


@pytest.mark.asyncio
async def test_scrape_jobs_total_excludes_jobs_owned_by_other_users():
    jobs = [
        SimpleNamespace(id=1, params={"_created_by_user_id": 7}),
        SimpleNamespace(id=2, params={"_created_by_user_id": 8}),
        SimpleNamespace(id=3, params={"_created_by_user_id": 7}),
    ]
    response = Response()

    result = await list_scrape_jobs(
        response=response,
        page=1,
        per_page=10,
        db=_Db(jobs),
        user=SimpleNamespace(id=7, is_admin=False),
    )

    assert [job.id for job in result] == [1, 3]
    assert response.headers["x-total-count"] == "2"
