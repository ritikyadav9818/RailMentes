"""Block occupancy: which train holds which track resource.

Two safety rules live here:
    1. One train per resource (``Block.resource_key``): single lines are shared by
       both directions, double lines have one slot per direction.
    2. On a single-line SEGMENT (station to station) trains may follow each other in
       the same direction but never run in opposite directions at once. Rule 1 alone
       would let two opposing trains enter the same segment from both ends and then
       block each other forever (deadlock), so we keep them out of the segment.
"""

from dataclasses import dataclass

from app.models.network import Block, Direction, LineType


@dataclass(frozen=True)
class Claim:
    """A train's hold on one block."""

    train_id: str
    block: Block
    direction: Direction


class BlockTracker:
    """Keeps the table of claimed block resources."""

    def __init__(self) -> None:
        self._claims: dict[str, Claim] = {}

    def holder(self, block: Block, direction: Direction) -> str | None:
        """Train id holding this resource, or None."""
        claim = self._claims.get(block.resource_key(direction))
        return claim.train_id if claim else None

    def can_claim(self, block: Block, direction: Direction, train_id: str) -> bool:
        """Return True if ``train_id`` may enter the block now."""
        holder = self.holder(block, direction)
        if holder is not None and holder != train_id:
            return False
        return not self._opposing_in_segment(block, direction, train_id)

    def blocker(self, block: Block, direction: Direction, train_id: str) -> str | None:
        """Id of the train that keeps ``train_id`` out of the block (None if nobody does)."""
        holder = self.holder(block, direction)
        if holder is not None and holder != train_id:
            return holder
        opposing = self._opposing_claim(block, direction, train_id)
        return opposing.train_id if opposing else None

    def _opposing_in_segment(self, block: Block, direction: Direction, train_id: str) -> bool:
        return self._opposing_claim(block, direction, train_id) is not None

    def _opposing_claim(self, block: Block, direction: Direction, train_id: str) -> Claim | None:
        if block.line is not LineType.SINGLE:
            return None
        return next(
            (
                c
                for c in self._claims.values()
                if c.train_id != train_id
                and c.direction is not direction
                and (c.block.from_code, c.block.to_code) == (block.from_code, block.to_code)
            ),
            None,
        )

    def claim(self, block: Block, direction: Direction, train_id: str) -> None:
        """Take the block. Raises if it is not allowed (a safety violation)."""
        if not self.can_claim(block, direction, train_id):
            raise RuntimeError(f"{train_id} may not enter {block.id} ({direction.value})")
        self._claims[block.resource_key(direction)] = Claim(train_id, block, direction)

    def release(self, block: Block, direction: Direction, train_id: str) -> None:
        """Give the block back. Raises if ``train_id`` does not hold it."""
        if self.holder(block, direction) != train_id:
            raise RuntimeError(f"{train_id} does not hold {block.id}")
        del self._claims[block.resource_key(direction)]

    def claims(self) -> list[Claim]:
        """All current claims, ordered by block id (stable output)."""
        return sorted(self._claims.values(), key=lambda c: c.block.id)
