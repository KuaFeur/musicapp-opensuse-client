#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
queue_view.py — Vue de la file d'attente : liste ordonnée, suppression,
lecture directe d'un élément.
"""

from __future__ import annotations

import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib  # noqa: E402

from widgets import TrackRow


class QueueView(Gtk.Box):
    def __init__(self, api, on_play):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.api = api
        self.on_play = on_play

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        header.set_margin_top(12)
        header.set_margin_start(16)
        header.set_margin_end(16)
        self.append(header)

        title = Gtk.Label(label="File d'attente", xalign=0, hexpand=True)
        title.add_css_class("title-1")
        header.append(title)

        refresh_btn = Gtk.Button(icon_name="view-refresh-symbolic")
        refresh_btn.add_css_class("flat")
        refresh_btn.connect("clicked", lambda *_: self.refresh())
        header.append(refresh_btn)

        self.scrolled = Gtk.ScrolledWindow(vexpand=True)
        self.append(self.scrolled)

        self.list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.list_box.set_margin_top(6)
        self.list_box.set_margin_bottom(16)
        self.list_box.set_margin_start(16)
        self.list_box.set_margin_end(16)
        self.scrolled.set_child(self.list_box)

        self._show_placeholder("File d'attente vide.")

    def _clear(self):
        child = self.list_box.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.list_box.remove(child)
            child = nxt

    def _show_placeholder(self, text):
        self._clear()
        status = Adw.StatusPage(title=text, icon_name="view-list-symbolic")
        self.list_box.append(status)

    def refresh(self):
        def worker():
            try:
                data = self.api.queue_get()
                GLib.idle_add(self._render, data.get("queue", []))
            except Exception as exc:
                GLib.idle_add(self._show_placeholder, f"Erreur : {exc}")

        threading.Thread(target=worker, daemon=True).start()

    def _render(self, queue: list):
        self._clear()
        if not queue:
            self._show_placeholder("File d'attente vide.")
            return

        for index, track in enumerate(queue):
            row = TrackRow(
                track,
                on_play=self.on_play,
                on_remove=lambda t, i=index: self._remove(i),
                show_remove=True,
            )
            self.list_box.append(row)
        return False

    def _remove(self, index: int):
        def worker():
            try:
                self.api.queue_delete(index)
                GLib.idle_add(self.refresh)
            except Exception:
                pass

        threading.Thread(target=worker, daemon=True).start()
