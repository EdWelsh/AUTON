"""Model Architect agent for SLM architecture design."""

from orchestrator.agents.base_agent import Agent, AgentRole
from orchestrator.llm.tools import MODEL_ARCHITECT_TOOLS
from orchestrator.llm.prompts import build_model_architect_prompt


class ModelArchitectAgent(Agent):
    """Agent specialized in designing SLM architectures."""

    def __init__(self, **kwargs):
        arch_profile = kwargs.get("arch_profile")
        system_prompt = build_model_architect_prompt(arch_profile)
        super().__init__(
            role=AgentRole.MODEL_ARCHITECT,
            system_prompt=system_prompt,
            tools=MODEL_ARCHITECT_TOOLS,
            **kwargs,
        )
