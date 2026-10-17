"""Data Scientist agent for SLM dataset preparation."""

from orchestrator.agents.base_agent import Agent, AgentRole
from orchestrator.llm.tools import DATA_SCIENTIST_TOOLS
from orchestrator.llm.prompts import build_data_scientist_prompt


class DataScientistAgent(Agent):
    """Agent specialized in preparing datasets for SLM training."""

    def __init__(self, **kwargs):
        arch_profile = kwargs.get("arch_profile")
        if arch_profile is None:
            # Every other role defaults to x86_64; these crashed on a None profile.
            from orchestrator.arch_registry import get_arch_profile
            arch_profile = get_arch_profile("x86_64")
        system_prompt = build_data_scientist_prompt(arch_profile)
        super().__init__(
            role=AgentRole.DATA_SCIENTIST,
            system_prompt=system_prompt,
            tools=DATA_SCIENTIST_TOOLS,
            **kwargs,
        )
