import os
import sys
from pathlib import Path
import pytest

# Ensure projects/Agents is on sys.path for all tests in this folder
AGENTS_ROOT = str(Path(__file__).resolve().parent.parent)
if AGENTS_ROOT not in sys.path:
    sys.path.insert(0, AGENTS_ROOT)


@pytest.fixture
def anyio_backend():
    return "asyncio"
