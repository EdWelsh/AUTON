# AUTON Development Guidelines

## Code Quality Standards

### Documentation Patterns
- **Module-level docstrings**: Every Python module starts with a comprehensive docstring explaining purpose and usage
- **Function docstrings**: Use descriptive docstrings for all public functions, following Google/NumPy style
- **Inline comments**: Explain complex logic, especially in orchestration loops and agent interactions
- **Type hints**: Extensive use of type annotations for function parameters and return values

### Code Formatting Standards
- **Line length**: 100 characters maximum (configured in pyproject.toml)
- **Import organization**: Standard library, third-party, local imports with clear separation
- **String formatting**: Prefer f-strings for readability and performance
- **Logging**: Structured logging with appropriate levels (DEBUG, INFO, WARNING, ERROR)

### Naming Conventions
- **Classes**: PascalCase (e.g., `OrchestrationEngine`, `ArchProfile`, `TaskResult`)
- **Functions/Methods**: snake_case (e.g., `execute_task`, `get_arch_profile`, `_run_build`)
- **Constants**: UPPER_SNAKE_CASE (e.g., `ARCH_PROFILES`, `BOOT_TESTS_COMMON`)
- **Private methods**: Leading underscore (e.g., `_execute_tool`, `_format_task_prompt`)
- **Agent IDs**: Hyphenated format (e.g., `manager-01`, `dev-02`, `reviewer-01`)

### Error Handling
- **Exception handling**: Comprehensive try-catch blocks with specific exception types
- **Graceful degradation**: Return meaningful error messages rather than crashing
- **Logging errors**: Always log exceptions with context before re-raising or returning error states
- **Timeout handling**: Explicit timeout parameters for async operations

## Architectural Patterns

### Agent-Based Architecture
- **Base Agent Pattern**: All agents inherit from `Agent` base class with common interface
- **Role-based specialization**: Each agent role has specific tools and system prompts
- **Tool execution pattern**: Consistent `_execute_tool` method with match-case statements
- **State management**: Agents maintain state through `AgentState` enum

### Configuration Management
- **Dataclass patterns**: Use `@dataclass` for structured configuration (e.g., `ArchProfile`, `TaskResult`)
- **TOML configuration**: Central configuration in `auton.toml` with example files
- **Environment variable fallback**: API keys can be set via environment variables
- **Architecture profiles**: Complete architecture definitions in registry pattern

### Async/Await Patterns
- **Async methods**: All agent operations are async for parallel execution
- **Concurrent execution**: Use `asyncio.gather()` for parallel agent task execution
- **Timeout handling**: Consistent timeout parameters with `asyncio.wait_for()`
- **Exception propagation**: Proper exception handling in async contexts

### Git Integration Patterns
- **Branch-based collaboration**: Each agent works on feature branches
- **Workspace abstraction**: `GitWorkspace` class encapsulates all git operations
- **Commit patterns**: Structured commit messages with agent identification
- **Merge strategies**: Integrator agent handles all merging operations

## Internal API Usage

### LLM Client Integration
```python
# Standard LLM client usage pattern
result_messages = await self.client.send_with_tools(
    agent_id=self.agent_id,
    system=self.system_prompt,
    messages=messages,
    tools=self.tools,
    tool_executor=self._execute_tool,
    model_override=self.model_override,
)
```

### Tool Definition Pattern
```python
# Consistent tool definition structure
TOOL_NAME = {
    "type": "function",
    "function": {
        "name": "tool_name",
        "description": "Clear description of tool purpose",
        "parameters": {
            "type": "object",
            "properties": {
                "param_name": {
                    "type": "string",
                    "description": "Parameter description",
                },
            },
            "required": ["param_name"],
        },
    },
}
```

### Task Execution Pattern
```python
# Standard task execution flow
async def execute_task(self, task: dict[str, Any]) -> TaskResult:
    self.state = AgentState.THINKING
    try:
        self.state = AgentState.EXECUTING
        # Execute task logic
        return TaskResult(success=True, ...)
    except Exception as e:
        self.state = AgentState.ERROR
        return TaskResult(success=False, error=str(e))
```

### Architecture Profile Usage
```python
# Access architecture-specific configuration
arch_profile = get_arch_profile(arch_name)
toolchain_cmd = [arch_profile.cc] + arch_profile.cflags
qemu_cmd = [arch_profile.qemu, "-machine", arch_profile.qemu_machine]
```

## Testing and Validation Patterns

### Acceptance Test Structure
- **Dataclass definitions**: Use `@dataclass` for test definitions with clear fields
- **Regex patterns**: Expected serial output patterns for QEMU validation
- **Architecture-aware tests**: Separate test sets for common and architecture-specific tests
- **Dependency tracking**: Tests specify required subsystems via `requires_subsystems`

### Test Organization
```python
# Architecture-aware test accessor pattern
def get_boot_tests(arch: str) -> list[AcceptanceTest]:
    arch_tests = _ARCH_BOOT_TESTS.get(arch, [])
    return BOOT_TESTS_COMMON + arch_tests
```

### Build and Test Integration
- **Make-based builds**: Delegate to Makefile for actual compilation
- **QEMU integration**: Serial output capture for test validation
- **Timeout handling**: Configurable timeouts for build and test operations
- **Exit code checking**: Always check and report process exit codes

## Common Code Idioms

### Dictionary Access Patterns
```python
# Safe dictionary access with defaults
model_overrides = self.config.get("agents", {}).get("models", {})
timeout = tool_input.get("timeout", 60)
```

### List Comprehensions for Data Processing
```python
# Extract data from complex structures
artifacts = [args.get("path", "") for tc in tool_calls 
            if tc.get("function", {}).get("name") == "write_file"]
```

### Enum Usage for Type Safety
```python
# Consistent enum patterns for state management
class AgentRole(str, Enum):
    MANAGER = "manager"
    DEVELOPER = "developer"
    # ...
```

### Path Handling
```python
# Consistent Path object usage
path = self.kernel_spec_path / "subsystems" / f"{subsystem}.md"
if not path.exists():
    return f"Specification not found: {subsystem}"
```

### Logging Patterns
```python
# Structured logging with context
logger.info("[%s] Starting task: %s", self.agent_id, task.get("title", "untitled"))
logger.error("Agent %s failed: %s", slot.agent.agent_id, result)
```

## Architecture-Specific Patterns

### Multi-Architecture Support
- **Registry pattern**: Central `ARCH_PROFILES` dictionary for all architectures
- **Profile-based configuration**: Complete toolchain and QEMU settings per architecture
- **Conditional logic**: Architecture-aware test selection and build configuration
- **Spec file organization**: Separate specification files per architecture

### Tool Chain Abstraction
- **Unified interface**: Same build commands work across all architectures
- **Profile-driven compilation**: Compiler flags and tools selected from architecture profile
- **QEMU configuration**: Machine type and CPU settings from architecture profile

### Boot Protocol Handling
- **Protocol-specific logic**: Different boot sequences for Multiboot2, DTB, OpenSBI
- **Firmware abstraction**: ACPI vs Device Tree handling based on architecture
- **Register set awareness**: Architecture-specific register naming in prompts

## Performance Considerations

### Parallel Agent Execution
- **Concurrent task processing**: Multiple developer agents work in parallel
- **Non-blocking operations**: Async/await throughout the codebase
- **Resource pooling**: Agent scheduler manages available agent slots
- **Batch operations**: Group related operations to reduce overhead

### Memory Management
- **Lazy loading**: Load specifications and configs only when needed
- **Conversation cleanup**: Clear agent conversations after task completion
- **Resource cleanup**: Proper cleanup of subprocess resources and file handles

### Cost Optimization
- **Model selection**: Different LLM models per agent role for cost efficiency
- **Token management**: Structured prompts to minimize token usage
- **Cost tracking**: Built-in cost monitoring with budget limits
- **Caching**: Reuse architecture profiles and specifications across agents