"""End-to-end tests for MainController, using fake agents (no real I/O)."""

from __future__ import annotations

import pytest

from core.controller import MainController
from domain.exceptions import AgentNotRegisteredError
from domain.models import AgentType, SubTask, TaskStatus


async def test_research_request_succeeds(controller: MainController) -> None:
    outcome = await controller.handle_request("ابحث عن أحدث تطورات نماذج اللغة")

    assert outcome.status == TaskStatus.SUCCEEDED
    assert len(outcome.results) == 1
    assert outcome.results[0].agent_type == AgentType.RESEARCH
    assert outcome.results[0].success
    assert outcome.answer


async def test_coding_keywords_route_to_coding_agent(controller: MainController) -> None:
    outcome = await controller.handle_request("fix a bug in the login function")

    assert outcome.results[0].agent_type == AgentType.CODING


async def test_missing_agent_raises_not_registered_error(
    controller: MainController,
) -> None:
    # BROWSER has no fake agent registered in the `dispatcher` fixture.
    with pytest.raises(AgentNotRegisteredError):
        await controller._dispatcher.dispatch(
            SubTask(agent_type=AgentType.BROWSER, description="scrape a page")
        )
