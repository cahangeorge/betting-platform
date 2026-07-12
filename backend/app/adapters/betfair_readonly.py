from dataclasses import dataclass

from app.config import Settings


@dataclass(frozen=True)
class BetfairReadOnlyHealth:
    status: str
    message: str


class BetfairReadOnlyAdapter:
    """A deliberately read-only boundary; it exposes no order-placement method."""

    def __init__(self, settings: Settings):
        self._settings = settings

    async def health(self) -> BetfairReadOnlyHealth:
        if not self._settings.trading_betfair_read_only_enabled:
            return BetfairReadOnlyHealth(
                status="not_configured",
                message="Betfair read-only market data is disabled and no credentials are loaded.",
            )
        return BetfairReadOnlyHealth(
            status="not_configured",
            message="Betfair read-only market data was enabled, but no credential provider is configured.",
        )
