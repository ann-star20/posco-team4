from uuid import uuid4

from event_gateway.command_auth import sign_command, verify_applied_receipt
from fab_virtual_lot.command_subscriber import make_applied_receipt, verify_command


def test_command_and_receipt_are_authenticated():
    key = "fixture-only-shared-key"
    command = {"command_id": str(uuid4()), "proposal_id": str(uuid4()),
               "run_id": str(uuid4()), "effective_from_lot": "LOT-2",
               "scope": "simulation", "x_candidate": {}, "x_current": {}}
    signed = sign_command(command, key)
    assert verify_command(signed, key)
    assert not verify_command(signed | {"effective_from_lot": "LOT-3"}, key)
    event_id = uuid4()
    receipt = make_applied_receipt(signed, event_id, key)
    assert verify_applied_receipt(receipt, event_id, key)
    assert not verify_applied_receipt(receipt | {"effective_from_lot": "LOT-3"},
                                      event_id, key)
