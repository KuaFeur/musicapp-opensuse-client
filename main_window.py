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
from search_view import SearchView
from detail_view import DetailView
from queue_view import QueueView
from playlists_view import PlaylistsView
from account_view import AccountView
from player_bar import PlayerBar
from discord_rpc import DiscordRPC
from widgets import TrackRow
import history
import updater


DEFAULT_HOST = "music.linkua.me"
DEFAULT_PORT = "80"


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

        # --- Écran de chargement (connexion auto au serveur) ---
        self.loading_page = self._build_loading_view()
        self.root_stack.add_named(self.loading_page, "loading")
        self.root_stack.set_visible_child_name("loading")

        self.player.connect("eos", self._on_track_ended)
        self.player.connect("error", self._on_player_error)
        self.player.connect("state-changed", self._on_player_state_changed)

        self.current_track = None
        self.shuffle_enabled = False
        self.repeat_mode = "off"  # "off" | "all" | "one"
        self.connect("close-request", self._on_close_request)

        self._auto_connect()

    def _build_loading_view(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        box.set_valign(Gtk.Align.CENTER)
        box.set_halign(Gtk.Align.CENTER)

        icon = Gtk.Image.new_from_icon_name("audio-headphones-symbolic")
        icon.set_pixel_size(64)
        icon.add_css_class("dim-label")
        box.append(icon)

        self.loading_label = Gtk.Label(label=f"Connexion à {DEFAULT_HOST}…")
        self.loading_label.add_css_class("title-2")
        box.append(self.loading_label)

        self.loading_spinner = Gtk.Spinner()
        self.loading_spinner.set_spinning(True)
        box.append(self.loading_spinner)

        self.loading_retry_btn = Gtk.Button(label="Réessayer")
        self.loading_retry_btn.add_css_class("pill")
        self.loading_retry_btn.set_visible(False)
        self.loading_retry_btn.connect("clicked", lambda *_: self._auto_connect())
        box.append(self.loading_retry_btn)

        return box

    # ------------------------------------------------------------------
    # Connexion automatique au serveur par défaut
    # ------------------------------------------------------------------

    def _auto_connect(self):
        self.loading_label.set_text(f"Connexion à {DEFAULT_HOST}…")
        self.loading_spinner.set_spinning(True)
        self.loading_retry_btn.set_visible(False)
        self.api.configure(DEFAULT_HOST, DEFAULT_PORT)

        def worker():
            try:
                self.api.test_connection()
                GLib.idle_add(self._on_connected, DEFAULT_HOST, DEFAULT_PORT)
            except Exception as exc:
                GLib.idle_add(self._on_connect_failed, str(exc))

        threading.Thread(target=worker, daemon=True).start()

    def _on_connect_failed(self, error_message: str):
        self.loading_spinner.set_spinning(False)
        self.loading_label.set_text(f"Connexion à {DEFAULT_HOST} impossible : {error_message}")
        self.loading_retry_btn.set_visible(True)
        return False

    # ------------------------------------------------------------------
    # Connexion réussie -> construire l'UI principale
    # ------------------------------------------------------------------

    def _on_connected(self, host, port):
        self._build_main_ui()
        self.root_stack.set_visible_child_name("main")
        self._refresh_auth_state()
        self._check_update_on_startup()

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
            on_shuffle_toggled=self._on_shuffle_toggled,
            on_repeat_toggled=self._on_repeat_toggled,
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
        scrolled = Gtk.ScrolledWindow(vexpand=True)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(24)
        box.set_margin_start(24)
        box.set_margin_end(24)
        box.set_margin_bottom(24)
        scrolled.set_child(box)

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

        recent_label = Gtk.Label(label="Écouté récemment", xalign=0)
        recent_label.add_css_class("title-3")
        recent_label.set_margin_top(18)
        box.append(recent_label)

        self.recent_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.append(self.recent_box)

        self._refresh_recent()

        return scrolled

    def _refresh_recent(self):
        child = self.recent_box.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.recent_box.remove(child)
            child = nxt

        recent = history.get_recent(10)
        if not recent:
            placeholder = Gtk.Label(label="Aucune écoute pour l'instant.", xalign=0)
            placeholder.add_css_class("dim-label")
            self.recent_box.append(placeholder)
            return

        for track in recent:
            row = TrackRow(
                track,
                on_play=self.play_track,
                on_queue=self._queue_track,
                on_add_to_playlist=self._open_add_to_playlist,
            )
            self.recent_box.append(row)

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
        if key == "home":
            self._refresh_recent()
        elif key == "queue":
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
        history.add_track(track)
        if hasattr(self, "recent_box"):
            self._refresh_recent()

    def _on_shuffle_toggled(self, enabled: bool):
        self.shuffle_enabled = enabled

    def _on_repeat_toggled(self, mode: str):
        self.repeat_mode = mode

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
                if self.shuffle_enabled:
                    data = self.api.queue_advance_random()
                else:
                    data = self.api.queue_advance()
                track = data.get("track")
                if track:
                    GLib.idle_add(self.play_track, track)
                elif self.repeat_mode == "all" and self.current_track:
                    # File vide mais répétition de la file active : on
                    # relance simplement le morceau courant (le serveur ne
                    # connaissant pas l'historique complet de la file, on
                    # ne peut pas reconstituer l'ordre original).
                    GLib.idle_add(self.play_track, self.current_track)
                else:
                    GLib.idle_add(lambda: self._add_toast("File d'attente vide"))
            except Exception as exc:
                GLib.idle_add(lambda: self._add_toast(f"Erreur : {exc}"))

        threading.Thread(target=worker, daemon=True).start()

    def _on_track_ended(self, _player):
        if self.repeat_mode == "one" and self.current_track:
            self.play_track(self.current_track)
            return
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

    # ------------------------------------------------------------------
    # Mise à jour automatique au démarrage
    # ------------------------------------------------------------------

    def _check_update_on_startup(self):
        def worker():
            try:
                result = updater.check_for_update()
                if result["update_available"]:
                    GLib.idle_add(self._on_startup_update_found, result)
            except Exception:
                pass  # échec silencieux : pas de perturbation au démarrage

        threading.Thread(target=worker, daemon=True).start()

    def _on_startup_update_found(self, result: dict):
        remote = result["remote"]

        def do_update():
            def worker():
                try:
                    updated_files = updater.apply_update(remote["sha"])
                    GLib.idle_add(self._on_startup_update_applied, len(updated_files))
                except Exception as exc:
                    GLib.idle_add(
                        lambda: self._add_toast(f"Échec de la mise à jour automatique : {exc}")
                    )

            threading.Thread(target=worker, daemon=True).start()

        toast = Adw.Toast(title="Mise à jour du client disponible, installation…", timeout=4)
        self.add_toast(toast)
        do_update()
        return False

    def _on_startup_update_applied(self, count: int):
        if count:
            self._add_toast(f"Mise à jour installée ({count} fichier(s)). Redémarre l'app pour l'appliquer.")
        return False
