"""Sample task definitions for testing."""


BOOT_TASK = {
    "task_id": "boot-001",
    "title": "Implement boot loader",
    "subsystem": "boot",
    "description": "Create Multiboot2 boot loader",
    "dependencies": [],
    "acceptance_criteria": ["Kernel boots", "Serial output works"],
}


MM_TASK = {
    "task_id": "mm-001",
    "title": "Implement PMM",
    "subsystem": "mm",
    "description": "Physical memory manager",
    "dependencies": ["boot-001"],
    "acceptance_criteria": ["PMM allocates pages", "PMM frees pages"],
}


SLM_DATA_TASK = {
    "task_id": "slm-data-prep",
    "title": "Prepare SLM training data",
    "subsystem": "slm",
    "description": "Process and tokenize training data",
    "dependencies": [],
    "acceptance_criteria": ["Dataset tokenized", "Validation split created"],
}


SLM_TRAIN_TASK = {
    "task_id": "slm-training",
    "title": "Train SLM model",
    "subsystem": "slm",
    "description": "Train small language model",
    "dependencies": ["slm-data-prep", "slm-arch-design"],
    "acceptance_criteria": ["Model converges", "Validation loss acceptable"],
}
