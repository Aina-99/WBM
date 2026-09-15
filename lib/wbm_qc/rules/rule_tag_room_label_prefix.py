# -*- coding: utf-8 -*-
"""Controle : dans la famille de RoomTag utilisee, le parametre de
label "Unbounded Height" doit avoir le prefixe "LRH:" (correction
d'une faute de frappe historique : "LHR:").

Contrairement aux autres controles, celui-ci inspecte la configuration
du Label a l'interieur de la famille de tag elle-meme (parametre
Prefix/Suffix visible dans l'editeur de famille, boite de dialogue
"Modifier le label"). Cette information n'existe que dans le document
de la famille (Document.EditFamily), une operation couteuse : par
souci de performance, seul le premier RoomTag rencontre dans le modele
est controle (pas famille par famille), et une anomalie declenche une
remarque generale (non rattachee a un element precis) invitant a
verifier l'ensemble des familles de RoomTag utilisees.

Avertissement : l'API de composition des labels (classe Label /
LabelParameterOptions) est peu documentee et peut varier selon la
version de Revit. Ce controle est ecrit de maniere defensive mais
merite d'etre verifie sur un modele reel avant d'etre considere fiable
a 100%."""

from Autodesk.Revit.DB import BuiltInCategory, FilteredElementCollector

from wbm_qc.models import QCIssue, SEVERITY_ERROR
from wbm_qc.registry import QCRule, register_rule

_LABEL_PARAM_NAME = "Unbounded Height"
_REQUIRED_PREFIX = "LRH:"


def _get_param_display_name(family_doc, param_id):
    element = family_doc.GetElement(param_id)
    if element is not None and hasattr(element, "Name"):
        return element.Name

    try:
        from Autodesk.Revit.DB import BuiltInParameter, LabelUtils

        bip = BuiltInParameter(param_id.IntegerValue)
        return LabelUtils.GetLabelFor(bip)
    except Exception:
        return None


def _find_label_prefix(family_doc, param_name):
    from Autodesk.Revit.DB import Label

    labels = FilteredElementCollector(family_doc).OfClass(Label).ToElements()

    for label in labels:
        try:
            param_ids = label.GetLabelParameterIds()
        except Exception:
            continue

        for param_id in param_ids:
            name = _get_param_display_name(family_doc, param_id)
            if name != param_name:
                continue

            try:
                options = label.GetLabelParameterOptions(param_id)
                return options.Prefix
            except Exception:
                return None

    return None


@register_rule
class RoomTagLabelPrefixRule(QCRule):
    rule_id = "room_tag_label_prefix"
    name = "Prefixe du label 'Unbounded Height'"
    category = "Tags"
    severity = SEVERITY_ERROR
    description = "Le label '{}' doit utiliser le prefixe '{}'.".format(
        _LABEL_PARAM_NAME, _REQUIRED_PREFIX
    )

    def check(self, doc):
        room_tags = (
            FilteredElementCollector(doc)
            .OfCategory(BuiltInCategory.OST_RoomTags)
            .WhereElementIsNotElementType()
            .ToElements()
        )

        first_tag = next(iter(room_tags), None)
        if first_tag is None:
            return []

        symbol = doc.GetElement(first_tag.GetTypeId())
        family = getattr(symbol, "Family", None)
        if family is None or not family.IsEditable:
            return []

        family_doc = None
        try:
            family_doc = doc.EditFamily(family)
            prefix = _find_label_prefix(family_doc, _LABEL_PARAM_NAME)
        except Exception:
            return []
        finally:
            if family_doc is not None:
                try:
                    family_doc.Close(False)
                except Exception:
                    pass

        if prefix is None or prefix == _REQUIRED_PREFIX:
            return []

        return [
            QCIssue(
                element_id=None,
                category=self.category,
                rule_name=self.name,
                severity=self.severity,
                description=(
                    "Verifier le prefixe du label '{}' sur les familles "
                    "de RoomTag : '{}' trouve au lieu de '{}' (controle "
                    "sur '{}').".format(
                        _LABEL_PARAM_NAME, prefix, _REQUIRED_PREFIX, family.Name
                    )
                ),
            )
        ]
