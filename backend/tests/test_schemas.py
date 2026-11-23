"""Validate the shared contract and the frontend mock snapshot against the Pydantic models."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.models.corridor import build_corridor
from app.models.schemas import Action, ActionKind, Position, StateSnapshot

MOCK_PATH = Path(__file__).resolve().parents[2] / "frontend" / "src" / "mocks" / "snapshot.json"


@pytest.fixture(scope="module")
def raw() -> dict:
    return json.loads(MOCK_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def snap(raw: dict) -> StateSnapshot:
    return StateSnapshot.model_validate(raw)


def test_mock_validates(snap: StateSnapshot) -> None:
    assert snap.tick == 135
    assert len(snap.trains) == 5


def test_json_round_trip(snap: StateSnapshot) -> None:
    again = StateSnapshot.model_validate_json(snap.model_dump_json())
    assert again == snap


def test_unknown_field_rejected(raw: dict) -> None:
    with pytest.raises(ValidationError):
        StateSnapshot.model_validate({**raw, "surprise": 1})


def test_mock_blocks_exist_in_corridor(snap: StateSnapshot) -> None:
    lengths = {b.id: b.length_km for b in build_corridor().blocks}
    for occ in snap.blocks:
        assert occ.block_id in lengths
    for train in snap.trains:
        pos = train.position
        if pos and pos.block_id:
            assert pos.block_id in lengths
            assert pos.offset_km <= lengths[pos.block_id]


def test_mock_references_are_consistent(snap: StateSnapshot) -> None:
    train_ids = {t.id for t in snap.trains}
    conflict_ids = {c.id for c in snap.conflicts}
    assert len(train_ids) == len(snap.trains)
    for conflict in snap.conflicts:
        assert set(conflict.train_ids) <= train_ids
    for occ in snap.blocks:
        assert occ.train_id is None or occ.train_id in train_ids
    for rec in snap.recommendations:
        assert set(rec.conflict_ids) <= conflict_ids
        assert rec.action.train_id in train_ids


def test_mock_priorities_match_train_types(snap: StateSnapshot) -> None:
    from app.models.train import get_train_type

    for train in snap.trains:
        assert train.priority == get_train_type(train.category).priority


def test_position_needs_exactly_one_location() -> None:
    with pytest.raises(ValidationError):
        Position()
    with pytest.raises(ValidationError):
        Position(block_id="A-B-1", direction="fwd", at_station="A")
    with pytest.raises(ValidationError):
        Position(block_id="A-B-1")  # direction missing


def test_action_fields_must_match_kind() -> None:
    with pytest.raises(ValidationError):
        Action(kind=ActionKind.HOLD, train_id="1", at_station="GNK", reason="x")
    with pytest.raises(ValidationError):
        Action(kind=ActionKind.PRECEDENCE, train_id="1", at_station="GNK", reason="x")
    ok = Action(kind=ActionKind.HOLD, train_id="1", at_station="GNK", hold_minutes=5, reason="x")
    assert ok.hold_minutes == 5
