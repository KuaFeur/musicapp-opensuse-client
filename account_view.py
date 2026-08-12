#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
account_view.py — Vue compte : connexion, création de compte, déconnexion.
"""

from __future__ import annotations

import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib  # noqa: E402

import updater


class AccountView(Gtk.Box):
    def __init__(self, api, on_auth_changed):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.api = api
        self.on_auth_changed = on_auth_changed
        self._remote_check = None

        self.stack = Gtk.Stack()
        self.stack.set_vexpand(True)
        self.append(self.stack)

        # --- Connecté ---
        self.logged_in_page = Adw.StatusPage(icon_name="avatar-default-symbolic")
        logged_in_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        logged_in_box.set_halign(Gtk.Align.CENTER)

        logout_btn = Gtk.Button(label="Se déconnecter")
        logout_btn.add_css_class("destructive-action")
        logout_btn.add_css_class("pill")
        logout_btn.set_halign(Gtk.Align.CENTER)
        logout_btn.connect("clicked", self._on_logout)
        logged_in_box.append(logout_btn)

        logged_in_box.append(self._build_update_section())

        self.logged_in_page.set_child(logged_in_box)
        self.stack.add_named(self.logged_in_page, "logged-in")

        # --- Formulaire connexion/inscription ---
        form_clamp = Adw.Clamp(maximum_size=380)
        self.stack.add_named(form_clamp, "form")

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        box.set_valign(Gtk.Align.CENTER)
        box.set_margin_top(24)
        box.set_margin_bottom(24)
        box.set_margin_start(24)
        box.set_margin_end(24)
        form_clamp.set_child(box)

        title = Gtk.Label(label="Compte")
        title.add_css_class("title-1")
        box.append(title)

        group = Adw.PreferencesGroup()
        box.append(group)

        self.username_row = Adw.EntryRow(title="Pseudo")
        group.add(self.username_row)

        self.password_row = Adw.PasswordEntryRow(title="Mot de passe")
        group.add(self.password_row)

        self.status_label = Gtk.Label(label="")
        self.status_label.add_css_class("error")
        self.status_label.set_wrap(True)
        self.status_label.set_visible(False)
        box.append(self.status_label)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8, halign=Gtk.Align.CENTER)
        box.append(btn_box)

        self.login_btn = Gtk.Button(label="Se connecter")
        self.login_btn.add_css_class("suggested-action")
        self.login_btn.add_css_class("pill")
        self.login_btn.connect("clicked", self._on_login)
        btn_box.append(self.login_btn)

        self.register_btn = Gtk.Button(label="Créer un compte")
        self.register_btn.add_css_class("pill")
        self.register_btn.connect("clicked", self._on_register)
        btn_box.append(self.register_btn)

        self.spinner = Gtk.Spinner()
        box.append(self.spinner)

        separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        separator.set_margin_top(10)
        separator.set_margin_bottom(10)
        box.append(separator)
        box.append(self._build_update_section())

    def _build_update_section(self) -> Gtk.Box:
        """Bloc 'Mise à jour' : vérifie et applique les mises à jour du
        client depuis le dépôt GitHub. Partagé entre l'écran connecté et
        le formulaire de connexion."""
        section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        section.set_halign(Gtk.Align.CENTER)

        self.update_status_label = Gtk.Label(label="")
        self.update_status_label.add_css_class("dim-label")
        self.update_status_label.add_css_class("caption")
        self.update_status_label.set_wrap(True)
        self.update_status_label.set_justify(Gtk.Justification.CENTER)
        self.update_status_label.set_visible(False)
        section.append(self.update_status_label)

        update_btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8, halign=Gtk.Align.CENTER)
        section.append(update_btn_box)

        self.check_update_btn = Gtk.Button(label="Mettre à jour")
        self.check_update_btn.add_css_class("pill")
        self.check_update_btn.set_tooltip_text("Rechercher et installer les mises à jour du client")
        self.check_update_btn.connect("clicked", self._on_check_update)
        update_btn_box.append(self.check_update_btn)

        self.update_spinner = Gtk.Spinner()
        update_btn_box.append(self.update_spinner)

        return section

    def _set_update_busy(self, busy: bool):
        self.check_update_btn.set_sensitive(not busy)
        if busy:
            self.update_spinner.start()
        else:
            self.update_spinner.stop()

    def _show_update_status(self, message: str):
        self.update_status_label.set_text(message)
        self.update_status_label.set_visible(True)

    def _on_check_update(self, *_args):
        self._set_update_busy(True)
        self._show_update_status("Recherche de mise à jour…")

        def worker():
            try:
                result = updater.check_for_update()
                GLib.idle_add(self._on_check_result, result)
            except Exception as exc:
                message = getattr(exc, "message", str(exc))
                GLib.idle_add(self._on_update_error, message)

        threading.Thread(target=worker, daemon=True).start()

    def _on_check_result(self, result: dict):
        self._set_update_busy(False)
        if not result["update_available"]:
            self._show_update_status("Le client est déjà à jour.")
            return False

        remote = result["remote"]
        short_sha = remote["sha"][:7]
        detail = f" — {remote['message']}" if remote.get("message") else ""
        self._show_update_status(f"Mise à jour disponible ({short_sha}){detail}. Installation…")
        self._apply_update(remote["sha"])
        return False

    def _apply_update(self, remote_sha: str):
        self._set_update_busy(True)

        def worker():
            try:
                updated_files = updater.apply_update(remote_sha)
                GLib.idle_add(self._on_update_applied, updated_files)
            except Exception as exc:
                message = getattr(exc, "message", str(exc))
                GLib.idle_add(self._on_update_error, message)

        threading.Thread(target=worker, daemon=True).start()

    def _on_update_applied(self, updated_files: list):
        self._set_update_busy(False)
        if updated_files:
            self._show_update_status(
                f"Mise à jour installée ({len(updated_files)} fichier(s)). "
                "Redémarre l'application pour l'appliquer."
            )
        else:
            self._show_update_status("Aucun fichier à mettre à jour.")
        return False

    def _on_update_error(self, message: str):
        self._set_update_busy(False)
        self._show_update_status(f"Erreur de mise à jour : {message}")
        return False

    def refresh(self):
        user = self.api.current_user
        if user:
            self.logged_in_page.set_title(f"Connecté en tant que {user.get('username', '')}")
            self.stack.set_visible_child_name("logged-in")
        else:
            self.stack.set_visible_child_name("form")

    def _set_busy(self, busy):
        self.login_btn.set_sensitive(not busy)
        self.register_btn.set_sensitive(not busy)
        if busy:
            self.spinner.start()
        else:
            self.spinner.stop()

    def _show_error(self, message):
        self.status_label.set_text(message)
        self.status_label.set_visible(True)

    def _on_login(self, *_args):
        self._do_auth(self.api.login)

    def _on_register(self, *_args):
        self._do_auth(self.api.register)

    def _do_auth(self, method):
        username = self.username_row.get_text().strip()
        password = self.password_row.get_text()
        if not username or not password:
            self._show_error("Pseudo et mot de passe requis.")
            return
        self.status_label.set_visible(False)
        self._set_busy(True)

        def worker():
            try:
                method(username, password)
                GLib.idle_add(self._on_success)
            except Exception as exc:
                message = getattr(exc, "message", str(exc))
                GLib.idle_add(self._on_failure, message)

        threading.Thread(target=worker, daemon=True).start()

    def _on_success(self):
        self._set_busy(False)
        self.username_row.set_text("")
        self.password_row.set_text("")
        self.refresh()
        self.on_auth_changed()
        return False

    def _on_failure(self, message):
        self._set_busy(False)
        self._show_error(message)
        return False

    def _on_logout(self, *_args):
        def worker():
            try:
                self.api.logout()
            except Exception:
                pass
            GLib.idle_add(self._on_success)

        threading.Thread(target=worker, daemon=True).start()
