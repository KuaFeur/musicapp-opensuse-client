#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
updater.py — Vérifie et applique les mises à jour du client depuis le dépôt
GitHub public (https://github.com/KuaFeur/musicapp-opensuse-client).

Le dépôt n'utilise pas de releases/tags : la "version" suivie est le SHA du
dernier commit de la branche `main`. Le module :
  1. interroge l'API GitHub pour connaître le dernier commit ;
  2. le compare au SHA stocké localement (fichier VERSION à côté du script) ;
  3. si une mise à jour est disponible, télécharge l'archive de la branche
     et remplace les fichiers .py à plat dans le dossier de l'app (celui où
     vit main.py), en sauvegardant les fichiers remplacés au cas où.

Toutes les fonctions réseau sont synchrones : à appeler depuis un thread de
fond, jamais depuis le thread principal GTK.
"""

from __future__ import annotations

import io
import os
import shutil
import zipfile
from pathlib import Path

import requests

REPO_OWNER = "KuaFeur"
REPO_NAME = "musicapp-opensuse-client"
REPO_BRANCH = "main"

API_LATEST_COMMIT = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/commits/{REPO_BRANCH}"
ARCHIVE_URL = f"https://github.com/{REPO_OWNER}/{REPO_NAME}/archive/refs/heads/{REPO_BRANCH}.zip"

# Dossier de l'app = celui contenant ce fichier (installation "à plat").
APP_DIR = Path(__file__).resolve().parent
VERSION_FILE = APP_DIR / "VERSION"

# On ne touche qu'aux fichiers Python et assets de premier niveau ; on ne
# remplace jamais requirements.txt/README.md pour ne pas surprendre
# l'utilisateur, ni le fichier VERSION lui-même (géré à part).
UPDATABLE_EXTENSIONS = {".py"}
IGNORE_FILES = {"VERSION"}


class UpdateError(Exception):
    pass


def get_local_version() -> str | None:
    """SHA du commit actuellement installé, ou None si inconnu (première
    installation depuis le zip, sans suivi de version)."""
    try:
        return VERSION_FILE.read_text(encoding="utf-8").strip() or None
    except FileNotFoundError:
        return None


def _set_local_version(sha: str):
    VERSION_FILE.write_text(sha, encoding="utf-8")


def get_remote_version(timeout: float = 10.0) -> dict:
    """Interroge GitHub pour le dernier commit de la branche suivie.
    Retourne {"sha": str, "message": str, "date": str}.
    """
    resp = requests.get(
        API_LATEST_COMMIT,
        headers={"Accept": "application/vnd.github+json"},
        timeout=timeout,
    )
    if not resp.ok:
        raise UpdateError(f"Impossible de contacter GitHub (HTTP {resp.status_code}).")
    data = resp.json()
    try:
        sha = data["sha"]
        commit = data.get("commit", {})
        message = commit.get("message", "").splitlines()[0] if commit.get("message") else ""
        date = commit.get("committer", {}).get("date", "") or commit.get("author", {}).get("date", "")
    except (KeyError, IndexError) as exc:
        raise UpdateError("Réponse GitHub inattendue.") from exc
    return {"sha": sha, "message": message, "date": date}


def check_for_update(timeout: float = 10.0) -> dict:
    """
    Retourne un dict décrivant l'état de mise à jour :
      {"update_available": bool, "local": str|None, "remote": dict}
    """
    remote = get_remote_version(timeout=timeout)
    local = get_local_version()
    return {
        "update_available": local is None or local != remote["sha"],
        "local": local,
        "remote": remote,
    }


def apply_update(remote_sha: str, timeout: float = 30.0) -> list[str]:
    """
    Télécharge l'archive de la branche suivie et remplace les fichiers .py
    à plat dans APP_DIR par leur nouvelle version. Retourne la liste des
    fichiers effectivement mis à jour.

    Les fichiers actuels sont sauvegardés dans APP_DIR/.backup_update avant
    remplacement (écrasé à chaque mise à jour), pour permettre un retour en
    arrière manuel en cas de souci.
    """
    resp = requests.get(ARCHIVE_URL, timeout=timeout)
    if not resp.ok:
        raise UpdateError(f"Téléchargement de l'archive échoué (HTTP {resp.status_code}).")

    try:
        archive = zipfile.ZipFile(io.BytesIO(resp.content))
    except zipfile.BadZipFile as exc:
        raise UpdateError("Archive téléchargée invalide.") from exc

    # L'archive GitHub contient un dossier racine du type
    # "musicapp-opensuse-client-main/". On ne garde que les fichiers de
    # premier niveau à l'intérieur de ce dossier (installation "à plat").
    names = archive.namelist()
    if not names:
        raise UpdateError("Archive vide.")
    root_prefix = names[0].split("/")[0] + "/"

    backup_dir = APP_DIR / ".backup_update"
    if backup_dir.exists():
        shutil.rmtree(backup_dir, ignore_errors=True)
    backup_dir.mkdir(parents=True, exist_ok=True)

    updated: list[str] = []

    for name in names:
        if not name.startswith(root_prefix):
            continue
        rel = name[len(root_prefix):]
        if not rel or "/" in rel:
            continue  # on ignore les sous-dossiers, installation à plat
        if rel in IGNORE_FILES:
            continue
        if Path(rel).suffix not in UPDATABLE_EXTENSIONS:
            continue

        new_content = archive.read(name)
        target = APP_DIR / rel

        if target.exists():
            shutil.copy2(target, backup_dir / rel)

        target.write_bytes(new_content)
        updated.append(rel)

    _set_local_version(remote_sha)
    return updated
