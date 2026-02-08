"""Tests for architecture registry."""

import pytest
from orchestrator.arch_registry import get_arch_profile, ARCH_PROFILES


def test_get_arch_profile_x86_64():
    """Test x86_64 profile retrieval."""
    profile = get_arch_profile("x86_64")
    assert profile.name == "x86_64"
    assert profile.cc == "x86_64-elf-gcc"


def test_get_arch_profile_aarch64():
    """Test aarch64 profile retrieval."""
    profile = get_arch_profile("aarch64")
    assert profile.name == "aarch64"


def test_get_arch_profile_riscv64():
    """Test riscv64 profile retrieval."""
    profile = get_arch_profile("riscv64")
    assert profile.name == "riscv64"


def test_get_arch_profile_invalid():
    """Test invalid architecture."""
    with pytest.raises(KeyError):
        get_arch_profile("invalid")


def test_all_profiles_have_required_fields():
    """Test all profiles have required fields."""
    for name, profile in ARCH_PROFILES.items():
        assert profile.name
        assert profile.cc
        assert profile.qemu
