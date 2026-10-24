import hashlib
import hmac
import json
from uuid import uuid4

import pytest

from fab_virtual_lot.command_subscriber import RecipeStore


def sign_fixture_command(command: dict, key: str) -> dict:
    canonical = json.dumps(command, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False).encode("utf-8")
    signature = hmac.new(key.encode("utf-8"), canonical, hashlib.sha256).hexdigest()
    return command | {"command_mac": signature}


def test_command_is_idempotent_and_lot_scoped(tmp_path):
    command = {
        "command_id": str(uuid4()), "proposal_id": str(uuid4()),
        "run_id": str(uuid4()), "scope": "simulation", "effective_from_lot": "LOT-2",
        "x_candidate": {"oxide_thickness": 0.98, "body_dose": 1.01,
                        "diffusion_time": 1.0, "epi_doping": 1.0},
        "x_current": {"oxide_thickness": 1.0, "body_dose": 1.0,
                       "diffusion_time": 1.0, "epi_doping": 1.0},
    }
    command = sign_fixture_command(command, "fixture-key")
    with RecipeStore(tmp_path / "recipe.sqlite", "fixture-key") as store:
        first = store.apply(command)
        assert store.apply(command) == first
        assert store.recipe_for("LOT-1") is None
        assert store.recipe_for("LOT-2")["body_dose"] == 1.01
        conflicting = command | {"effective_from_lot": "LOT-3"}
        with pytest.raises(ValueError):
            store.apply(conflicting)
