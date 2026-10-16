"""Shared platform boundary tests; no desktop action is actually launched."""

from tools.platform_support import capability_summary, platform_name


def test_platform_name_is_supported_or_explicitly_unknown():
    assert platform_name() in {"macos", "windows", "linux", "chromeos", "other"}


def test_capability_summary_is_honest():
    summary = capability_summary()
    assert summary["platform"] == platform_name()
    assert summary["browser"] is True
    assert summary["desktop_gui"] is True
    assert isinstance(summary["notes"], str) and summary["notes"]
