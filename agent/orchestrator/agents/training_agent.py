"""Training agent for SLM model training."""

from orchestrator.agents.base_agent import Agent, AgentRole
from orchestrator.llm.tools import TRAINING_TOOLS
from orchestrator.llm.prompts import build_training_prompt


class TrainingAgent(Agent):
    """Agent specialized in training SLM models."""

    def __init__(self, **kwargs):
        arch_profile = kwargs.get("arch_profile")
        system_prompt = build_training_prompt(arch_profile)
        super().__init__(
            role=AgentRole.TRAINING,
            system_prompt=system_prompt,
            tools=TRAINING_TOOLS,
            **kwargs,
        )
