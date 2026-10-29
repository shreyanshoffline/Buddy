"""dmgbuild settings: the drag-to-Applications window. Icon positions match dmg_background.py.

Run through make_dmg.py (it passes the -D defines below), or directly:
  dmgbuild -s packaging/macos/dmg_settings.py -D app=dist/Buddy.app -D bg=packaging/macos/dmg_background.png Buddy Buddy.dmg
"""
import os

app = defines["app"]                      # noqa: F821  (dmgbuild injects `defines`)
background = defines["bg"]                # noqa: F821
icon = defines.get("icon") or None        # noqa: F821  volume icon (.icns)
appname = os.path.basename(app)

format = "UDZO"
filesystem = "HFS+"
files = [app]
symlinks = {"Applications": "/Applications"}
icon_locations = {appname: (165, 205), "Applications": (495, 205)}

window_rect = ((200, 120), (660, 400))
default_view = "icon-view"
icon_size = 112
text_size = 13
show_status_bar = False
show_tab_view = False
show_toolbar = False
show_pathbar = False
show_sidebar = False
arrange_by = None
