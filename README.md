# MusicApp — client GTK (openSUSE)

Client graphique natif GTK4/libadwaita pour ton serveur `app.py`. Reprend tout
ce qui existe côté web : recherche (morceaux/albums/artistes), lecture audio,
file d'attente, comptes, playlists.

## 1. Installer les dépendances système (openSUSE)

```bash
sudo zypper install python3-gobject python3-gobject-Gdk \
    gtk4 libadwaita gobject-introspection-devel \
    gstreamer gstreamer-plugins-base gstreamer-plugins-good \
    gstreamer-plugins-bad gstreamer-plugins-ugly \
    typelib-1_0-Gtk-4_0 typelib-1_0-Adw-1
```

Si `libadwaita`/`typelib-1_0-Adw-1` n'existe pas sous ce nom exact sur ta
version d'openSUSE (Tumbleweed vs Leap), cherche avec :

```bash
zypper se -s adwaita gtk4 gstreamer-plugins
```

## 2. Installer les dépendances Python

```bash
cd musicapp-gtk-flat
pip install -r requirements.txt --break-system-packages
```

Tous les fichiers sont à plat dans ce dossier (pas de sous-dossier de
modules) — lance simplement `main.py` depuis ce même dossier.

(`PyGObject` peut aussi venir du paquet système `python3-gobject` — dans ce
cas tu peux retirer `PyGObject` de `requirements.txt` et n'installer que
`requests` via pip.)

## 3. Lancer l'application

```bash
python3 main.py
```

Au démarrage, l'app se connecte automatiquement à `music.linkua.me:80`
(pas d'écran de connexion — l'adresse est fixée dans `main_window.py`, via
`DEFAULT_HOST`/`DEFAULT_PORT`). En cas d'échec, un bouton "Réessayer"
s'affiche. Une fois connecté, tu retrouves :

- **Accueil**
- **Rechercher** — morceaux / albums / artistes, avec ouverture du détail
  d'un album ou d'un artiste
- **File d'attente** — ajout, lecture, suppression, "morceau suivant"
- **Playlists** — création, ajout/retrait de morceaux
- **Compte** — connexion / inscription / déconnexion, et mise à jour du
  client

La barre de lecture en bas (lecture/pause, suivant, progression, volume)
reste visible dans toute l'app.

## Rich Presence Discord

Si Discord est lancé sur la machine, l'app affiche automatiquement le
morceau en cours de lecture (titre, artiste, état lecture/pause) en Rich
Presence. Ça repose sur `pypresence`, qui parle en IPC local au client
Discord — aucune configuration n'est nécessaire, et si Discord n'est pas
lancé ou que `pypresence` n'est pas installé, l'app fonctionne normalement
sans RPC.

Le client Discord utilisé par défaut (`discord_rpc.DEFAULT_CLIENT_ID`) peut
être remplacé par le tien, créé sur
https://discord.com/developers/applications, si tu veux personnaliser les
images affichées (`large_image`/`small_image` dans l'onglet "Rich
Presence").

## Mettre à jour le client

Au démarrage, l'app vérifie silencieusement le dernier commit de la branche
`main` du dépôt
[KuaFeur/musicapp-opensuse-client](https://github.com/KuaFeur/musicapp-opensuse-client)
et, si une nouvelle version est disponible, la télécharge et l'installe
automatiquement (toast de notification, aucune action requise). Un
redémarrage manuel de l'app est nécessaire pour que les changements
prennent effet. Si la vérification échoue (pas de réseau, GitHub
injoignable), l'échec est silencieux et n'affecte pas le démarrage.

Le bouton **Mettre à jour** dans l'onglet **Compte** permet aussi de
déclencher cette vérification manuellement à tout moment. Les fichiers
remplacés sont sauvegardés dans `.backup_update/` avant écrasement.

## Notes techniques

- Le flux audio est lu directement depuis `/api/stream/{id}` via GStreamer
  (`playbin`), sans téléchargement intermédiaire.
- L'authentification utilise les cookies de session du serveur (comme un
  navigateur), stockés dans la session `requests`.
- Fichiers principaux : `api.py` (client HTTP), `player.py` (GStreamer),
  `main_window.py` (assemblage UI), `discord_rpc.py` (Rich Presence),
  `updater.py` (mise à jour depuis GitHub).
