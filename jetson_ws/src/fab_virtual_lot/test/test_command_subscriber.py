from uuid import uuid4

import pytest

from fab_virtual_lot.command_subscriber import RecipeStore
from event_gateway.command_auth import sign_command


def test_command_is_idempotent_and_lot_scoped(tmp_path):
    command = {
        "command_id": str(uuid4()), "proposal_id": str(uuid4()),
        "run_id": str(uuid4()), "scope": "simulation", "effective_from_lot": "LOT-2",
        "x_candidate": {"oxide_thickness": 0.98, "body_dose": 1.01,
                        "diffusion_time": 1.0, "epi_doping": 1.0},
        "x_current": {"oxide_thickness": 1.0, "body_dose": 1.0,
                       "diffusion_time": 1.0, "epi_doping": 1.0},
    }
    command = sign_command(command, "fixture-key")
    with RecipeStore(tmp_path / "recipe.sqlite", "fixture-key") as store:
        first = store.apply(command)
        assert store.apply(command) == first
        assert store.recipe_for("LOT-1") is None
        assert store.recipe_for("LOT-2")["body_dose"] == 1.01
        conflicting = command | {"effective_from_lot": "LOT-3"}
        with pytest.raises(ValueError):
            store.apply(conflicting)
