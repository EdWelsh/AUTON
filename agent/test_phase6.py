"""Phase 6 validation test - verify all infrastructure is ready for integration."""

import sys
from pathlib import Path

def test_workflow_modes():
    """Test all 3 workflow modes are accessible."""
    print("Testing workflow modes...")
    
    try:
        from orchestrator.core.engine import WorkflowMode
        
        modes = {m.value for m in WorkflowMode}
        expected = {"kernel_build", "slm_training", "dual"}
        
        if modes == expected:
            print(f"  [OK] All workflow modes available: {modes}")
            return True
        else:
            print(f"  [FAIL] Missing modes: {expected - modes}")
            return False
    except Exception as e:
        print(f"  [FAIL] {e}")
        return False


def test_slm_pipeline_tasks():
    """Test SLM pipeline creates all required tasks."""
    print("\nTesting SLM pipeline tasks...")
    
    try:
        from orchestrator.core.task_graph import TaskGraph
        
        graph = TaskGraph()
        tasks = graph.create_slm_training_tasks("Test")
        
        required_tasks = [
            "slm-data-prep",
            "slm-arch-design",
            "slm-training",
            "slm-evaluation",
            "slm-quantization",
            "slm-export",
            "slm-integration"
        ]
        
        task_ids = [t["task_id"] for t in tasks]
        
        if task_ids == required_tasks:
            print(f"  [OK] All 7 SLM tasks present")
            return True
        else:
            print(f"  [FAIL] Task mismatch")
            return False
    except Exception as e:
        print(f"  [FAIL] {e}")
        return False


def test_slm_agents():
    """Test SLM agents can be instantiated."""
    print("\nTesting SLM agents...")
    
    try:
        from orchestrator.agents import (
            DataScientistAgent,
            ModelArchitectAgent,
            TrainingAgent
        )
        print("  [OK] All SLM agent classes importable")
        return True
    except Exception as e:
        print(f"  [FAIL] {e}")
        return False


def test_slm_tools():
    """Test SLM tools are defined."""
    print("\nTesting SLM tools...")
    
    try:
        from orchestrator.llm.tools import (
            DATA_SCIENTIST_TOOLS,
            MODEL_ARCHITECT_TOOLS,
            TRAINING_TOOLS
        )
        
        total_tools = len(DATA_SCIENTIST_TOOLS) + len(MODEL_ARCHITECT_TOOLS) + len(TRAINING_TOOLS)
        
        if total_tools >= 10:
            print(f"  [OK] {total_tools} SLM tools defined")
            return True
        else:
            print(f"  [FAIL] Only {total_tools} tools (expected 10+)")
            return False
    except Exception as e:
        print(f"  [FAIL] {e}")
        return False


def test_slm_scripts():
    """Test SLM scripts exist."""
    print("\nTesting SLM scripts...")
    
    try:
        slm_scripts = Path(__file__).parent.parent / "SLM" / "scripts"
        
        required = ["train.py", "evaluate.py", "quantize.py", "export_gguf.py", "export_onnx.py"]
        
        for script in required:
            if not (slm_scripts / script).exists():
                print(f"  [FAIL] Missing {script}")
                return False
        
        print(f"  [OK] All 5 SLM scripts present")
        return True
    except Exception as e:
        print(f"  [FAIL] {e}")
        return False


def test_slm_configs():
    """Test SLM model configs exist."""
    print("\nTesting SLM configs...")
    
    try:
        slm_configs = Path(__file__).parent.parent / "SLM" / "configs"
        
        required = ["tiny_10M.yaml", "small_50M.yaml"]
        
        for config in required:
            if not (slm_configs / config).exists():
                print(f"  [FAIL] Missing {config}")
                return False
        
        print(f"  [OK] Model configs present")
        return True
    except Exception as e:
        print(f"  [FAIL] {e}")
        return False


def test_kernel_workspaces():
    """Test kernel workspaces are ready."""
    print("\nTesting kernel workspaces...")
    
    try:
        kernels = Path(__file__).parent.parent / "kernels"
        
        for arch in ["x86_64", "aarch64", "riscv64"]:
            git_dir = kernels / arch / ".git"
            if not git_dir.exists():
                print(f"  [FAIL] {arch} workspace not initialized")
                return False
        
        print("  [OK] All 3 architecture workspaces ready")
        return True
    except Exception as e:
        print(f"  [FAIL] {e}")
        return False


def test_orchestration_engine():
    """Test orchestration engine can be instantiated."""
    print("\nTesting orchestration engine...")
    
    try:
        from orchestrator.core.engine import OrchestrationEngine
        import tomli
        from pathlib import Path
        
        config_path = Path(__file__).parent / "config" / "auton.toml"
        with open(config_path, "rb") as f:
            config = tomli.load(f)
        
        workspace_path = Path(__file__).parent.parent / "kernels" / "x86_64"
        kernel_spec_path = Path(__file__).parent / "kernel_spec"
        
        # Just test instantiation, don't run
        engine = OrchestrationEngine(
            workspace_path=workspace_path,
            kernel_spec_path=kernel_spec_path,
            config=config
        )
        
        print("  [OK] OrchestrationEngine instantiates successfully")
        return True
    except Exception as e:
        print(f"  [FAIL] {e}")
        return False


def test_cost_tracking():
    """Test cost tracking is configured."""
    print("\nTesting cost tracking...")
    
    try:
        import tomli
        from pathlib import Path
        
        config_path = Path(__file__).parent / "config" / "auton.toml"
        with open(config_path, "rb") as f:
            config = tomli.load(f)
        
        if "llm" in config and "cost" in config["llm"]:
            max_cost = config["llm"]["cost"].get("max_cost_usd", 0)
            print(f"  [OK] Cost tracking configured (max: ${max_cost})")
            return True
        else:
            print("  [FAIL] Cost tracking not configured")
            return False
    except Exception as e:
        print(f"  [FAIL] {e}")
        return False


def test_documentation():
    """Test documentation files exist."""
    print("\nTesting documentation...")
    
    try:
        base = Path(__file__).parent.parent
        
        docs = [
            "README.md",
            "PHASES.md",
            "LICENSE.md"
        ]
        
        for doc in docs:
            if not (base / doc).exists():
                print(f"  [FAIL] Missing {doc}")
                return False
        
        print("  [OK] Core documentation present")
        return True
    except Exception as e:
        print(f"  [FAIL] {e}")
        return False


def main():
    """Run all Phase 6 validation tests."""
    print("=" * 60)
    print("Phase 6 Validation Tests")
    print("Infrastructure Readiness Check")
    print("=" * 60)
    
    results = []
    
    results.append(("Workflow Modes", test_workflow_modes()))
    results.append(("SLM Pipeline Tasks", test_slm_pipeline_tasks()))
    results.append(("SLM Agents", test_slm_agents()))
    results.append(("SLM Tools", test_slm_tools()))
    results.append(("SLM Scripts", test_slm_scripts()))
    results.append(("SLM Configs", test_slm_configs()))
    results.append(("Kernel Workspaces", test_kernel_workspaces()))
    results.append(("Orchestration Engine", test_orchestration_engine()))
    results.append(("Cost Tracking", test_cost_tracking()))
    results.append(("Documentation", test_documentation()))
    
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
        print("\nPhase 6 Infrastructure: 100% READY!")
        print("\nAll components in place for:")
        print("  - SLM training pipeline")
        print("  - Kernel development workflow")
        print("  - DUAL mode orchestration")
        print("  - Multi-architecture support")
        print("\nNext: Run actual orchestration with 'auton run <goal>'")
        return 0
    else:
        print(f"\nPhase 6 has {total - passed} failing test(s)")
        return 1


if __name__ == "__main__":
    sys.exit(main())
