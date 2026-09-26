"""ucrom-fod: in-display (under-screen) fingerprint for OnePlus phones.

Works on top of droidian-fpd (system bus org.droidian.fingerprint), which
talks to the phone's Android fingerprint HAL:

  * While a scan is running (verify / identify / enroll) it lights the sensor
    area: shows a bright target at the sensor position (GTK layer-shell
    overlay) and turns on the panel's fingerprint dim layer
    (/sys/kernel/oplus_display/dimlayer_bl_en), exactly what OxygenOS does.
  * When the screen is locked it starts an Identify, and on a match unlocks
    the Phosh lock screen (org.gnome.ScreenSaver.SetActive(false)).

Sensor geometry per device comes from /usr/share/ucrom/devices/<codename>.conf
(DEVICE_FOD_X/Y/R in panel pixels).
"""

import argparse
import logging
import os
import sys

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

from . import write_state, write_text  # noqa: E402

FPD_NAME = "org.droidian.fingerprint"
FPD_PATH = "/org/droidian/fingerprint"
FPD_IFACE = "org.droidian.fingerprint"
SS_NAME = "org.gnome.ScreenSaver"
SS_PATH = "/org/gnome/ScreenSaver"
DIMLAYER = "/sys/kernel/oplus_display/dimlayer_bl_en"
SCANNING = {"FPSTATE_VERIFYING", "FPSTATE_IDENTIFYING", "FPSTATE_ENROLLING"}

log = logging.getLogger("ucrom-fod")


class Overlay:
    """Bright circle over the sensor; optional (needs a display)."""

    def __init__(self, x, y, r, scale):
        self.win = None
        try:
            gi.require_version("Gtk", "3.0")
            gi.require_version("GtkLayerShell", "0.1")
            from gi.repository import Gtk, GtkLayerShell
        except (ValueError, ImportError):
            log.info("no layer-shell overlay available; dim layer only")
            return
        if not Gtk.init_check()[0]:
            return
        size = int(2 * r / scale)
        win = Gtk.Window()
        GtkLayerShell.init_for_window(win)
        GtkLayerShell.set_layer(win, GtkLayerShell.Layer.OVERLAY)
        GtkLayerShell.set_anchor(win, GtkLayerShell.Edge.TOP, True)
        GtkLayerShell.set_anchor(win, GtkLayerShell.Edge.LEFT, True)
        GtkLayerShell.set_margin(win, GtkLayerShell.Edge.LEFT, int((x - r) / scale))
        GtkLayerShell.set_margin(win, GtkLayerShell.Edge.TOP, int((y - r) / scale))
        GtkLayerShell.set_keyboard_mode(win, GtkLayerShell.KeyboardMode.NONE)
        win.set_size_request(size, size)
        area = Gtk.DrawingArea()

        def draw(_w, cr):
            cr.set_source_rgb(0.8, 0.8, 0.67)  # LineageOS udfps colour #ccccac
            cr.arc(size / 2, size / 2, size / 2, 0, 6.2832)
            cr.fill()

        area.connect("draw", draw)
        win.add(area)
        self.win = win

    def show(self, on):
        if self.win:
            (self.win.show_all if on else self.win.hide)()


class Fod:
    def __init__(self, geometry, scale):
        self.system = Gio.bus_get_sync(Gio.BusType.SYSTEM)
        try:
            self.session = Gio.bus_get_sync(Gio.BusType.SESSION)
        except GLib.Error:
            self.session = None
        self.overlay = Overlay(*geometry, scale) if geometry else None
        self.lit = False
        self.system.signal_subscribe(FPD_NAME, FPD_IFACE, "StateChanged", FPD_PATH, None,
                                     Gio.DBusSignalFlags.NONE, self.on_state)
        self.system.signal_subscribe(FPD_NAME, FPD_IFACE, "Identified", FPD_PATH, None,
                                     Gio.DBusSignalFlags.NONE, self.on_identified)
        if self.session:
            self.session.signal_subscribe(SS_NAME, SS_NAME, "ActiveChanged", SS_PATH, None,
                                          Gio.DBusSignalFlags.NONE, self.on_lock_changed)
        write_state("fod", "ready")

    # scanning -> light the sensor
    def light(self, on):
        if on == self.lit:
            return
        self.lit = on
        write_text(DIMLAYER, "1" if on else "0")
        if self.overlay:
            self.overlay.show(on)
        write_state("fod-light", "on" if on else "off")
        log.info("sensor light %s", "on" if on else "off")

    def on_state(self, _c, _s, _p, _i, _sig, params):
        state = params.unpack()[0]
        self.light(state in SCANNING)

    # locked -> identify -> unlock
    def on_lock_changed(self, _c, _s, _p, _i, _sig, params):
        if params.unpack()[0]:
            self.identify()

    def identify(self):
        try:
            r = self.system.call_sync(FPD_NAME, FPD_PATH, FPD_IFACE, "Identify", None,
                                      GLib.VariantType("(i)"), Gio.DBusCallFlags.NONE, 5000, None)
            log.info("identify requested (reply %s)", r.unpack()[0])
        except GLib.Error as e:
            log.info("fingerprint service not available: %s", e.message)

    def on_identified(self, _c, _s, _p, _i, _sig, params):
        finger = params.unpack()[0]
        log.info("finger %s identified; unlocking", finger)
        write_state("fod-unlock", finger)
        if self.session:
            self.session.call_sync(SS_NAME, SS_PATH, SS_NAME, "SetActive",
                                   GLib.Variant("(b)", (False,)), None,
                                   Gio.DBusCallFlags.NONE, 5000, None)


def load_geometry():
    """(x, y, r) of the sensor in panel pixels from the device profile."""
    codename = ""
    try:
        codename = open("/etc/ucrom-device").read().strip()
    except OSError:
        pass
    conf = os.environ.get("UCROM_DEVICE_CONF", f"/usr/share/ucrom/devices/{codename}.conf")
    vals = {}
    try:
        for line in open(conf):
            k, _, v = line.strip().partition("=")
            vals[k] = v.strip('"')
    except OSError:
        return None, 1.0
    try:
        geo = (int(vals["DEVICE_FOD_X"]), int(vals["DEVICE_FOD_Y"]), int(vals["DEVICE_FOD_R"]))
    except (KeyError, ValueError):
        geo = None
    return geo, float(vals.get("DEVICE_SCALE", "1") or 1)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
    geo, scale = load_geometry()
    if geo is None:
        log.info("this device has no in-display fingerprint sensor")
    Fod(geo, scale)
    GLib.MainLoop().run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
