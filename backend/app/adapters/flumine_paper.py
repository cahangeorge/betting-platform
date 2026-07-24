"""Offline-only adapter to Flumine's order contract.

This adapter deliberately uses only Flumine value objects. It never creates a
client, market, execution engine, or transaction, so it has no path capable of
sending an order to an exchange.
"""

import sys
from dataclasses import dataclass
from pathlib import Path

from app.config import Settings, get_settings


@dataclass(frozen=True)
class PaperLimitInstruction:
    side: str
    price: float
    size: float
    order_type: str
    persistence_type: str
    framework: str = "flumine"


class FluminePaperAdapter:
    """Build and validate an offline paper instruction with Flumine objects."""

    def __init__(self, settings: Settings | None = None):
        self._settings = settings or get_settings()

    def _limit_order_class(self):
        root = Path(self._settings.resolved_flumine_root).resolve()
        local_order_type = root / "flumine" / "order" / "ordertype.py"
        if self._settings.flumine_root and not local_order_type.is_file():
            raise RuntimeError(f"Local Flumine checkout is unavailable at {root}")
        if local_order_type.is_file():
            root_text = str(root)
            if root_text not in sys.path:
                sys.path.insert(0, root_text)

        try:
            from flumine.order.ordertype import LimitOrder
        except ImportError as exc:  # pragma: no cover - exact missing dependency varies by environment
            raise RuntimeError("Flumine and its runtime dependencies are not installed") from exc
        return LimitOrder

    def build_back_limit(self, *, price: float, size: float) -> PaperLimitInstruction:
        if price <= 1 or size <= 0:
            raise ValueError("A paper BACK LIMIT instruction requires price > 1 and size > 0")

        limit_order = self._limit_order_class()(price=price, size=size, persistence_type="LAPSE")
        instruction = limit_order.place_instruction()
        info = limit_order.info
        if info["order_type"] != "Limit" or instruction["price"] != price or instruction["size"] != size:
            raise RuntimeError("Flumine produced an unexpected LIMIT order contract")

        return PaperLimitInstruction(
            side="BACK",
            price=float(instruction["price"]),
            size=float(instruction["size"]),
            order_type=info["order_type"],
            persistence_type=str(instruction["persistenceType"]),
        )
