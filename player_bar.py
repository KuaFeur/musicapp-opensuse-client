#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
player_bar.py — Barre de lecture persistante en bas de la fenêtre :
pochette, titre/artiste, contrôles play/pause/next, barre de progression, volume.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib  # noqa: E402

from widgets import load_thumbnail_async


def format_time(seconds: float) -> str:
    seconds = max(0, int(seconds))
    m, s = divmod(seconds, 60)
    return f"{m}:{s:02d}"


class PlayerBar(Gtk.Box):
    def __init__(self, player, on_next, on_add_to_playlist=None):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.player = player
        self.on_next = on_next
        self.on_add_to_playlist = on_add_to_playlist
        self.current_track = None
        self._seeking = False

        self.add_css_class("toolbar")
        self.set_margin_top(6)
        self.set_margin_bottom(6)
        self.set_margin_start(12)
        self.set_margin_end(12)

        # Pochette + infos
        self.avatar = Adw.Avatar(size=44, show_initials=True, text="?")
        self.append(self.avatar)

        info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        info_box.set_valign(Gtk.Align.CENTER)
        info_box.set_size_request(160, -1)
        self.append(info_box)

        self.title_label = Gtk.Label(label="Aucun morceau", xalign=0)
        self.title_label.set_ellipsize(3)
        self.title_label.add_css_class("heading")
        info_box.append(self.title_label)

        self.artist_label = Gtk.Label(label="", xalign=0)
        self.artist_label.set_ellipsize(3)
        self.artist_label.add_css_class("dim-label")
        self.artist_label.add_css_class("caption")
        info_box.append(self.artist_label)

        # Contrôles centraux
        center_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        center_box.set_hexpand(True)
        center_box.set_valign(Gtk.Align.CENTER)
        self.append(center_box)

        controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6, halign=Gtk.Align.CENTER)
        center_box.append(controls)

        self.play_button = Gtk.Button(icon_name="media-playback-start-symbolic")
        self.play_button.add_css_class("circular")
        self.play_button.connect("clicked", self._on_play_pause)
        controls.append(self.play_button)

        self.next_button = Gtk.Button(icon_name="media-skip-forward-symbolic")
        self.next_button.add_css_class("flat")
        self.next_button.connect("clicked", lambda *_: self.on_next())
        controls.append(self.next_button)

        if self.on_add_to_playlist is not None:
            self.add_button = Gtk.Button(icon_name="bookmark-new-symbolic")
            self.add_button.add_css_class("flat")
            self.add_button.set_tooltip_text("Ajouter à une playlist")
            self.add_button.connect("clicked", self._on_add_clicked)
            controls.append(self.add_button)

        # Barre de progression
        progress_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        center_box.append(progress_box)

        self.position_label = Gtk.Label(label="0:00")
        self.position_label.add_css_class("caption")
        self.position_label.add_css_class("dim-label")
        progress_box.append(self.position_label)

        self.progress_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        self.progress_scale.set_hexpand(True)
        self.progress_scale.set_draw_value(False)
        self.progress_scale.connect("change-value", self._on_seek)
        progress_box.append(self.progress_scale)

        self.duration_label = Gtk.Label(label="0:00")
        self.duration_label.add_css_class("caption")
        self.duration_label.add_css_class("dim-label")
        progress_box.append(self.duration_label)

        # Volume
        vol_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        vol_box.set_valign(Gtk.Align.CENTER)
        self.append(vol_box)

        vol_icon = Gtk.Image.new_from_icon_name("audio-volume-high-symbolic")
        vol_box.append(vol_icon)

        self.volume_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 1, 0.05)
        self.volume_scale.set_value(1.0)
        self.volume_scale.set_size_request(100, -1)
        self.volume_scale.set_draw_value(False)
        self.volume_scale.connect("value-changed", self._on_volume_changed)
        vol_box.append(self.volume_scale)

        # Ticker de progression
        GLib.timeout_add(500, self._tick)

        self.player.connect("state-changed", self._on_state_changed)
        self.player.connect("duration-changed", self._on_duration_changed)

    # ------------------------------------------------------------------

    def set_track(self, track: dict):
        self.current_track = track
        self.title_label.set_text(track.get("title", "Inconnu"))
        self.artist_label.set_text(track.get("artist", ""))
        self.avatar.set_text(track.get("title", "?"))
        load_thumbnail_async(self.avatar, track.get("thumbnail", ""))
        self.progress_scale.set_value(0)
        self.position_label.set_text("0:00")
        self.duration_label.set_text("0:00")

    def _on_add_clicked(self, *_args):
        if self.current_track and self.on_add_to_playlist:
            self.on_add_to_playlist(self.current_track)

    def _on_play_pause(self, *_args):
        if self.player.is_playing():
            self.player.pause()
        else:
            self.player.play()

    def _on_state_changed(self, _player, state):
        icon = "media-playback-pause-symbolic" if state == "playing" else "media-playback-start-symbolic"
        self.play_button.set_icon_name(icon)

    def _on_duration_changed(self, _player, seconds):
        self.duration_label.set_text(format_time(seconds))
        self.progress_scale.set_range(0, max(1, seconds))

    def _on_seek(self, _scale, _scroll_type, value):
        self.player.seek(value)
        return False

    def _on_volume_changed(self, scale):
        self.player.set_volume(scale.get_value())

    def _tick(self):
        if self.current_track:
            pos = self.player.get_position()
            dur = self.player.get_duration()
            if dur and self.progress_scale.get_adjustment().get_upper() != dur:
                self.progress_scale.set_range(0, dur)
                self.duration_label.set_text(format_time(dur))
            self.progress_scale.set_value(pos)
            self.position_label.set_text(format_time(pos))
        return True
