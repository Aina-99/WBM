# -*- coding: utf-8 -*-
"""Registre des regles de controle qualite.

Chaque regle est une classe qui herite de QCRule et qui s'enregistre
elle-meme via le decorateur @register_rule. Pour ajouter un nouveau
controle il suffit de deposer un fichier rule_xxx.py dans le package
wbm_qc.rules : aucune modification du moteur n'est necessaire, c'est ce
qui rend le systeme modulable.
"""

_REGISTRY = []


class QCRule(object):
    """Classe de base pour une regle de controle qualite.

    A surcharger :
        rule_id     (str)  identifiant unique et stable de la regle
        name        (str)  libelle court affiche a l'utilisateur
        category    (str)  regroupement fonctionnel (Pieces, Vues, ...)
        severity    (str)  QCIssue.SEVERITY_ERROR / WARNING / INFO par defaut
        description (str)  explication de ce que controle la regle
        enabled     (bool) permet de desactiver une regle sans la supprimer

        check(self, doc) -> list[QCIssue]
    """

    rule_id = None
    name = "Regle sans nom"
    category = "General"
    severity = "Avertissement"
    description = ""
    enabled = True

    def check(self, doc):
        raise NotImplementedError(
            "La regle '{}' doit implementer check(doc)".format(self.rule_id)
        )


def register_rule(rule_cls):
    """Decorateur a appliquer sur chaque classe de regle pour l'enregistrer."""
    if not getattr(rule_cls, "rule_id", None):
        raise ValueError(
            "La regle '{}' doit definir un rule_id unique.".format(rule_cls.__name__)
        )
    _REGISTRY.append(rule_cls)
    return rule_cls


def get_registered_rules():
    """Retourne la liste des classes de regles enregistrees, triees par
    categorie puis par nom pour un affichage stable."""
    return sorted(_REGISTRY, key=lambda r: (r.category, r.name))


def clear_registry():
    """Utile pour les tests unitaires."""
    del _REGISTRY[:]
