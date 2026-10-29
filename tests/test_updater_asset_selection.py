from core.updater import pick_asset


ASSETS = [
    {"name": "Buddy-Setup-0.9.8-x64.exe"},
    {"name": "Buddy-0.9.8-linux-x86_64.AppImage"},
    {"name": "Buddy-0.9.8-macos-universal.dmg"},
    {"name": "Buddy-0.9.8-macos-universal.zip"},
]


def test_macos_auto_update_selects_only_macos_zip():
    assert pick_asset(ASSETS, "macos") == ASSETS[-1]


def test_windows_and_linux_use_release_page_instead_of_macos_zip():
    assert pick_asset(ASSETS, "windows") is None
    assert pick_asset(ASSETS, "linux") is None


def test_missing_macos_zip_returns_no_asset():
    assert pick_asset(ASSETS[:-1], "macos") is None
    assert pick_asset([], "macos") is None
