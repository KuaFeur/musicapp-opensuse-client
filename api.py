#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
api.py — Client HTTP pour le serveur musicapp (app.py).

Enveloppe toutes les routes /api/... exposées par le serveur aiohttp et
gère la session (cookie) comme le ferait un navigateur.
"""

from __future__ import annotations

import requests


class ApiError(Exception):
    """Erreur renvoyée par le serveur (avec message si disponible)."""

    def __init__(self, message: str, status: int = 0):
        super().__init__(message)
        self.message = message
        self.status = status


class MusicApiClient:
    """
    Client synchrone (utilisé depuis un thread de fond, jamais depuis le
    thread principal GTK) vers le serveur musicapp.
    """

    def __init__(self):
        self.base_url: str = ""
        self.session = requests.Session()
        self.current_user: dict | None = None

    # ------------------------------------------------------------------
    # Connexion au serveur
    # ------------------------------------------------------------------

    def configure(self, host: str, port: str | int):
        host = host.strip()
        self.base_url = f"http://{host}:{port}"

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def test_connection(self, timeout: float = 5.0):
        """Vérifie que le serveur répond (utilisé lors de l'écran de connexion)."""
        resp = self.session.get(self._url("/"), timeout=timeout)
        resp.raise_for_status()

    # ------------------------------------------------------------------
    # Aides internes
    # ------------------------------------------------------------------

    def _handle(self, resp: requests.Response):
        if resp.ok:
            if resp.content:
                try:
                    return resp.json()
                except ValueError:
                    return {}
            return {}
        message = "Erreur serveur."
        try:
            data = resp.json()
            message = data.get("error", message)
        except ValueError:
            pass
        raise ApiError(message, resp.status_code)

    def get(self, path: str, params: dict | None = None):
        resp = self.session.get(self._url(path), params=params, timeout=15)
        return self._handle(resp)

    def post(self, path: str, json: dict | None = None):
        resp = self.session.post(self._url(path), json=json or {}, timeout=15)
        return self._handle(resp)

    def delete(self, path: str):
        resp = self.session.delete(self._url(path), timeout=15)
        return self._handle(resp)

    # ------------------------------------------------------------------
    # Recherche / métadonnées / stream
    # ------------------------------------------------------------------

    def search(self, query: str, search_type: str = "all") -> dict:
        return self.get("/api/search", {"q": query, "type": search_type})

    def get_album(self, browse_id: str) -> dict:
        return self.get(f"/api/album/{browse_id}")

    def get_artist(self, browse_id: str) -> dict:
        return self.get(f"/api/artist/{browse_id}")

    def get_artist_all_tracks(self, browse_id: str) -> dict:
        return self.get(f"/api/artist/{browse_id}/all-tracks")

    def get_track(self, video_id: str) -> dict:
        return self.get(f"/api/track/{video_id}")

    def stream_url(self, video_id: str) -> str:
        """URL directe du flux audio, à donner telle quelle au lecteur (GStreamer)."""
        return self._url(f"/api/stream/{video_id}")

    def share_create(self, video_id: str) -> dict:
        return self.post("/api/share", {"id": video_id})

    # ------------------------------------------------------------------
    # File d'attente
    # ------------------------------------------------------------------

    def queue_get(self) -> dict:
        return self.get("/api/queue")

    def queue_add(self, track: dict, mode: str = "end") -> dict:
        body = {
            "id": track.get("id"),
            "title": track.get("title", ""),
            "artist": track.get("artist", ""),
            "thumbnail": track.get("thumbnail", ""),
            "mode": mode,
        }
        return self.post("/api/queue", body)

    def queue_advance(self) -> dict:
        return self.post("/api/queue/advance")

    def queue_advance_random(self) -> dict:
        """Retire un élément aléatoire de la file d'attente et le retourne
        (équivalent 'aléatoire' de queue_advance). Pas d'endpoint dédié
        côté serveur : on pioche un index au hasard et on le supprime."""
        import random
        data = self.queue_get()
        queue = data.get("queue", [])
        if not queue:
            return {"track": None}
        index = random.randrange(len(queue))
        track = queue[index]
        self.queue_delete(index)
        return {"track": track}

    def queue_delete(self, index: int) -> dict:
        return self.delete(f"/api/queue/{index}")

    def queue_clear(self):
        """Vide entièrement la file d'attente. Pas d'endpoint dédié côté
        serveur : on supprime le premier élément en boucle jusqu'à ce que
        la file soit vide."""
        while True:
            data = self.queue_get()
            queue = data.get("queue", [])
            if not queue:
                break
            self.queue_delete(0)

    def queue_reorder(self, from_index: int, to_index: int) -> dict:
        """Déplace un élément de la file d'attente. Pas d'endpoint dédié
        côté serveur : on récupère la file, on réordonne localement, puis
        on la reconstruit (delete-all + re-add dans le nouvel ordre)."""
        data = self.queue_get()
        queue = list(data.get("queue", []))
        if not (0 <= from_index < len(queue)) or not (0 <= to_index < len(queue)):
            return {"queue": queue}
        track = queue.pop(from_index)
        queue.insert(to_index, track)
        for i in range(len(data.get("queue", []))):
            self.queue_delete(0)
        for track in queue:
            self.queue_add(track)
        return {"queue": queue}

    # ------------------------------------------------------------------
    # Comptes / sessions
    # ------------------------------------------------------------------

    def register(self, username: str, password: str) -> dict:
        data = self.post("/api/register", {"username": username, "password": password})
        self.current_user = data
        return data

    def login(self, username: str, password: str) -> dict:
        data = self.post("/api/login", {"username": username, "password": password})
        self.current_user = data
        return data

    def logout(self):
        try:
            self.post("/api/logout")
        finally:
            self.current_user = None

    def me(self) -> dict | None:
        try:
            data = self.get("/api/me")
            self.current_user = data
            return data
        except ApiError as exc:
            if exc.status == 401:
                self.current_user = None
                return None
            raise

    # ------------------------------------------------------------------
    # Playlists
    # ------------------------------------------------------------------

    def playlists_get(self) -> dict:
        return self.get("/api/playlists")

    def playlist_create(self, name: str) -> dict:
        return self.post("/api/playlists", {"name": name})

    def playlist_detail(self, playlist_id: int) -> dict:
        return self.get(f"/api/playlists/{playlist_id}")

    def playlist_delete(self, playlist_id: int):
        return self.delete(f"/api/playlists/{playlist_id}")

    def playlist_add_track(self, playlist_id: int, track: dict):
        body = {
            "id": track.get("id"),
            "title": track.get("title", ""),
            "artist": track.get("artist", ""),
            "thumbnail": track.get("thumbnail", ""),
        }
        return self.post(f"/api/playlists/{playlist_id}/tracks", body)

    def playlist_remove_track(self, playlist_id: int, track_id: str):
        return self.delete(f"/api/playlists/{playlist_id}/tracks/{track_id}")
