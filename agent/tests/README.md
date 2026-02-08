# AUTON Test Suite

## Structure

```
tests/
├── unit/              # Fast, isolated unit tests
├── integration/       # Multi-component integration tests
├── fixtures/          # Mocks and test data
└── conftest.py        # Pytest configuration

SLM/tests/            # SLM pipeline tests
agent/tools/*/tests/  # Rust tool tests
```

## Running Tests

### Python Unit Tests
```bash
# All unit tests
pytest tests/unit/ -v

# Specific component
pytest tests/unit/agents/ -v

# With coverage
pytest tests/unit/ --cov=orchestrator --cov-report=html
```

### Integration Tests
```bash
pytest tests/integration/ -v
```

### Rust Tests
```bash
cd agent/tools
cargo test
```

### SLM Tests
```bash
pytest SLM/tests/ -v
```

### All Tests
```bash
pytest tests/ SLM/tests/ -v
cd agent/tools && cargo test
```

## Test Categories

- **Unit**: Fast (<1s), heavily mocked, no external dependencies
- **Integration**: Slower (<30s), minimal mocking, real git/filesystem
- **Acceptance**: Full system (kernel_spec/tests/), real QEMU

## Next Steps

1. Implement mock fixtures in `tests/fixtures/`
2. Write unit tests for core components
3. Add integration tests for workflows
4. Implement Rust tool tests
5. Add SLM pipeline tests
