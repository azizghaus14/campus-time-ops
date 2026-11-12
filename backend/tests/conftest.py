import pytest

from app.data.loader import get_dataset, reset_dataset
from app.services import attendance, holidays
from app.services.store import JsonStore, set_store
from app.services.workspace import LocalWorkspace, set_workspace


@pytest.fixture(autouse=True)
def isolated_state(tmp_path):
    """Every test gets a fresh store + outbox; dataset reloaded if a test mutated it."""
    set_store(JsonStore(tmp_path / "state"))
    set_workspace(LocalWorkspace(tmp_path / "outbox"))
    holidays.invalidate()
    yield tmp_path
    set_store(None)
    set_workspace(None)
    holidays.invalidate()


@pytest.fixture
def fresh_dataset():
    reset_dataset()
    attendance.reload_students()
    ds = get_dataset()
    yield ds
    reset_dataset()


@pytest.fixture(scope="session")
def ds():
    return get_dataset()
