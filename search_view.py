#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
search_view.py — Vue de recherche : champ de recherche + résultats
(morceaux en liste, albums/artistes en grille de cartes).
"""

from __future__ import annotations

import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib  # noqa: E402

from widgets import TrackRow, ResultCard


class SearchView(Gtk.Box):
    def __init__(self, api, on_play, on_queue, on_add_to_playlist, on_open_album, on_open_artist):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.api = api
        self.on_play = on_play
        self.on_queue = on_queue
        self.on_add_to_playlist = on_add_to_playlist
        self.on_open_album = on_open_album
        self.on_open_artist = on_open_artist

        # Barre de recherche
        search_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        search_bar.set_margin_top(12)
        search_bar.set_margin_bottom(6)
        search_bar.set_margin_start(16)
        search_bar.set_margin_end(16)
        self.append(search_bar)

        self.search_entry = Gtk.SearchEntry(hexpand=True)
        self.search_entry.set_placeholder_text("Rechercher des morceaux, albums, artistes…")
        self.search_entry.connect("activate", self._on_search)
        search_bar.append(self.search_entry)

        # Onglets de type
        self.type_dropdown = Gtk.DropDown.new_from_strings(
            ["Tout", "Morceaux", "Albums", "Artistes"]
        )
        self.type_dropdown.connect("notify::selected", lambda *_: self._on_search())
        search_bar.append(self.type_dropdown)

        self.spinner = Gtk.Spinner()
        search_bar.append(self.spinner)

        self.scrolled = Gtk.ScrolledWindow(vexpand=True)
        self.append(self.scrolled)

        self.results_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.results_box.set_margin_top(6)
        self.results_box.set_margin_bottom(16)
        self.results_box.set_margin_start(16)
        self.results_box.set_margin_end(16)
        self.scrolled.set_child(self.results_box)

        self._show_placeholder("Recherche des morceaux, albums ou artistes.")

    def _show_placeholder(self, text):
        self._clear_results()
        status = Adw.StatusPage(title=text, icon_name="system-search-symbolic")
        status.set_vexpand(True)
        self.results_box.append(status)

    def _clear_results(self):
        child = self.results_box.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.results_box.remove(child)
            child = nxt

    def _search_type_key(self) -> str:
        idx = self.type_dropdown.get_selected()
        return ["all", "songs", "albums", "artists"][idx]

    def _on_search(self, *_args):
        query = self.search_entry.get_text().strip()
        if not query:
            return
        self.spinner.start()
        search_type = self._search_type_key()

        def worker():
            try:
                data = self.api.search(query, search_type)
                GLib.idle_add(self._render_results, data)
            except Exception as exc:
                GLib.idle_add(self._render_error, str(exc))

        threading.Thread(target=worker, daemon=True).start()

    def _render_error(self, message):
        self.spinner.stop()
        self._show_placeholder(f"Erreur : {message}")
        return False

    def _render_results(self, data: dict):
        self.spinner.stop()
        self._clear_results()
        results = data.get("results", [])

        # Le serveur renvoie toujours une liste plate d'items, chacun
        # marqué "kind": "song" | "album" | "artist" (y compris pour
        # type=all, où les types sont mélangés). On les répartit ici.
        if isinstance(results, dict):
            # Robustesse si jamais le serveur renvoyait un dict groupé.
            songs = results.get("songs") or []
            albums = results.get("albums") or []
            artists = results.get("artists") or []
        else:
            songs = [r for r in results if r.get("kind") == "song"]
            albums = [r for r in results if r.get("kind") == "album"]
            artists = [r for r in results if r.get("kind") == "artist"]

        if not (songs or albums or artists):
            self._show_placeholder("Aucun résultat.")
            return

        if songs:
            self.results_box.append(self._section_label("Morceaux"))
            list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            for track in songs:
                list_box.append(
                    TrackRow(
                        track,
                        on_play=self.on_play,
                        on_queue=self.on_queue,
                        on_add_to_playlist=self.on_add_to_playlist,
                    )
                )
            self.results_box.append(list_box)

        if albums:
            self.results_box.append(self._section_label("Albums"))
            self.results_box.append(self._grid(albums, "album", self.on_open_album))

        if artists:
            self.results_box.append(self._section_label("Artistes"))
            self.results_box.append(self._grid(artists, "artist", self.on_open_artist))

    def _section_label(self, text):
        label = Gtk.Label(label=text, xalign=0)
        label.add_css_class("title-3")
        label.set_margin_top(6)
        return label

    def _grid(self, items, kind, on_activate):
        flow = Gtk.FlowBox()
        flow.set_selection_mode(Gtk.SelectionMode.NONE)
        flow.set_max_children_per_line(8)
        flow.set_row_spacing(12)
        flow.set_column_spacing(12)
        flow.set_homogeneous(False)
        for item in items:
            flow.append(ResultCard(item, kind, on_activate))
        return flow