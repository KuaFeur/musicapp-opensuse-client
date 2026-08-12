#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
widgets.py — Widgets réutilisables : ligne de morceau, carte album/artiste,
avatar avec chargement d'image en arrière-plan.
"""

from __future__ import annotations

import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib, GdkPixbuf, Gio  # noqa: E402

import requests


# Cache mémoire des textures déjà téléchargées, partagé par tous les
# widgets de l'app (avatars de morceau, cartes album/artiste, barre de
# lecture…). Évite de retélécharger la même pochette à chaque fois qu'un
# widget est recréé (changement d'onglet, rafraîchissement de liste, etc.).
_THUMBNAIL_CACHE: dict[str, object] = {}
_THUMBNAIL_CACHE_MAX = 500  # évite une croissance illimitée sur une longue session


def load_thumbnail_async(avatar_or_picture, url: str, is_picture: bool = False):
    """Charge une image distante dans un Adw.Avatar (custom-image) ou Gtk.Picture.
    Sert d'abord depuis le cache mémoire si l'image a déjà été chargée."""
    if not url:
        return

    cached = _THUMBNAIL_CACHE.get(url)
    if cached is not None:
        _apply_texture(avatar_or_picture, cached, is_picture)
        return

    def worker():
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            loader = GdkPixbuf.PixbufLoader()
            loader.write(resp.content)
            loader.close()
            pixbuf = loader.get_pixbuf()
            from gi.repository import Gdk
            gtexture = Gdk.Texture.new_for_pixbuf(pixbuf)

            if len(_THUMBNAIL_CACHE) >= _THUMBNAIL_CACHE_MAX:
                # Purge simple : on vide tout plutôt que de gérer un LRU,
                # le coût de re-télécharger occasionnellement est faible.
                _THUMBNAIL_CACHE.clear()
            _THUMBNAIL_CACHE[url] = gtexture

            GLib.idle_add(_apply_texture, avatar_or_picture, gtexture, is_picture)
        except Exception:
            pass

    threading.Thread(target=worker, daemon=True).start()


def _apply_texture(avatar_or_picture, texture, is_picture: bool):
    if is_picture:
        avatar_or_picture.set_paintable(texture)
    else:
        avatar_or_picture.set_custom_image(texture)
    return False


class TrackRow(Gtk.Box):
    """Une ligne de morceau : pochette, titre/artiste, durée, menu d'actions."""

    def __init__(self, track: dict, on_play, on_queue=None, on_add_to_playlist=None, on_remove=None, show_remove=False):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.track = track
        self.set_margin_top(4)
        self.set_margin_bottom(4)
        self.set_margin_start(8)
        self.set_margin_end(8)

        avatar = Adw.Avatar(size=40, text=track.get("title", "?"), show_initials=True)
        load_thumbnail_async(avatar, track.get("thumbnail", ""))
        self.append(avatar)

        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        text_box.set_hexpand(True)
        text_box.set_valign(Gtk.Align.CENTER)
        self.append(text_box)

        title_label = Gtk.Label(label=track.get("title", "Inconnu"), xalign=0)
        title_label.set_ellipsize(3)  # PANGO_ELLIPSIZE_END
        title_label.add_css_class("heading")
        text_box.append(title_label)

        artist_label = Gtk.Label(label=track.get("artist", ""), xalign=0)
        artist_label.set_ellipsize(3)
        artist_label.add_css_class("dim-label")
        artist_label.add_css_class("caption")
        text_box.append(artist_label)

        duration = track.get("duration", "")
        if duration:
            dur_label = Gtk.Label(label=duration)
            dur_label.add_css_class("dim-label")
            dur_label.add_css_class("caption")
            dur_label.set_valign(Gtk.Align.CENTER)
            self.append(dur_label)

        play_btn = Gtk.Button(icon_name="media-playback-start-symbolic")
        play_btn.add_css_class("flat")
        play_btn.set_valign(Gtk.Align.CENTER)
        play_btn.set_tooltip_text("Lire")
        play_btn.connect("clicked", lambda *_: on_play(track))
        self.append(play_btn)

        if on_queue is not None:
            queue_btn = Gtk.Button(icon_name="list-add-symbolic")
            queue_btn.add_css_class("flat")
            queue_btn.set_valign(Gtk.Align.CENTER)
            queue_btn.set_tooltip_text("Ajouter à la file d'attente")
            queue_btn.connect("clicked", lambda *_: on_queue(track))
            self.append(queue_btn)

        if on_add_to_playlist is not None:
            pl_btn = Gtk.Button(icon_name="bookmark-new-symbolic")
            pl_btn.add_css_class("flat")
            pl_btn.set_valign(Gtk.Align.CENTER)
            pl_btn.set_tooltip_text("Ajouter à une playlist")
            pl_btn.connect("clicked", lambda *_: on_add_to_playlist(track))
            self.append(pl_btn)

        if show_remove and on_remove is not None:
            rm_btn = Gtk.Button(icon_name="user-trash-symbolic")
            rm_btn.add_css_class("flat")
            rm_btn.set_valign(Gtk.Align.CENTER)
            rm_btn.set_tooltip_text("Retirer")
            rm_btn.connect("clicked", lambda *_: on_remove(track))
            self.append(rm_btn)

        # Clic sur la ligne = lecture
        click = Gtk.GestureClick()
        click.connect("released", lambda *_: on_play(track))
        text_box.add_controller(click)


class ResultCard(Gtk.Box):
    """Carte pour un album ou un artiste dans les résultats de recherche."""

    def __init__(self, item: dict, kind: str, on_activate):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.item = item
        self.set_size_request(140, -1)

        avatar = Adw.Avatar(
            size=120,
            text=item.get("name") or item.get("title", "?"),
            show_initials=True,
        )
        if kind == "artist":
            avatar.set_property("visible", True)
        load_thumbnail_async(avatar, item.get("thumbnail", ""))
        self.append(avatar)

        name = item.get("name") or item.get("title", "")
        name_label = Gtk.Label(label=name, xalign=0.5)
        name_label.set_ellipsize(3)
        name_label.set_wrap(True)
        name_label.set_lines(2)
        name_label.set_justify(Gtk.Justification.CENTER)
        name_label.add_css_class("heading")
        self.append(name_label)

        subtitle = item.get("artist", "") if kind == "album" else "Artiste"
        if subtitle:
            sub_label = Gtk.Label(label=subtitle, xalign=0.5)
            sub_label.add_css_class("dim-label")
            sub_label.add_css_class("caption")
            sub_label.set_ellipsize(3)
            self.append(sub_label)

        click = Gtk.GestureClick()
        click.connect("released", lambda *_: on_activate(item))
        self.add_controller(click)

        btn_cursor = Gtk.EventControllerMotion()
        self.add_controller(btn_cursor)
