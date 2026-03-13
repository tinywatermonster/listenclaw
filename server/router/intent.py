"""
Intent router.
Currently a pass-through — routes every utterance to the configured agent.
Future: keyword matching, multi-agent routing, function dispatch.
"""

import logging

logger = logging.getLogger(__name__)


class IntentRouter:
    def __init__(self, config: dict):
        self._default_agent = config.get("agent", {}).get("provider", "openclaw")

    def route(self, text: str) -> str:
        """Return the agent provider name to handle this utterance."""
        # Placeholder: always use default agent
        logger.debug("Routing %r → %s", text, self._default_agent)
        return self._default_agent
