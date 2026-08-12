#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
main_window.py — Fenêtre principale : sidebar de navigation, pile de vues,
barre de lecture persistante en bas.
"""

from __future__ import annotations

import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib  # noqa: E402

from api import MusicApiClient
from player import Player
from connect_view import ConnectView
from search_view import SearchView
from detail_view import DetailView
from queue_view import QueueView
from playlists_view import PlaylistsView
from account_view import AccountView
from player_bar import PlayerBar
from discord_rpc import DiscordRPC


NAV_ITEMS = [
    ("home", "Accueil", "go-home-symbolic"),
    ("search", "Rechercher", "system-search-symbolic"),
    ("queue", "File d'attente", "view-list-symbolic"),
    ("playlists", "Playlists", "media-playlist-consecutive-symbolic"),
    ("account", "Compte", "avatar-default-symbolic"),
]


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="MusicApp")
        self.set_default_size(1100, 720)

        self.api = MusicApiClient()
        self.player = Player()
        self.discord_rpc = DiscordRPC()

        self.toast_overlay = Adw.ToastOverlay()
        self.set_content(self.toast_overlay)

        self.root_stack = Gtk.Stack()
        self.root_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.toast_overlay.set_child(self.root_stack)

        # --- Écran de connexion ---
        self.connect_view = ConnectView(self.api, self._on_connected)
        self.root_stack.add_named(self.connect_view, "connect")

        # --- Application principale (construite après connexion) ---
        self.app_box = None
        self.root_stack.set_visible_child_name("connect")

        self.player.connect("eos", self._on_track_ended)
        self.player.connect("error", self._on_player_error)
        self.player.connect("state-changed", self._on_player_state_changed)

        self.current_track = None
        self.connect("close-request", self._on_close_request)

    # ------------------------------------------------------------------
    # Connexion réussie -> construire l'UI principale
    # ------------------------------------------------------------------

    def _on_connected(self, host, port):
        self._build_main_ui()
        self.root_stack.set_visible_child_name("main")
        self._refresh_auth_state()

    def _build_main_ui(self):
        split = Adw.NavigationSplitView()
        split.set_min_sidebar_width(200)
        split.set_max_sidebar_width(260)

        # --- Sidebar ---
        sidebar_page = Adw.NavigationPage(title="MusicApp")
        sidebar_toolbar = Adw.ToolbarView()
        sidebar_header = Adw.HeaderBar()
        sidebar_header.set_show_end_title_buttons(False)
        sidebar_toolbar.add_top_bar(sidebar_header)

        self.nav_listbox = Gtk.ListBox()
        self.nav_listbox.add_css_class("navigation-sidebar")
        self.nav_listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.nav_listbox.connect("row-selected", self._on_nav_selected)

        for key, label, icon_name in NAV_ITEMS:
            row = Gtk.ListBoxRow()
            row.nav_key = key
            hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            hbox.set_margin_top(8)
            hbox.set_margin_bottom(8)
            hbox.set_margin_start(10)
            hbox.set_margin_end(10)
            hbox.append(Gtk.Image.new_from_icon_name(icon_name))
            hbox.append(Gtk.Label(label=label, xalign=0))
            row.set_child(hbox)
            self.nav_listbox.append(row)

        sidebar_toolbar.set_content(self.nav_listbox)
        sidebar_page.set_child(sidebar_toolbar)
        split.set_sidebar(sidebar_page)

        # --- Contenu principal (vues + barre de lecture) ---
        content_page = Adw.NavigationPage(title="MusicApp")
        content_toolbar = Adw.ToolbarView()
        content_header = Adw.HeaderBar()
        content_toolbar.add_top_bar(content_header)

        outer_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        content_toolbar.set_content(outer_box)

        self.view_stack = Gtk.Stack()
        self.view_stack.set_vexpand(True)
        self.view_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        outer_box.append(self.view_stack)

        separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        outer_box.append(separator)

        self.player_bar = PlayerBar(
            self.player,
            on_next=self._on_next_clicked,
            on_add_to_playlist=self._open_add_to_playlist,
        )
        outer_box.append(self.player_bar)

        content_page.set_child(content_toolbar)
        split.set_content(content_page)

        self.root_stack.add_named(split, "main")

        # --- Vues ---
        self.home_view = self._build_home_view()
        self.view_stack.add_named(self.home_view, "home")

        self.search_view = SearchView(
            self.api,
            on_play=self.play_track,
            on_queue=self._queue_track,
            on_add_to_playlist=self._open_add_to_playlist,
            on_open_album=self._open_album,
            on_open_artist=self._open_artist,
        )
        self.view_stack.add_named(self.search_view, "search")

        self.detail_view = DetailView(
            self.api,
            on_play=self.play_track,
            on_queue=self._queue_track,
            on_add_to_playlist=self._open_add_to_playlist,
            on_back=lambda: self.view_stack.set_visible_child_name("search"),
        )
        self.view_stack.add_named(self.detail_view, "detail")

        self.queue_view = QueueView(self.api, on_play=self.play_track)
        self.view_stack.add_named(self.queue_view, "queue")

        self.playlists_view = PlaylistsView(
            self.api, on_play=self.play_track, is_logged_in=lambda: self.api.current_user is not None
        )
        self.view_stack.add_named(self.playlists_view, "playlists")

        self.account_view = AccountView(self.api, on_auth_changed=self._refresh_auth_state)
        self.view_stack.add_named(self.account_view, "account")

        self.view_stack.set_visible_child_name("home")
        self.nav_listbox.select_row(self.nav_listbox.get_row_at_index(0))

    def _build_home_view(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(24)
        box.set_margin_start(24)
        box.set_margin_end(24)

        title = Gtk.Label(label="Bienvenue", xalign=0)
        title.add_css_class("title-1")
        box.append(title)

        subtitle = Gtk.Label(
            label="Utilise la recherche pour trouver des morceaux, albums et artistes.",
            xalign=0,
        )
        subtitle.add_css_class("dim-label")
        box.append(subtitle)

        search_btn = Gtk.Button(label="Rechercher")
        search_btn.add_css_class("suggested-action")
        search_btn.add_css_class("pill")
        search_btn.set_halign(Gtk.Align.START)
        search_btn.connect("clicked", lambda *_: self._select_nav("search"))
        box.append(search_btn)

        return box

    def _select_nav(self, key):
        for i in range(len(NAV_ITEMS)):
            row = self.nav_listbox.get_row_at_index(i)
            if row.nav_key == key:
                self.nav_listbox.select_row(row)
                break

    def _on_nav_selected(self, _listbox, row):
        if row is None:
            return
        key = row.nav_key
        self.view_stack.set_visible_child_name(key)
        if key == "queue":
            self.queue_view.refresh()
        elif key == "playlists":
            self.playlists_view.refresh()
        elif key == "account":
            self.account_view.refresh()

    # ------------------------------------------------------------------
    # Lecture
    # ------------------------------------------------------------------

    def play_track(self, track: dict):
        self.current_track = track
        self.player_bar.set_track(track)
        url = self.api.stream_url(track["id"])
        self.player.load(url, autoplay=True)
        self._add_toast(f"Lecture : {track.get('title', '')}")
        self.discord_rpc.update_track(track)

    def _on_player_state_changed(self, _player, state):
        if not self.current_track:
            return
        if state == "playing":
            self.discord_rpc.update_track(
                self.current_track,
                position_seconds=self.player.get_position(),
                duration_seconds=self.player.get_duration(),
            )
        elif state == "paused":
            self.discord_rpc.set_paused(self.current_track)
        elif state == "stopped":
            self.discord_rpc.clear()

    def _on_close_request(self, *_args):
        self.discord_rpc.clear()
        self.discord_rpc.shutdown()
        return False

    def _queue_track(self, track: dict):
        def worker():
            try:
                self.api.queue_add(track)
                GLib.idle_add(lambda: self._add_toast("Ajouté à la file d'attente"))
            except Exception as exc:
                GLib.idle_add(lambda: self._add_toast(f"Erreur : {exc}"))

        threading.Thread(target=worker, daemon=True).start()

    def _on_next_clicked(self):
        def worker():
            try:
                data = self.api.queue_advance()
                track = data.get("track")
                if track:
                    GLib.idle_add(self.play_track, track)
                else:
                    GLib.idle_add(lambda: self._add_toast("File d'attente vide"))
            except Exception as exc:
                GLib.idle_add(lambda: self._add_toast(f"Erreur : {exc}"))

        threading.Thread(target=worker, daemon=True).start()

    def _on_track_ended(self, _player):
        self._on_next_clicked()

    def _on_player_error(self, _player, message):
        self._add_toast(f"Erreur de lecture : {message}")

    # ------------------------------------------------------------------
    # Navigation détail
    # ------------------------------------------------------------------

    def _open_album(self, item: dict):
        browse_id = item.get("browseId") or item.get("browse_id")
        if not browse_id:
            return
        self.view_stack.set_visible_child_name("detail")
        self.detail_view.load_album(browse_id)

    def _open_artist(self, item: dict):
        browse_id = item.get("browseId") or item.get("browse_id")
        if not browse_id:
            return
        self.view_stack.set_visible_child_name("detail")
        self.detail_view.load_artist(browse_id)

    def _open_add_to_playlist(self, track: dict):
        self.playlists_view.open_add_to_playlist_dialog(track, self)

    # ------------------------------------------------------------------
    # Divers
    # ------------------------------------------------------------------

    def _refresh_auth_state(self):
        def worker():
            try:
                self.api.me()
            except Exception:
                pass
            GLib.idle_add(self._on_auth_refreshed)

        threading.Thread(target=worker, daemon=True).start()

    def _on_auth_refreshed(self):
        if hasattr(self, "account_view"):
            self.account_view.refresh()
        return False

    def add_toast(self, toast: Adw.Toast):
        self.toast_overlay.add_toast(toast)

    def _add_toast(self, message: str):
        self.toast_overlay.add_toast(Adw.Toast(title=message, timeout=3))
