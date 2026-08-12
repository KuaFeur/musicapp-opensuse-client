#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
connect_view.py — Écran de connexion : demande IP + port du serveur,
teste la connexion dans un thread, puis appelle on_connected(host, port).
"""

from __future__ import annotations

import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib  # noqa: E402


class ConnectView(Gtk.Box):
    def __init__(self, api_client, on_connected):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.api = api_client
        self.on_connected = on_connected
        self.set_valign(Gtk.Align.CENTER)
        self.set_halign(Gtk.Align.CENTER)

        clamp = Adw.Clamp(maximum_size=380)
        self.append(clamp)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        box.set_margin_top(24)
        box.set_margin_bottom(24)
        box.set_margin_start(24)
        box.set_margin_end(24)
        clamp.set_child(box)

        icon = Gtk.Image.new_from_icon_name("audio-headphones-symbolic")
        icon.set_pixel_size(64)
        icon.add_css_class("dim-label")
        box.append(icon)

        title = Gtk.Label(label="Connexion au serveur")
        title.add_css_class("title-1")
        box.append(title)

        subtitle = Gtk.Label(label="Entre l'adresse IP et le port du serveur musicapp.")
        subtitle.add_css_class("dim-label")
        subtitle.set_wrap(True)
        subtitle.set_justify(Gtk.Justification.CENTER)
        box.append(subtitle)

        group = Adw.PreferencesGroup()
        box.append(group)

        self.host_row = Adw.EntryRow(title="Adresse IP ou nom d'hôte")
        self.host_row.set_text("music.linkua.me")
        group.add(self.host_row)

        self.port_row = Adw.EntryRow(title="Port")
        self.port_row.set_text("80")
        group.add(self.port_row)

        self.status_label = Gtk.Label(label="")
        self.status_label.add_css_class("error")
        self.status_label.set_wrap(True)
        self.status_label.set_visible(False)
        box.append(self.status_label)

        self.connect_button = Gtk.Button(label="Se connecter")
        self.connect_button.add_css_class("suggested-action")
        self.connect_button.add_css_class("pill")
        self.connect_button.connect("clicked", self._on_connect_clicked)
        box.append(self.connect_button)

        self.spinner = Gtk.Spinner()
        box.append(self.spinner)

        # Entrée -> connexion
        self.port_row.connect("entry-activated", self._on_connect_clicked)
        self.host_row.connect("entry-activated", self._on_connect_clicked)

    def _set_busy(self, busy: bool):
        self.connect_button.set_sensitive(not busy)
        self.host_row.set_sensitive(not busy)
        self.port_row.set_sensitive(not busy)
        if busy:
            self.spinner.start()
        else:
            self.spinner.stop()

    def _show_error(self, message: str):
        self.status_label.set_text(message)
        self.status_label.set_visible(True)

    def _on_connect_clicked(self, *_args):
        host = self.host_row.get_text().strip()
        port = self.port_row.get_text().strip()

        if not host:
            self._show_error("L'adresse du serveur est requise.")
            return
        if not port.isdigit():
            self._show_error("Le port doit être un nombre.")
            return

        self.status_label.set_visible(False)
        self._set_busy(True)
        self.api.configure(host, port)

        def worker():
            try:
                self.api.test_connection()
                GLib.idle_add(self._on_success, host, port)
            except Exception as exc:
                GLib.idle_add(self._on_failure, str(exc))

        threading.Thread(target=worker, daemon=True).start()

    def _on_success(self, host, port):
        self._set_busy(False)
        self.on_connected(host, port)
        return False

    def _on_failure(self, error_message: str):
        self._set_busy(False)
        self._show_error(f"Connexion impossible : {error_message}")
        return False
