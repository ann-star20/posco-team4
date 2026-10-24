from uuid import uuid4

from fab_virtual_lot.aoi_request import make_request


def test_request_carries_one_run_and_unique_job():
    run_id = uuid4()
    first = make_request(run_id, "LOT-1")
    second = make_request(run_id, "LOT-1")
    assert first["run_id"] == second["run_id"] == str(run_id)
    assert first["job_id"] != second["job_id"]
    assert first["request_id"] != second["request_id"]
    assert first["task_type"] == "aoi" and first["attempt"] == 1
