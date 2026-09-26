#!/usr/bin/python3
"""ucrom App Hub: one-tap install of AI agents and developer apps.

Big touch targets, no keyboard needed. Each app installs from its official
source via apps/installers/<app>.sh (as the phone user, into $HOME) and gets a
home-screen launcher.
"""

import os
import subprocess
import sys
import threading
from pathlib import Path

import gi
import yaml

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402

APP_ID = "io.ucrom.AppHub"
BASE = Path(os.environ.get("UCROM_APPS_DIR", "/usr/lib/ucrom/apps"))
CATALOG = BASE / "catalog.yaml"
INSTALLERS = BASE / "installers"
ENV_PATH = "/opt/node/bin:{h}/.npm-global/bin:{h}/.local/bin:/usr/local/bin:/usr/bin:/bin"


def load_catalog():
    with open(CATALOG) as f:
        return yaml.safe_load(f)["apps"]


def child_env():
    env = dict(os.environ)
    home = env.get("HOME", str(Path.home()))
    env["PATH"] = ENV_PATH.format(h=home)
    env["NPM_CONFIG_PREFIX"] = f"{home}/.npm-global"
    return env


def is_installed(app):
    r = subprocess.run(["bash", "-c", app["check"]], env=child_env(),
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    return r.returncode == 0


class AppRow(Adw.ActionRow):
    def __init__(self, window, app):
        super().__init__(title=app["name"], subtitle=app["summary"])
        self.window = window
        self.app = app
        self.set_subtitle_lines(2)
        self.add_prefix(Gtk.Image(icon_name=app.get("icon", "application-x-executable-symbolic"),
                                  pixel_size=32))
        self.spinner = Gtk.Spinner()
        self.button = Gtk.Button(valign=Gtk.Align.CENTER)
        self.button.set_size_request(96, 48)  # finger-sized target
        self.button.connect("clicked", self.on_clicked)
        self.add_suffix(self.spinner)
        self.add_suffix(self.button)
        self.refresh()

    def refresh(self):
        installed = is_installed(self.app)
        self.button.set_label("Open" if installed else "Install")
        self.button.remove_css_class("suggested-action")
        if not installed:
            self.button.add_css_class("suggested-action")
        self.button.set_sensitive(True)

    def on_clicked(self, _btn):
        if self.button.get_label() == "Open":
            self.launch()
        else:
            self.install()

    def launch(self):
        app = self.app
        env = child_env()
        if app["kind"] == "terminal":
            argv = [str(INSTALLERS / "run-in-terminal.sh"), app["command"]]
        else:
            argv = ["bash", "-lc", app["command"]]
        subprocess.Popen(argv, env=env, start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.window.toast(f"Opening {app['name']}")

    def install(self):
        self.button.set_sensitive(False)
        self.button.set_label("Installing")
        self.spinner.start()
        self.window.log_line(f"--- installing {self.app['name']} ({self.app['source']})")
        threading.Thread(target=self._install_worker, daemon=True).start()

    def _install_worker(self):
        proc = subprocess.Popen(["bash", str(INSTALLERS / self.app["installer"])],
                                env=child_env(), stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True)
        needs_download = None
        for line in proc.stdout:
            line = line.rstrip()
            if line.startswith("NEEDS_DOWNLOAD "):
                needs_download = line.split(" ", 1)[1]
            GLib.idle_add(self.window.log_line, line)
        rc = proc.wait()
        GLib.idle_add(self._install_done, rc, needs_download)

    def _install_done(self, rc, needs_download):
        self.spinner.stop()
        if needs_download:
            Gio.AppInfo.launch_default_for_uri(needs_download, None)
            self.window.toast("Download the ARM64 build, then tap Install again")
        elif rc == 0:
            self.window.toast(f"{self.app['name']} installed")
            self.window.log_line(f"INSTALLED {self.app['id']}")
        else:
            self.window.toast(f"{self.app['name']} failed to install (code {rc})")
            self.window.log_line(f"FAILED {self.app['id']} rc={rc}")
        self.refresh()
        return False


class HubWindow(Adw.ApplicationWindow):
    def __init__(self, application):
        super().__init__(application=application, title="App Hub")
        self.set_default_size(360, 720)
        self.toasts = Adw.ToastOverlay()
        view = Adw.ToolbarView()
        view.add_top_bar(Adw.HeaderBar())

        page = Adw.PreferencesPage()
        group = Adw.PreferencesGroup(
            title="AI agents and developer apps",
            description="Tap Install. Everything comes from the official source.")
        self.rows = [AppRow(self, a) for a in load_catalog()]
        for row in self.rows:
            group.add(row)
        page.add(group)

        log_group = Adw.PreferencesGroup(title="Activity")
        self.buffer = Gtk.TextBuffer()
        log_view = Gtk.TextView(buffer=self.buffer, editable=False, monospace=True,
                                wrap_mode=Gtk.WrapMode.CHAR, cursor_visible=False)
        log_view.set_size_request(-1, 160)
        log_group.add(log_view)
        page.add(log_group)

        view.set_content(page)
        self.toasts.set_child(view)
        self.set_content(self.toasts)

        # Log file so tests and the Hardware Check can read install results
        self.logfile = Path(GLib.get_user_state_dir()) / "ucrom" / "apphub.log"
        self.logfile.parent.mkdir(parents=True, exist_ok=True)

    def toast(self, text):
        self.toasts.add_toast(Adw.Toast(title=text, timeout=3))

    def log_line(self, line):
        self.buffer.insert(self.buffer.get_end_iter(), line + "\n")
        with open(self.logfile, "a") as f:
            f.write(line + "\n")
        return False


class HubApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)

    def do_activate(self):
        win = self.props.active_window or HubWindow(self)
        win.present()


def main():
    if "--list" in sys.argv:
        for a in load_catalog():
            print(f"{a['id']}\t{'installed' if is_installed(a) else 'available'}\t{a['source']}")
        return 0
    return HubApp().run(sys.argv[:1])


if __name__ == "__main__":
    sys.exit(main())
