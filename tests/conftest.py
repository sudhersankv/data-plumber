import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from demo.providers import target_schema  # noqa: E402


@pytest.fixture
def gpu_schema() -> dict:
    return target_schema()
