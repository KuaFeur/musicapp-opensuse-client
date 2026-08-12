#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
queue_view.py — Vue de la file d'attente : liste ordonnée, réordonnancement
(monter/descendre), suppression individuelle, vidage complet, lecture
directe d'un élément.
"""

from __future__ import annotations

import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib  # noqa: E402

from widgets import load_thumbnail_async


class QueueRow(Gtk.Box):
    """Ligne de file d'attente : comme TrackRow, mais avec des boutons
    monter/descendre en plus de la suppression."""

    def __init__(self, track: dict, index: int, total: int, on_play, on_remove, on_move_up, on_move_down):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.track = track
        self.set_margin_top(4)
        self.set_margin_bottom(4)
        self.set_margin_start(8)
        self.set_margin_end(8)

        move_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        move_box.set_valign(Gtk.Align.CENTER)
        self.append(move_box)

        up_btn = Gtk.Button(icon_name="go-up-symbolic")
        up_btn.add_css_class("flat")
        up_btn.set_sensitive(index > 0)
        up_btn.connect("clicked", lambda *_: on_move_up(index))
        move_box.append(up_btn)

        down_btn = Gtk.Button(icon_name="go-down-symbolic")
        down_btn.add_css_class("flat")
        down_btn.set_sensitive(index < total - 1)
        down_btn.connect("clicked", lambda *_: on_move_down(index))
        move_box.append(down_btn)

        avatar = Adw.Avatar(size=40, text=track.get("title", "?"), show_initials=True)
        load_thumbnail_async(avatar, track.get("thumbnail", ""))
        self.append(avatar)

        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        text_box.set_hexpand(True)
        text_box.set_valign(Gtk.Align.CENTER)
        self.append(text_box)

        title_label = Gtk.Label(label=track.get("title", "Inconnu"), xalign=0)
        title_label.set_ellipsize(3)
        title_label.add_css_class("heading")
        text_box.append(title_label)

        artist_label = Gtk.Label(label=track.get("artist", ""), xalign=0)
        artist_label.set_ellipsize(3)
        artist_label.add_css_class("dim-label")
        artist_label.add_css_class("caption")
        text_box.append(artist_label)

        play_btn = Gtk.Button(icon_name="media-playback-start-symbolic")
        play_btn.add_css_class("flat")
        play_btn.set_valign(Gtk.Align.CENTER)
        play_btn.set_tooltip_text("Lire")
        play_btn.connect("clicked", lambda *_: on_play(track))
        self.append(play_btn)

        rm_btn = Gtk.Button(icon_name="user-trash-symbolic")
        rm_btn.add_css_class("flat")
        rm_btn.set_valign(Gtk.Align.CENTER)
        rm_btn.set_tooltip_text("Retirer")
        rm_btn.connect("clicked", lambda *_: on_remove(index))
        self.append(rm_btn)

        click = Gtk.GestureClick()
        click.connect("released", lambda *_: on_play(track))
        text_box.add_controller(click)


class QueueView(Gtk.Box):
    def __init__(self, api, on_play):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.api = api
        self.on_play = on_play
        self._busy = False

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        header.set_margin_top(12)
        header.set_margin_start(16)
        header.set_margin_end(16)
        self.append(header)

        title = Gtk.Label(label="File d'attente", xalign=0, hexpand=True)
        title.add_css_class("title-1")
        header.append(title)

        self.count_label = Gtk.Label(label="")
        self.count_label.add_css_class("dim-label")
        header.append(self.count_label)

        self.clear_btn = Gtk.Button(icon_name="edit-clear-all-symbolic")
        self.clear_btn.add_css_class("flat")
        self.clear_btn.set_tooltip_text("Vider la file d'attente")
        self.clear_btn.connect("clicked", self._on_clear_clicked)
        header.append(self.clear_btn)

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
        self.count_label.set_text("")
        self.clear_btn.set_sensitive(False)

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

        self.count_label.set_text(f"{len(queue)} morceau(x)")
        self.clear_btn.set_sensitive(True)

        total = len(queue)
        for index, track in enumerate(queue):
            row = QueueRow(
                track,
                index=index,
                total=total,
                on_play=self.on_play,
                on_remove=self._remove,
                on_move_up=lambda i: self._move(i, i - 1),
                on_move_down=lambda i: self._move(i, i + 1),
            )
            self.list_box.append(row)
        return False

    def _remove(self, index: int):
        if self._busy:
            return
        self._busy = True

        def worker():
            try:
                self.api.queue_delete(index)
            finally:
                GLib.idle_add(self._on_op_done)

        threading.Thread(target=worker, daemon=True).start()

    def _move(self, from_index: int, to_index: int):
        if self._busy:
            return
        self._busy = True

        def worker():
            try:
                self.api.queue_reorder(from_index, to_index)
            finally:
                GLib.idle_add(self._on_op_done)

        threading.Thread(target=worker, daemon=True).start()

    def _on_clear_clicked(self, *_args):
        root = self.get_root()
        dialog = Adw.MessageDialog(
            transient_for=root,
            heading="Vider la file d'attente ?",
            body="Tous les morceaux en attente seront retirés.",
        )
        dialog.add_response("cancel", "Annuler")
        dialog.add_response("clear", "Vider")
        dialog.set_response_appearance("clear", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")

        def on_response(_dlg, response):
            if response == "clear":
                self._clear_queue()

        dialog.connect("response", on_response)
        dialog.present()

    def _clear_queue(self):
        if self._busy:
            return
        self._busy = True

        def worker():
            try:
                self.api.queue_clear()
            finally:
                GLib.idle_add(self._on_op_done)

        threading.Thread(target=worker, daemon=True).start()

    def _on_op_done(self):
        self._busy = False
        self.refresh()
        return False
