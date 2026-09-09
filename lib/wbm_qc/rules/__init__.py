# -*- coding: utf-8 -*-
"""Auto-decouverte des regles de controle qualite.

Tout module nomme rule_*.py depose dans ce dossier est importe
automatiquement au chargement du package. Chaque module doit definir
une classe heritant de wbm_qc.registry.QCRule et decoree avec
@register_rule pour etre prise en compte par le moteur.

=> Pour ajouter un nouveau controle : creer un fichier
   rule_mon_controle.py dans ce dossier, aucune autre modification
   n'est necessaire (c'est le point cle de la modularite).
"""

import os
import pkgutil
import importlib

_package_dir = os.path.dirname(__file__)

for _, _module_name, _is_pkg in pkgutil.iter_modules([_package_dir]):
    if _module_name.startswith("rule_"):
        importlib.import_module("wbm_qc.rules." + _module_name)
