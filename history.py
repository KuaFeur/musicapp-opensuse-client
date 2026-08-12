#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
history.py — Historique d'écoute local, persisté en JSON dans le dossier de
config utilisateur (indépendant du compte serveur : c'est un historique par
machine/installation, pas synchronisé).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

MAX_HISTORY = 30

_CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "musicapp-gtk"
_HISTORY_FILE = _CONFIG_DIR / "history.json"


def _load() -> list[dict]:
    try:
        with open(_HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
    except (FileNotFoundError, ValueError, OSError):
        pass
    return []


def _save(entries: list[dict]):
    try:
        _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(_HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False)
    except OSError:
        pass  # historique best-effort : jamais bloquant pour la lecture


def add_track(track: dict):
    """Ajoute un morceau en tête d'historique (déduplication par id)."""
    track_id = track.get("id")
    if not track_id:
        return
    entries = _load()
    entries = [e for e in entries if e.get("id") != track_id]
    entries.insert(0, {
        "id": track_id,
        "title": track.get("title", ""),
        "artist": track.get("artist", ""),
        "thumbnail": track.get("thumbnail", ""),
    })
    entries = entries[:MAX_HISTORY]
    _save(entries)


def get_recent(limit: int = 10) -> list[dict]:
    return _load()[:limit]


def clear():
    _save([])
