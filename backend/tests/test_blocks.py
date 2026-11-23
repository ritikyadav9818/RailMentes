"""Tests for the block tracker (single vs double line safety)."""

import pytest

from app.models.network import Block, Direction, LineType
from app.simulation.blocks import BlockTracker

FWD, REV = Direction.FORWARD, Direction.REVERSE


def single(i: int) -> Block:
    return Block(f"A-B-{i}", "A", "B", 10, LineType.SINGLE, 100)


def double(i: int) -> Block:
    return Block(f"C-D-{i}", "C", "D", 10, LineType.DOUBLE, 100)


def test_one_train_per_block() -> None:
    t = BlockTracker()
    t.claim(double(1), FWD, "t1")
    assert not t.can_claim(double(1), FWD, "t2")
    with pytest.raises(RuntimeError):
        t.claim(double(1), FWD, "t2")


def test_double_line_has_one_slot_per_direction() -> None:
    t = BlockTracker()
    t.claim(double(1), FWD, "t1")
    assert t.can_claim(double(1), REV, "t2")


def test_single_line_blocked_in_both_directions() -> None:
    t = BlockTracker()
    t.claim(single(1), FWD, "t1")
    assert not t.can_claim(single(1), REV, "t2")
    assert not t.can_claim(single(1), FWD, "t2")


def test_single_segment_keeps_opposing_trains_out() -> None:
    t = BlockTracker()
    t.claim(single(1), FWD, "t1")
    assert not t.can_claim(single(3), REV, "t2")  # different block, same segment
    assert t.can_claim(single(2), FWD, "t2")  # following in the same direction is fine


def test_release_frees_block() -> None:
    t = BlockTracker()
    t.claim(single(1), FWD, "t1")
    t.release(single(1), FWD, "t1")
    assert t.can_claim(single(1), REV, "t2")
    with pytest.raises(RuntimeError):
        t.release(single(1), FWD, "t1")
