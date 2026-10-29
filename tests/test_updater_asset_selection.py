from core.updater import pick_asset


ASSETS = [
    {"name": "Buddy-Setup-0.9.8-x64.exe"},
    {"name": "Buddy-0.9.8-linux-x86_64.AppImage"},
    {"name": "Buddy-0.9.8-macos-intel.dmg"},
    {"name": "Buddy-0.9.8-macos-apple-silicon.dmg"},
    {"name": "Buddy-macos-arm64-0.9.8.zip"},
    {"name": "Buddy-macos-x86_64-0.9.8.zip"},
    {"name": "Buddy-macos-x86_64-0.9.8.zip.sha256"},
]


def test_macos_auto_update_selects_the_zip_for_each_cpu():
    assert pick_asset(ASSETS, "macos", machine="arm64") == ASSETS[4]
    assert pick_asset(ASSETS, "macos", machine="x86_64") == ASSETS[5]


def test_windows_and_linux_use_release_page_instead_of_macos_zip():
    assert pick_asset(ASSETS, "windows") is None
    assert pick_asset(ASSETS, "linux") is None


def test_missing_macos_zip_returns_no_asset():
    assert pick_asset(ASSETS[:4], "macos", machine="arm64") is None
    assert pick_asset([], "macos") is None
