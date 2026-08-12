#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
detail_view.py — Vue détail pour un album ou un artiste : pochette/avatar,
titre, liste des morceaux.
"""

from __future__ import annotations

import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib  # noqa: E402

from widgets import TrackRow, load_thumbnail_async


class DetailView(Gtk.Box):
    def __init__(self, api, on_play, on_queue, on_add_to_playlist, on_back):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.api = api
        self.on_play = on_play
        self.on_queue = on_queue
        self.on_add_to_playlist = on_add_to_playlist
        self.on_back = on_back

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        header.set_margin_top(12)
        header.set_margin_start(16)
        header.set_margin_end(16)
        self.append(header)

        back_btn = Gtk.Button(icon_name="go-previous-symbolic")
        back_btn.add_css_class("flat")
        back_btn.connect("clicked", lambda *_: self.on_back())
        header.append(back_btn)

        self.spinner = Gtk.Spinner()
        header.append(self.spinner)

        self.scrolled = Gtk.ScrolledWindow(vexpand=True)
        self.append(self.scrolled)

        self.content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.content_box.set_margin_top(6)
        self.content_box.set_margin_bottom(16)
        self.content_box.set_margin_start(16)
        self.content_box.set_margin_end(16)
        self.scrolled.set_child(self.content_box)

    def _clear(self):
        child = self.content_box.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.content_box.remove(child)
            child = nxt

    def load_album(self, browse_id: str):
        self._clear()
        self.spinner.start()

        def worker():
            try:
                data = self.api.get_album(browse_id)
                GLib.idle_add(self._render_album, data)
            except Exception as exc:
                GLib.idle_add(self._render_error, str(exc))

        threading.Thread(target=worker, daemon=True).start()

    def load_artist(self, browse_id: str):
        self._clear()
        self.spinner.start()

        def worker():
            try:
                data = self.api.get_artist(browse_id)
                GLib.idle_add(self._render_artist, data)
            except Exception as exc:
                GLib.idle_add(self._render_error, str(exc))

        threading.Thread(target=worker, daemon=True).start()

    def _render_error(self, message):
        self.spinner.stop()
        self._clear()
        status = Adw.StatusPage(title="Erreur", description=message, icon_name="dialog-error-symbolic")
        self.content_box.append(status)
        return False

    def _header_box(self, title, subtitle, thumbnail):
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        avatar = Adw.Avatar(size=120, text=title, show_initials=True)
        load_thumbnail_async(avatar, thumbnail or "")
        box.append(avatar)

        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        text_box.set_valign(Gtk.Align.CENTER)
        box.append(text_box)

        title_label = Gtk.Label(label=title, xalign=0)
        title_label.add_css_class("title-1")
        title_label.set_wrap(True)
        text_box.append(title_label)

        if subtitle:
            sub_label = Gtk.Label(label=subtitle, xalign=0)
            sub_label.add_css_class("dim-label")
            text_box.append(sub_label)

        return box

    def _track_list(self, tracks):
        list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        for track in tracks:
            list_box.append(
                TrackRow(
                    track,
                    on_play=self.on_play,
                    on_queue=self.on_queue,
                    on_add_to_playlist=self.on_add_to_playlist,
                )
            )
        return list_box

    def _render_album(self, data: dict):
        self.spinner.stop()
        self._clear()
        title = data.get("title") or data.get("name", "Album")
        artist = data.get("artist", "")
        thumbnail = data.get("thumbnail", "")
        self.content_box.append(self._header_box(title, artist, thumbnail))

        tracks = data.get("tracks", [])
        # Assurer que chaque morceau a une pochette pour l'affichage
        for t in tracks:
            t.setdefault("thumbnail", thumbnail)
            t.setdefault("artist", artist)
        self.content_box.append(self._track_list(tracks))

    def _render_artist(self, data: dict):
        self.spinner.stop()
        self._clear()
        name = data.get("name", "Artiste")
        thumbnail = data.get("thumbnail", "")
        self.content_box.append(self._header_box(name, "Artiste", thumbnail))

        songs = data.get("songs") or []
        if isinstance(songs, dict):
            songs = songs.get("results", [])
        if songs:
            label = Gtk.Label(label="Titres populaires", xalign=0)
            label.add_css_class("title-3")
            self.content_box.append(label)
            self.content_box.append(self._track_list(songs))

        albums = data.get("albums") or []
        if isinstance(albums, dict):
            albums = albums.get("results", [])
        if albums:
            label = Gtk.Label(label="Albums", xalign=0)
            label.add_css_class("title-3")
            label.set_margin_top(6)
            self.content_box.append(label)
            flow = Gtk.FlowBox()
            flow.set_selection_mode(Gtk.SelectionMode.NONE)
            flow.set_max_children_per_line(8)
            flow.set_row_spacing(12)
            flow.set_column_spacing(12)
            from widgets import ResultCard
            for album in albums:
                flow.append(ResultCard(album, "album", lambda a: self.load_album(a.get("browse_id") or a.get("browseId"))))
            self.content_box.append(flow)