"""Tests for the OS backend: profile registry, docker argv, and honest guarding."""

from __future__ import annotations

import shutil

from controlplane.backends.os import builder, plugin, profiles
from controlplane.backends.os.builder import OSManager
from controlplane.backends.os.profiles import OSStatus, all_profiles, profile_for_text
from controlplane.core import CapabilityStatus, Registry, Router


# --- profiles ---------------------------------------------------------------

def test_five_profiles_present():
    keys = {p.key for p in all_profiles()}
    assert keys == {"linux", "windows", "android", "macos", "ios"}


def test_only_linux_runs_real_apps_without_kvm_or_caveats():
    linux = profiles.profile_by_key("linux")
    assert linux.status is OSStatus.REAL
    assert linux.runs_real_apps and not linux.requires_kvm


def test_ios_is_external_and_not_runnable():
    ios = profiles.profile_by_key("ios")
    assert ios.status is OSStatus.EXTERNAL
    assert ios.runs_real_apps is False
    assert ios.image is None  # no container image


def test_kvm_profiles_carry_a_compose_file():
    for key in ("android", "macos"):
        p = profiles.profile_by_key(key)
        assert p.requires_kvm and p.compose_file


def test_profile_for_text_picks_most_specific():
    assert profile_for_text("boot the mac os please").key == "macos"
    assert profile_for_text("run an iphone app").key == "ios"
    assert profile_for_text("spin up ubuntu").key == "linux"
    assert profile_for_text("start the windows vm").key == "windows"
    assert profile_for_text("make me a sandwich") is None


# --- pure argv builders -----------------------------------------------------

def test_pull_and_tag_argv():
    linux = profiles.profile_by_key("linux")
    assert builder.pull_argv(linux) == ["docker", "pull", linux.image]
    assert builder.tag_argv(linux.image, linux.tag) == ["docker", "tag", linux.image, linux.tag]


def test_run_argv_maps_web_port_and_restart():
    linux = profiles.profile_by_key("linux")
    argv = builder.run_argv(linux)
    assert argv[:5] == ["docker", "run", "-d", "--name", "auton-linux"]
    assert "-p" in argv and "3000:3000" in argv
    assert argv[-1] == "auton/linux:latest"


def test_run_argv_wires_devices_caps_env_privileged():
    android = profiles.profile_by_key("android")
    argv = builder.run_argv(android)
    assert "--privileged" in argv
    assert "--device" in argv and "/dev/kvm" in argv
    assert "EMULATOR_DEVICE=Samsung Galaxy S10" in argv
    assert "6080:6080" in argv


def test_build_argv_uses_build_dir():
    win = profiles.profile_by_key("windows")
    argv = builder.build_argv(win)
    assert argv[:4] == ["docker", "build", "-t", "auton/windows:latest"]
    assert argv[-1].endswith("windows-wine")


# --- OSManager honest guarding (no mocks) -----------------------------------

def test_kvm_profile_refuses_without_kvm_and_points_at_compose():
    # On a host without /dev/kvm (this Mac), launching macOS must refuse cleanly
    # and hand back the compose path — never a cryptic docker failure.
    if builder.kvm_available():
        import pytest

        pytest.skip("host has /dev/kvm; the refusal path can't be exercised here")
    mgr = OSManager()
    res = mgr.launch(profiles.profile_by_key("macos"))
    assert res.ok is False
    assert "kvm" in res.message.lower()
    assert "compose" in res.message.lower()


def test_ios_provision_returns_guidance_not_an_image():
    mgr = OSManager()
    prov = mgr.provision(profiles.profile_by_key("ios"))
    assert prov.ok is True
    assert "corellium" in prov.message.lower() or "appetize" in prov.message.lower()
    launch = mgr.launch(profiles.profile_by_key("ios"))
    assert launch.ok is False


def test_running_returns_list_with_real_docker():
    if shutil.which("docker") is None:
        import pytest

        pytest.skip("docker not installed")
    # Real `docker ps` call — must return a list and never raise.
    assert isinstance(OSManager().running(), list)


# --- chat capability --------------------------------------------------------

def test_capability_registered_and_working():
    caps = plugin.get_capabilities()
    assert len(caps) == 1
    assert caps[0].name == "os" and caps[0].status is CapabilityStatus.WORKING


def test_router_routes_os_catalog():
    reg = Registry(plugin.get_capabilities())
    res = Router(reg).route("what os can you create")
    assert res.handled
    assert "Linux" in res.text and "iOS" in res.text


def test_router_routes_list_running():
    reg = Registry(plugin.get_capabilities())
    res = Router(reg).route("what oses are running")
    assert res.handled  # returns either "none running" or the list, never errors
