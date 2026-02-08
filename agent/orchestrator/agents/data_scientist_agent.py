"""Data Scientist agent for SLM dataset preparation."""

from orchestrator.agents.base_agent import Agent, AgentRole
from orchestrator.llm.tools import DATA_SCIENTIST_TOOLS
from orchestrator.llm.prompts import build_data_scientist_prompt


class DataScientistAgent(Agent):
    """Agent specialized in preparing datasets for SLM training."""

    def __init__(self, **kwargs):
        arch_profile = kwargs.get("arch_profile")
        system_prompt = build_data_scientist_prompt(arch_profile)
        super().__init__(
            role=AgentRole.DATA_SCIENTIST,
            system_prompt=system_prompt,
            tools=DATA_SCIENTIST_TOOLS,
            **kwargs,
        )
