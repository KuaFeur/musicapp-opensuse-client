#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
playlists_view.py — Vue playlists : liste des playlists de l'utilisateur,
création, détail avec morceaux, et boîte de dialogue "ajouter à une playlist".
"""

from __future__ import annotations

import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib  # noqa: E402

from widgets import TrackRow


class PlaylistsView(Gtk.Box):
    def __init__(self, api, on_play, is_logged_in):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.api = api
        self.on_play = on_play
        self.is_logged_in = is_logged_in
        self.current_playlist_id = None

        self.stack = Gtk.Stack()
        self.stack.set_vexpand(True)
        self.append(self.stack)

        # --- Vue "non connecté" ---
        self.auth_required = Adw.StatusPage(
            title="Connecte-toi pour voir tes playlists",
            icon_name="dialog-password-symbolic",
        )
        self.stack.add_named(self.auth_required, "auth-required")

        # --- Liste des playlists ---
        list_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.stack.add_named(list_page, "list")

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        header.set_margin_top(12)
        header.set_margin_start(16)
        header.set_margin_end(16)
        list_page.append(header)

        title = Gtk.Label(label="Playlists", xalign=0, hexpand=True)
        title.add_css_class("title-1")
        header.append(title)

        new_btn = Gtk.Button(icon_name="list-add-symbolic")
        new_btn.add_css_class("flat")
        new_btn.set_tooltip_text("Nouvelle playlist")
        new_btn.connect("clicked", self._open_new_playlist_dialog)
        header.append(new_btn)

        scrolled = Gtk.ScrolledWindow(vexpand=True)
        list_page.append(scrolled)

        self.playlists_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.playlists_box.set_margin_top(6)
        self.playlists_box.set_margin_bottom(16)
        self.playlists_box.set_margin_start(16)
        self.playlists_box.set_margin_end(16)
        scrolled.set_child(self.playlists_box)

        # --- Détail d'une playlist ---
        detail_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.stack.add_named(detail_page, "detail")

        detail_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        detail_header.set_margin_top(12)
        detail_header.set_margin_start(16)
        detail_header.set_margin_end(16)
        detail_page.append(detail_header)

        back_btn = Gtk.Button(icon_name="go-previous-symbolic")
        back_btn.add_css_class("flat")
        back_btn.connect("clicked", lambda *_: self.show_list())
        detail_header.append(back_btn)

        self.detail_title = Gtk.Label(label="", xalign=0, hexpand=True)
        self.detail_title.add_css_class("title-2")
        detail_header.append(self.detail_title)

        detail_scrolled = Gtk.ScrolledWindow(vexpand=True)
        detail_page.append(detail_scrolled)

        self.detail_tracks_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.detail_tracks_box.set_margin_top(6)
        self.detail_tracks_box.set_margin_bottom(16)
        self.detail_tracks_box.set_margin_start(16)
        self.detail_tracks_box.set_margin_end(16)
        detail_scrolled.set_child(self.detail_tracks_box)

    # ------------------------------------------------------------------

    def refresh(self):
        if not self.is_logged_in():
            self.stack.set_visible_child_name("auth-required")
            return
        self.stack.set_visible_child_name("list")
        self._clear_box(self.playlists_box)

        def worker():
            try:
                data = self.api.playlists_get()
                GLib.idle_add(self._render_list, data.get("playlists", []))
            except Exception as exc:
                GLib.idle_add(self._render_list_error, str(exc))

        threading.Thread(target=worker, daemon=True).start()

    def show_list(self):
        self.stack.set_visible_child_name("list")

    def _clear_box(self, box):
        child = box.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            box.remove(child)
            child = nxt

    def _render_list_error(self, message):
        self._clear_box(self.playlists_box)
        status = Adw.StatusPage(title="Erreur", description=message)
        self.playlists_box.append(status)
        return False

    def _render_list(self, playlists: list):
        self._clear_box(self.playlists_box)
        if not playlists:
            status = Adw.StatusPage(title="Aucune playlist pour l'instant.", icon_name="view-list-symbolic")
            self.playlists_box.append(status)
            return False

        for p in playlists:
            row = Adw.ActionRow(title=p["name"], subtitle=f"{p['track_count']} morceau(x)")
            row.set_activatable(True)
            row.connect("activated", lambda _r, pid=p["id"], name=p["name"]: self.open_playlist(pid, name))

            remove_btn = Gtk.Button(icon_name="user-trash-symbolic")
            remove_btn.add_css_class("flat")
            remove_btn.set_valign(Gtk.Align.CENTER)
            remove_btn.connect("clicked", lambda _b, pid=p["id"]: self._delete_playlist(pid))
            row.add_suffix(remove_btn)

            self.playlists_box.append(row)
        return False

    def _delete_playlist(self, playlist_id: int):
        def worker():
            try:
                self.api.playlist_delete(playlist_id)
                GLib.idle_add(self.refresh)
            except Exception:
                pass

        threading.Thread(target=worker, daemon=True).start()

    def open_playlist(self, playlist_id: int, name: str):
        self.current_playlist_id = playlist_id
        self.detail_title.set_text(name)
        self.stack.set_visible_child_name("detail")
        self._clear_box(self.detail_tracks_box)

        def worker():
            try:
                data = self.api.playlist_detail(playlist_id)
                GLib.idle_add(self._render_detail, data.get("tracks", []), playlist_id)
            except Exception as exc:
                GLib.idle_add(self._render_detail_error, str(exc))

        threading.Thread(target=worker, daemon=True).start()

    def _render_detail_error(self, message):
        self._clear_box(self.detail_tracks_box)
        status = Adw.StatusPage(title="Erreur", description=message)
        self.detail_tracks_box.append(status)
        return False

    def _render_detail(self, tracks: list, playlist_id: int):
        self._clear_box(self.detail_tracks_box)
        if not tracks:
            status = Adw.StatusPage(title="Playlist vide.", icon_name="view-list-symbolic")
            self.detail_tracks_box.append(status)
            return False

        for track in tracks:
            track_id = track.get("track_id", track.get("id"))
            row = TrackRow(
                {**track, "id": track_id},
                on_play=self.on_play,
                on_remove=lambda t, pid=playlist_id: self._remove_track(pid, t.get("id")),
                show_remove=True,
            )
            self.detail_tracks_box.append(row)
        return False

    def _remove_track(self, playlist_id: int, track_id: str):
        def worker():
            try:
                self.api.playlist_remove_track(playlist_id, track_id)
                GLib.idle_add(lambda: self.open_playlist(playlist_id, self.detail_title.get_text()))
            except Exception:
                pass

        threading.Thread(target=worker, daemon=True).start()

    # ------------------------------------------------------------------
    # Nouvelle playlist
    # ------------------------------------------------------------------

    def _open_new_playlist_dialog(self, *_args):
        root = self.get_root()
        dialog = Adw.MessageDialog(
            transient_for=root,
            heading="Nouvelle playlist",
            body="Choisis un nom pour ta nouvelle playlist.",
        )
        entry = Gtk.Entry()
        entry.set_activates_default(True)
        dialog.set_extra_child(entry)
        dialog.add_response("cancel", "Annuler")
        dialog.add_response("create", "Créer")
        dialog.set_response_appearance("create", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("create")

        def on_response(_dlg, response):
            if response == "create":
                name = entry.get_text().strip()
                if name:
                    self._create_playlist(name)

        dialog.connect("response", on_response)
        dialog.present()

    def _create_playlist(self, name: str):
        def worker():
            try:
                self.api.playlist_create(name)
                GLib.idle_add(self.refresh)
            except Exception:
                pass

        threading.Thread(target=worker, daemon=True).start()

    # ------------------------------------------------------------------
    # Boîte de dialogue "Ajouter à une playlist" (appelée depuis d'autres vues)
    # ------------------------------------------------------------------

    def open_add_to_playlist_dialog(self, track: dict, parent_window):
        if not self.is_logged_in():
            toast = Adw.Toast(title="Connecte-toi pour utiliser les playlists.")
            if hasattr(parent_window, "add_toast"):
                parent_window.add_toast(toast)
            return

        def worker():
            try:
                data = self.api.playlists_get()
                GLib.idle_add(self._show_add_dialog, data.get("playlists", []), track, parent_window)
            except Exception:
                pass

        threading.Thread(target=worker, daemon=True).start()

    def _show_add_dialog(self, playlists: list, track: dict, parent_window):
        dialog = Adw.MessageDialog(
            transient_for=parent_window,
            heading="Ajouter à une playlist",
            body=track.get("title", ""),
        )
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_margin_top(8)
        box.set_margin_bottom(8)

        if not playlists:
            box.append(Gtk.Label(label="Aucune playlist. Crée-en une d'abord."))
        else:
            names = [p["name"] for p in playlists]
            dropdown = Gtk.DropDown.new_from_strings(names)
            box.append(dropdown)
            dialog.set_extra_child(box)
            dialog.add_response("cancel", "Annuler")
            dialog.add_response("add", "Ajouter")
            dialog.set_response_appearance("add", Adw.ResponseAppearance.SUGGESTED)

            def on_response(_dlg, response):
                if response == "add":
                    idx = dropdown.get_selected()
                    playlist_id = playlists[idx]["id"]
                    self._add_to_playlist(playlist_id, track)

            dialog.connect("response", on_response)
            dialog.present()
            return

        dialog.set_extra_child(box)
        dialog.add_response("ok", "OK")
        dialog.present()

    def _add_to_playlist(self, playlist_id: int, track: dict):
        def worker():
            try:
                self.api.playlist_add_track(playlist_id, track)
            except Exception:
                pass

        threading.Thread(target=worker, daemon=True).start()
