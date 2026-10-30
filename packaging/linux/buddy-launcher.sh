#!/bin/sh
# Launcher for the installed app (.deb installs it as /usr/bin/buddy).
# ChromeOS's Linux container (Crostini) runs apps through XWayland, so ask Qt for X11 there.
APP_DIR="${BUDDY_HOME:-/opt/buddy}"
if [ -z "$QT_QPA_PLATFORM" ] && { [ -e /dev/.cros_milestone ] || [ -d /opt/google/cros-containers ]; }; then
    export QT_QPA_PLATFORM=xcb
fi
exec "$APP_DIR/Buddy" "$@"
