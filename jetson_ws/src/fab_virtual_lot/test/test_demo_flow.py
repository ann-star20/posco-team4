from uuid import uuid4

from fab_virtual_lot.publisher import make_demo_proposal


def test_demo_proposal_is_valid_and_run_scoped():
    run_id = uuid4()
    event = make_demo_proposal(run_id)
    assert event["run_id"] == str(run_id)
    assert event["event_type"] == "correction.proposed"
    proposal = event["payload"]
    assert proposal["run_id"] == str(run_id)
    assert proposal["delta_x"]["epi_doping"] == 0
    assert set(proposal["targets"]) == {"vth", "gm", "id_on", "bv"}
