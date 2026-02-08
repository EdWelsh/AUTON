"""Agent classes for AUTON orchestration."""

from orchestrator.agents.architect_agent import ArchitectAgent
from orchestrator.agents.base_agent import Agent, AgentRole, AgentState, TaskResult
from orchestrator.agents.data_scientist_agent import DataScientistAgent
from orchestrator.agents.developer_agent import DeveloperAgent
from orchestrator.agents.integrator_agent import IntegratorAgent
from orchestrator.agents.manager_agent import ManagerAgent
from orchestrator.agents.model_architect_agent import ModelArchitectAgent
from orchestrator.agents.reviewer_agent import ReviewerAgent
from orchestrator.agents.tester_agent import TesterAgent
from orchestrator.agents.training_agent import TrainingAgent

__all__ = [
    "Agent",
    "AgentRole",
    "AgentState",
    "TaskResult",
    "ManagerAgent",
    "ArchitectAgent",
    "DeveloperAgent",
    "ReviewerAgent",
    "TesterAgent",
    "IntegratorAgent",
    "DataScientistAgent",
    "ModelArchitectAgent",
    "TrainingAgent",
]
