#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
main.py — Point d'entrée de MusicApp (client GTK4/libadwaita).

Lancement :
    pip install -r requirements.txt
    python3 main.py
"""

import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, Gio

from main_window import MainWindow


class MusicApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id="me.linkua.musicapp", flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.window = None

    def do_activate(self):
        if not self.window:
            self.window = MainWindow(self)
        self.window.present()


def main():
    app = MusicApp()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
