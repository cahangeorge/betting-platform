import pytest
from pydantic import ValidationError

from app.config import Settings


def test_inline_backend_is_a_deprecated_inprocess_alias():
    with pytest.warns(DeprecationWarning, match="inline is deprecated"):
        settings = Settings(_env_file=None, task_queue_backend="inline")

    assert settings.task_queue_backend == "inprocess"


def test_invalid_task_backend_is_rejected_during_settings_validation():
    with pytest.raises(ValidationError, match="task_queue_backend"):
        Settings(_env_file=None, task_queue_backend="celery")
