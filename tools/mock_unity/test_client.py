from uuid import uuid4

import pytest

from client import MockUnity


def test_cursor_only_advances_after_valid_event(tmp_path):
    run_id = uuid4()
    client = MockUnity(run_id, tmp_path / "cursor.txt")
    with pytest.raises(ValueError):
        client.handle({"run_id": str(uuid4()), "sequence": 7})
    assert client.cursor() == 0
    client.handle({"run_id": str(run_id), "sequence": 7, "event_type": "correction.verified"})
    assert MockUnity(run_id, tmp_path / "cursor.txt").cursor() == 7
    client.handle({"run_id": str(run_id), "sequence": 4})
    assert client.cursor() == 7
