from __future__ import annotations

import importlib
from unittest.mock import AsyncMock, call

import pytest


def _topic_mute_service_type():
    try:
        module = importlib.import_module("src.application.topics.mute")
    except ModuleNotFoundError:
        pytest.fail("TopicMuteService is not implemented")
    return module.TopicMuteService


async def test_mute_and_unmute_delegate_to_user_scoped_repository_update() -> None:
    repository = AsyncMock()
    repository.set_inbound_enabled.side_effect = [True, True]
    service = _topic_mute_service_type()(repository)

    muted = await service.mute(telegram_user_id=100, telegram_topic_id=50)
    unmuted = await service.unmute(telegram_user_id=100, telegram_topic_id=50)

    assert muted is True
    assert unmuted is True
    assert repository.set_inbound_enabled.await_args_list == [
        call(100, 50, False),
        call(100, 50, True),
    ]
