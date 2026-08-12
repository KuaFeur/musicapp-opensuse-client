#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
player.py — Lecteur audio basé sur GStreamer (playbin), avec position,
durée, volume et un jeu de signaux simples pour l'UI.
"""

from __future__ import annotations

import gi

gi.require_version("Gst", "1.0")
from gi.repository import Gst, GObject  # noqa: E402

Gst.init(None)


class Player(GObject.Object):
    """
    Enveloppe playbin. Émet :
      - "state-changed" (str state: 'playing'|'paused'|'stopped')
      - "eos"            : fin du morceau
      - "error" (str msg)
      - "duration-changed" (int seconds)
    """

    __gsignals__ = {
        "state-changed": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "eos": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "error": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "duration-changed": (GObject.SignalFlags.RUN_FIRST, None, (int,)),
    }

    def __init__(self):
        super().__init__()
        self.playbin = Gst.ElementFactory.make("playbin", "player")
        if self.playbin is None:
            raise RuntimeError(
                "Impossible de créer l'élément GStreamer 'playbin'. "
                "Vérifie que gstreamer1-plugins-base/good/bad sont installés."
            )

        # Flux purement audio : on désactive toute piste vidéo pour éviter
        # que playbin n'ouvre une fenêtre séparée quand le flux contient une
        # pochette embarquée (souvent détectée comme piste vidéo/image).
        GST_PLAY_FLAG_VIDEO = 1 << 0
        flags = self.playbin.get_property("flags")
        self.playbin.set_property("flags", flags & ~GST_PLAY_FLAG_VIDEO)
        # Puits vidéo "fakesink" en secours, au cas où une piste vidéo
        # persisterait malgré le flag ci-dessus.
        fakesink = Gst.ElementFactory.make("fakesink", "video_fake_sink")
        if fakesink is not None:
            self.playbin.set_property("video-sink", fakesink)

        bus = self.playbin.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self._on_bus_message)
        self._duration = 0
        self._current_url = None

    # ------------------------------------------------------------------
    # Contrôle
    # ------------------------------------------------------------------

    def load(self, url: str, autoplay: bool = True):
        self.playbin.set_state(Gst.State.NULL)
        self._current_url = url
        self._duration = 0
        self.playbin.set_property("uri", url)
        self.playbin.set_state(Gst.State.PLAYING if autoplay else Gst.State.PAUSED)

    def play(self):
        self.playbin.set_state(Gst.State.PLAYING)
        self.emit("state-changed", "playing")

    def pause(self):
        self.playbin.set_state(Gst.State.PAUSED)
        self.emit("state-changed", "paused")

    def stop(self):
        self.playbin.set_state(Gst.State.NULL)
        self.emit("state-changed", "stopped")

    def set_volume(self, value: float):
        """value entre 0.0 et 1.0"""
        self.playbin.set_property("volume", max(0.0, min(1.0, value)))

    def get_volume(self) -> float:
        return self.playbin.get_property("volume")

    def seek(self, seconds: float):
        self.playbin.seek_simple(
            Gst.Format.TIME, Gst.SeekFlags.FLUSH | Gst.SeekFlags.KEY_UNIT, int(seconds * Gst.SECOND)
        )

    def get_position(self) -> float:
        """Position actuelle en secondes, ou 0 si indisponible."""
        ok, pos = self.playbin.query_position(Gst.Format.TIME)
        return pos / Gst.SECOND if ok else 0.0

    def get_duration(self) -> float:
        ok, dur = self.playbin.query_duration(Gst.Format.TIME)
        if ok:
            self._duration = dur / Gst.SECOND
            return self._duration
        return self._duration

    def is_playing(self) -> bool:
        _, state, _ = self.playbin.get_state(0)
        return state == Gst.State.PLAYING

    # ------------------------------------------------------------------
    # Bus GStreamer
    # ------------------------------------------------------------------

    def _on_bus_message(self, bus, message):
        t = message.type
        if t == Gst.MessageType.EOS:
            self.emit("eos")
        elif t == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            self.emit("error", err.message)
        elif t == Gst.MessageType.DURATION_CHANGED:
            dur = self.get_duration()
            if dur:
                self.emit("duration-changed", int(dur))
        elif t == Gst.MessageType.STATE_CHANGED:
            if message.src == self.playbin:
                old, new, pending = message.parse_state_changed()
                if new == Gst.State.PLAYING:
                    self.emit("state-changed", "playing")
                elif new == Gst.State.PAUSED:
                    self.emit("state-changed", "paused")