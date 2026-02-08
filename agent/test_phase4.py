"""Phase 4 validation test - verify all components work together."""

import sys
from pathlib import Path

def test_imports():
    """Test all critical imports."""
    print("Testing imports...")
    
    try:
        from orchestrator.core.engine import OrchestrationEngine, WorkflowMode
        print("  [OK] OrchestrationEngine and WorkflowMode")
        
        from orchestrator.core.task_graph import TaskGraph
        print("  [OK] TaskGraph")
        
        from orchestrator.agents import (
            DataScientistAgent,
            ModelArchitectAgent,
            TrainingAgent,
        )
        print("  [OK] SLM agents")
        
        from orchestrator.llm.prompts import (
            build_manager_prompt,
            build_architect_prompt,
            build_developer_prompt,
            build_reviewer_prompt,
            build_tester_prompt,
            build_integrator_prompt,
            build_data_scientist_prompt,
            build_model_architect_prompt,
            build_training_prompt,
        )
        print("  [OK] All agent prompts")
        
        return True
    except ImportError as e:
        print(f"  [FAIL] Import failed: {e}")
        return False


def test_workflow_modes():
    """Test WorkflowMode enum."""
    print("\nTesting WorkflowMode enum...")
    
    try:
        from orchestrator.core.engine import WorkflowMode
        
        modes = [m.value for m in WorkflowMode]
        expected = ["kernel_build", "slm_training", "dual"]
        
        if modes == expected:
            print(f"  [OK] WorkflowMode has all 3 modes: {modes}")
            return True
        else:
            print(f"  [FAIL] Expected {expected}, got {modes}")
            return False
    except Exception as e:
        print(f"  [FAIL] Failed: {e}")
        return False


def test_slm_task_graph():
    """Test SLM task graph creation."""
    print("\nTesting SLM task graph...")
    
    try:
        from orchestrator.core.task_graph import TaskGraph
        
        graph = TaskGraph()
        tasks = graph.create_slm_training_tasks("Test SLM training")
        
        if len(tasks) == 7:
            print(f"  [OK] Created 7 SLM tasks")
            
            task_ids = [t["task_id"] for t in tasks]
            expected_ids = [
                "slm-data-prep",
                "slm-arch-design",
                "slm-training",
                "slm-evaluation",
                "slm-quantization",
                "slm-export",
                "slm-integration",
            ]
            
            if task_ids == expected_ids:
                print(f"  [OK] Task IDs correct")
                return True
            else:
                print(f"  [FAIL] Expected {expected_ids}, got {task_ids}")
                return False
        else:
            print(f"  [FAIL] Expected 7 tasks, got {len(tasks)}")
            return False
    except Exception as e:
        print(f"  [FAIL] Failed: {e}")
        return False


def test_config():
    """Test config file has workflow section."""
    print("\nTesting config file...")
    
    try:
        import tomli
        
        config_path = Path(__file__).parent / "config" / "auton.toml"
        
        if not config_path.exists():
            print(f"  [FAIL] Config file not found: {config_path}")
            return False
        
        with open(config_path, "rb") as f:
            config = tomli.load(f)
        
        if "workflow" in config:
            mode = config["workflow"].get("mode")
            print(f"  [OK] Workflow section exists, mode={mode}")
            
            if mode in ["kernel_build", "slm_training", "dual"]:
                print(f"  [OK] Valid workflow mode: {mode}")
                return True
            else:
                print(f"  [FAIL] Invalid workflow mode: {mode}")
                return False
        else:
            print("  [FAIL] No workflow section in config")
            return False
    except Exception as e:
        print(f"  [FAIL] Failed: {e}")
        return False


def test_agent_prompts():
    """Test all agent prompts are callable."""
    print("\nTesting agent prompts...")
    
    try:
        from orchestrator.llm.prompts import (
            build_manager_prompt,
            build_architect_prompt,
            build_developer_prompt,
            build_reviewer_prompt,
            build_tester_prompt,
            build_integrator_prompt,
            build_data_scientist_prompt,
            build_model_architect_prompt,
            build_training_prompt,
        )
        from orchestrator.arch_registry import get_arch_profile
        
        arch = get_arch_profile("x86_64")
        
        prompts = {
            "manager": build_manager_prompt(arch),
            "architect": build_architect_prompt(arch),
            "developer": build_developer_prompt(arch),
            "reviewer": build_reviewer_prompt(arch),
            "tester": build_tester_prompt(arch),
            "integrator": build_integrator_prompt(arch),
            "data_scientist": build_data_scientist_prompt(arch),
            "model_architect": build_model_architect_prompt(arch),
            "training": build_training_prompt(arch),
        }
        
        for name, prompt in prompts.items():
            if prompt and len(prompt) > 50:
                print(f"  [OK] {name} prompt: {len(prompt)} chars")
            else:
                print(f"  [FAIL] {name} prompt too short or empty")
                return False
        
        return True
    except Exception as e:
        print(f"  [FAIL] Failed: {e}")
        return False


def main():
    """Run all Phase 4 validation tests."""
    print("=" * 60)
    print("Phase 4 Validation Tests")
    print("=" * 60)
    
    results = []
    
    results.append(("Imports", test_imports()))
    results.append(("WorkflowMode", test_workflow_modes()))
    results.append(("SLM Task Graph", test_slm_task_graph()))
    results.append(("Config File", test_config()))
    results.append(("Agent Prompts", test_agent_prompts()))
    
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "[PASS]" if result else "[FAIL]"
        print(f"{status}: {name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\nPhase 4 is 100% COMPLETE!")
        return 0
    else:
        print(f"\nPhase 4 has {total - passed} failing test(s)")
        return 1


if __name__ == "__main__":
    sys.exit(main())
