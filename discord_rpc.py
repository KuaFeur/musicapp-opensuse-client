#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
discord_rpc.py — Rich Presence Discord affichant le morceau en cours de
lecture. Utilise pypresence (protocole IPC local vers le client Discord).

Conçu pour être tolérant aux pannes : si Discord n'est pas lancé, si
pypresence n'est pas installé, ou si l'IPC échoue, l'app continue de
fonctionner normalement (le RPC est simplement désactivé).
"""

from __future__ import annotations

import glob
import os
import threading
import time

try:
    from pypresence import Presence
    from pypresence.exceptions import PyPresenceException
except ImportError:  # pypresence non installé
    Presence = None
    PyPresenceException = Exception


# Identifiant d'application Discord dédié à MusicApp. À remplacer par le
# tien si tu as créé/veux créer ta propre application sur
# https://discord.com/developers/applications (onglet "Rich Presence" pour
# les assets d'image large_image/small_image).
DEFAULT_CLIENT_ID = "1503878289939234928"

_RECONNECT_DELAY = 15  # secondes entre deux tentatives de reconnexion

# pypresence cherche le socket discord-ipc-N uniquement dans
# $XDG_RUNTIME_DIR (ou /tmp en repli). Sur Linux, si Discord tourne en
# Flatpak ou Snap, le socket réel est isolé dans un sous-dossier propre
# au sandbox et n'apparaît jamais à cet emplacement standard. On liste
# ici tous les emplacements connus, du plus courant au plus rare.
def _candidate_ipc_dirs() -> list[str]:
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
    return [
        runtime_dir,                                                  # install native (rpm/deb/tar)
        os.path.join(runtime_dir, "app", "com.discordapp.Discord"),   # Flatpak stable
        os.path.join(runtime_dir, "app", "com.discordapp.DiscordCanary"),
        os.path.join(runtime_dir, "app", "com.discordapp.DiscordPTB"),
        os.path.join(runtime_dir, "snap.discord"),                    # Snap
        "/tmp",                                                       # repli historique pypresence
    ]


def _find_discord_ipc_dir() -> str | None:
    """Retourne le dossier contenant un socket discord-ipc-N valide, ou None."""
    for directory in _candidate_ipc_dirs():
        if glob.glob(os.path.join(directory, "discord-ipc-*")):
            return directory
    return None


class DiscordRPC:
    """
    Gère la connexion Discord IPC dans un thread dédié et expose des
    méthodes simples pour mettre à jour ou effacer la présence.

    Toutes les méthodes publiques sont thread-safe et non bloquantes : le
    travail réseau/IPC réel est délégué à un thread de fond.
    """

    def __init__(self, client_id: str = DEFAULT_CLIENT_ID):
        self.client_id = client_id
        self.enabled = Presence is not None
        self._rpc: "Presence | None" = None
        self._connected = False
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._pending_activity: dict | None = None
        self._activity_event = threading.Event()
        self._start_ts = None
        self._thread = None

        if self.enabled:
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()

    # ------------------------------------------------------------------
    # API publique
    # ------------------------------------------------------------------

    @staticmethod
    def _large_image(track: dict) -> str:
        """Retourne l'URL d'image pour large_image.

        Discord Rich Presence accepte les URLs externes via le préfixe
        ``mp:external/<hash>/<url>`` mais pypresence peut passer l'URL
        directement — Discord la proxifie automatiquement si elle est
        publique et commence par https://.  On essaie donc d'abord la
        thumbnail du track ; si elle est absente on tombe sur le logo
        statique déclaré dans les assets de l'app Discord.
        """
        thumbnail = (track.get("thumbnail") or "").strip()
        if thumbnail.startswith("https://"):
            return thumbnail
        return "musicapp_logo"

    def update_track(self, track: dict, position_seconds: float = 0.0, duration_seconds: float = 0.0):
        """Met à jour la présence avec le morceau en cours de lecture."""
        if not self.enabled:
            return
        now = time.time()
        large_img = self._large_image(track)
        activity = {
            "details": (track.get("title") or "Morceau inconnu")[:128],
            "state": (track.get("artist") or "Artiste inconnu")[:128],
            "large_image": large_img,
            "large_text": track.get("title") or "MusicApp",
            "small_image": "play",
            "small_text": "En lecture",
        }
        if duration_seconds and duration_seconds > 0:
            start = now - max(0.0, position_seconds)
            activity["start"] = int(start)
            activity["end"] = int(start + duration_seconds)
        else:
            activity["start"] = int(now - max(0.0, position_seconds))

        with self._lock:
            self._pending_activity = ("update", activity)
        self._activity_event.set()

    def set_paused(self, track: dict):
        """Affiche l'état pause pour le morceau courant."""
        if not self.enabled:
            return
        large_img = self._large_image(track)
        activity = {
            "details": (track.get("title") or "Morceau inconnu")[:128],
            "state": (track.get("artist") or "Artiste inconnu")[:128],
            "large_image": large_img,
            "large_text": track.get("title") or "MusicApp",
            "small_image": "pause",
            "small_text": "En pause",
        }
        with self._lock:
            self._pending_activity = ("update", activity)
        self._activity_event.set()

    def clear(self):
        """Efface la présence (ex : app fermée, déconnexion du serveur)."""
        if not self.enabled:
            return
        with self._lock:
            self._pending_activity = ("clear", None)
        self._activity_event.set()

    def shutdown(self):
        """Arrête proprement le thread RPC."""
        self._stop.set()
        self._activity_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2)

    # ------------------------------------------------------------------
    # Boucle interne
    # ------------------------------------------------------------------

    def _connect(self) -> bool:
        ipc_dir = _find_discord_ipc_dir()
        if ipc_dir is None:
            # Aucun socket discord-ipc-* trouvé nulle part : Discord
            # n'est probablement pas lancé. On ne tente même pas la
            # connexion pour éviter une exception pypresence bruyante.
            self._rpc = None
            self._connected = False
            return False

        # pypresence lit XDG_RUNTIME_DIR au moment de connect(), donc on
        # le pointe temporairement vers le dossier où le socket a été
        # trouvé (utile pour Flatpak/Snap dont le socket est isolé),
        # puis on restaure la valeur d'origine pour ne pas perturber le
        # reste de l'application.
        original_runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
        os.environ["XDG_RUNTIME_DIR"] = ipc_dir
        try:
            self._rpc = Presence(self.client_id)
            self._rpc.connect()
            self._connected = True
            return True
        except Exception:
            self._rpc = None
            self._connected = False
            return False
        finally:
            if original_runtime_dir is None:
                os.environ.pop("XDG_RUNTIME_DIR", None)
            else:
                os.environ["XDG_RUNTIME_DIR"] = original_runtime_dir

    def _run(self):
        while not self._stop.is_set():
            if not self._connected:
                if not self._connect():
                    # Discord probablement fermé : on retente plus tard,
                    # sans bloquer le reste de l'app.
                    self._stop.wait(_RECONNECT_DELAY)
                    continue

            triggered = self._activity_event.wait(timeout=15)
            self._activity_event.clear()
            if self._stop.is_set():
                break

            with self._lock:
                pending = self._pending_activity
                self._pending_activity = None

            if pending is None:
                # Pas de nouvelle activité : simple keep-alive périodique.
                continue

            kind, activity = pending
            try:
                if kind == "clear":
                    self._rpc.clear()
                else:
                    self._rpc.update(**activity)
            except Exception:
                # IPC cassé (Discord fermé entre-temps, etc.) : on force
                # une reconnexion au prochain tour.
                self._connected = False
                self._rpc = None

        if self._rpc is not None:
            try:
                self._rpc.close()
            except Exception:
                pass