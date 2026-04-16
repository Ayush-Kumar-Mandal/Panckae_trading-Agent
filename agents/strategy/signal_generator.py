"""
Signal Generator Agent: receives market opportunities and generates trade signals.
Acts as the bridge between Market Intelligence and Risk Agent.
"""

from utils.logger import get_logger
from utils.models import MarketState, TradeProposal, PortfolioState
from utils.constants import Events
from agents.strategy.arbitrage_strategy import ArbitrageStrategy
from config.settings import StrategyConfig

logger = get_logger(__name__)


class SignalGenerator:
    """
    Subscribes to market opportunities, generates trade proposals,
    and publishes them as trade signals for the Risk Agent.
    """

    def __init__(
        self,
        strategy_config: StrategyConfig,
        event_bus=None,
        portfolio_agent=None,
    ):
        self.config = strategy_config
        self.event_bus = event_bus
        self.portfolio_agent = portfolio_agent
        self.strategy = ArbitrageStrategy(strategy_config)
        self.total_signals: int = 0

    async def on_market_opportunity(self, data: dict) -> None:
        """
        Event handler: receives market state from the Market Agent.
        Generates and publishes trade proposals.
        """
        market_state: MarketState = data["market_state"]

        # Generate proposals
        proposals = self.strategy.generate_proposals(market_state)

        if not proposals:
            logger.debug("No trade signals generated this cycle")
            return

        # Get current portfolio state
        portfolio = (
            self.portfolio_agent.get_state()
            if self.portfolio_agent
            else PortfolioState(capital_usd=1000.0, peak_capital_usd=1000.0)
        )

        # Publish each proposal as a trade signal
        for proposal in proposals:
            self.total_signals += 1
            logger.info(
                f"📡 Signal #{self.total_signals}: {proposal.opportunity.token_pair} | "
                f"profit=${proposal.expected_profit_usd:.2f}"
            )

            if self.event_bus:
                await self.event_bus.publish(
                    Events.TRADE_SIGNAL,
                    {"proposal": proposal, "portfolio": portfolio},
                )

    @property
    def stats(self) -> dict:
        return {"total_signals": self.total_signals}
