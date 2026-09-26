#!/usr/bin/python3
"""ucrom Hardware Check: test every part of the phone by touch.

  ucrom-hwcheck            touch app (big Yes/No buttons for things only a
                           person can confirm, like hearing a sound)
  ucrom-hwcheck --auto     run the automatic checks, print JSON, write the report
"""

import json
import subprocess
import sys
import threading
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import checks  # noqa: E402

ICONS = {checks.PASS: "emblem-ok-symbolic", checks.FAIL: "dialog-error-symbolic",
         checks.ABSENT: "action-unavailable-symbolic", checks.ASK: "dialog-question-symbolic"}


def auto_main():
    results = checks.run_all()
    report = checks.save_report(results)
    print(json.dumps([asdict(r) for r in results], indent=2))
    print(f"report: {report}", file=sys.stderr)
    return 1 if any(r.status == checks.FAIL for r in results) else 0


def gui_main():
    import gi
    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Adw, GLib, Gtk

    class Win(Adw.ApplicationWindow):
        def __init__(self, app):
            super().__init__(application=app, title="Hardware Check")
            self.set_default_size(360, 720)
            self.answers = {}
            self.results = []
            view = Adw.ToolbarView()
            header = Adw.HeaderBar()
            self.run_btn = Gtk.Button(label="Run checks")
            self.run_btn.add_css_class("suggested-action")
            self.run_btn.connect("clicked", self.run)
            header.pack_start(self.run_btn)
            view.add_top_bar(header)
            self.page = Adw.PreferencesPage()
            self.group = Adw.PreferencesGroup(title="Tap “Run checks”",
                                              description="Every part of the phone is tested. "
                                                          "Some tests ask you to confirm what you see or hear.")
            self.page.add(self.group)
            view.set_content(self.page)
            self.set_content(view)

        def run(self, _b):
            self.run_btn.set_sensitive(False)
            self.group.set_title("Checking…")
            threading.Thread(target=self.worker, daemon=True).start()

        def worker(self):
            res = checks.run_all()
            GLib.idle_add(self.show, res)

        def show(self, results):
            self.results = results
            self.page.remove(self.group)
            self.group = Adw.PreferencesGroup(title="Results")
            for r in results:
                row = Adw.ActionRow(title=r.title, subtitle=r.detail or r.status)
                row.set_subtitle_lines(3)
                row.add_prefix(Gtk.Image(icon_name=ICONS[r.status]))
                if r.status == checks.ASK:
                    box = Gtk.Box(spacing=6, valign=Gtk.Align.CENTER)
                    if r.action:
                        t = Gtk.Button(label="Test")
                        t.connect("clicked", lambda _b, a=r.action: subprocess.Popen(["bash", "-c", a]))
                        box.append(t)
                    for label, val in (("Yes", True), ("No", False)):
                        b = Gtk.Button(label=label)
                        b.set_size_request(64, 48)
                        b.connect("clicked", self.answer, r, val, row)
                        box.append(b)
                    row.set_subtitle(f"{r.detail}\n{r.question}")
                    row.add_suffix(box)
                self.group.add(row)
            self.page.add(self.group)
            self.save()
            self.run_btn.set_sensitive(True)
            self.run_btn.set_label("Run again")
            return False

        def answer(self, _b, r, val, row):
            self.answers[r.id] = val
            row.set_subtitle(f"{r.detail}\nYou said: {'yes' if val else 'no'}")
            self.save()

        def save(self):
            path = checks.save_report(self.results, self.answers)
            self.group.set_description(f"Report saved: {path}")

    class App(Adw.Application):
        def __init__(self):
            super().__init__(application_id="io.ucrom.HardwareCheck")

        def do_activate(self):
            (self.props.active_window or Win(self)).present()

    return App().run(sys.argv[:1])


if __name__ == "__main__":
    sys.exit(auto_main() if "--auto" in sys.argv else gui_main())
