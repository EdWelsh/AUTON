"""Training agent for SLM model training."""

from orchestrator.agents.base_agent import Agent, AgentRole
from orchestrator.llm.tools import TRAINING_TOOLS
from orchestrator.llm.prompts import build_training_prompt


class TrainingAgent(Agent):
    """Agent specialized in training SLM models."""

    def __init__(self, **kwargs):
        arch_profile = kwargs.get("arch_profile")
        if arch_profile is None:
            # Every other role defaults to x86_64; these crashed on a None profile.
            from orchestrator.arch_registry import get_arch_profile
            arch_profile = get_arch_profile("x86_64")
        system_prompt = build_training_prompt(arch_profile)
        super().__init__(
            role=AgentRole.TRAINING,
            system_prompt=system_prompt,
            tools=TRAINING_TOOLS,
            **kwargs,
        )
