# -*- coding: utf-8 -*-
"""Fonctions utilitaires partagees entre plusieurs regles de controle."""

import re

# Convention WBM : "{18 chiffres numero de projet}_{YYYYMMDD date}[...].rvt"
_FILENAME_PATTERN = re.compile(r"^(\d{18})_(\d{8})")


def parse_project_filename(doc):
    """Extrait (numero_projet, date_yyyymmdd) du nom du document actif.

    Retourne (None, None) si le nom du fichier ne respecte pas la
    convention "{18 chiffres}_{YYYYMMDD}".
    """
    title = doc.Title or ""
    match = _FILENAME_PATTERN.match(title)
    if not match:
        return None, None
    return match.group(1), match.group(2)
