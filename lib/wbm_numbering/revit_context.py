# -*- coding: utf-8 -*-
"""Pont vers le contexte API Revit pour les fenetres non modales.

Une fenetre affichee avec Show() (non modale) survit a la fin du script
pyRevit : ses gestionnaires d'evenements s'executent donc HORS du
contexte API Revit. Y ouvrir une transaction, ou appeler PickObject, est
interdit par l'API -- Revit ne le detecte pas systematiquement, mais le
symptome quand il le detecte est un blocage suivi d'une "unrecoverable
error".

Tout appel a l'API Revit declenche depuis une telle fenetre doit donc
passer par un ExternalEvent : Revit rappelle alors le code dans un
contexte valide, sur le thread UI.
"""

from Autodesk.Revit.DB import FailureProcessingResult, FailureSeverity, IFailuresPreprocessor
from Autodesk.Revit.UI import ExternalEvent, IExternalEventHandler


class SwallowWarnings(IFailuresPreprocessor):
    """Supprime les avertissements non bloquants d'une transaction.

    Renumeroter sur place cree transitoirement des Mark en double (on
    ecrit un numero qu'un autre element porte encore le temps de la
    boucle) : sans ca Revit ouvre une boite modale par doublon au
    commit, ce qui fige l'application quand cette boite s'ouvre depuis
    une fenetre non modale. Seuls les avertissements sont absorbes, les
    erreurs bloquantes remontent normalement.

    A installer sur toute transaction lancee par ce module :
        options = t.GetFailureHandlingOptions()
        options.SetFailuresPreprocessor(SwallowWarnings())
        options.SetForcedModalHandling(False)
        t.SetFailureHandlingOptions(options)
    """

    def PreprocessFailures(self, accessor):
        for failure in accessor.GetFailureMessages():
            if failure.GetSeverity() == FailureSeverity.Warning:
                accessor.DeleteWarning(failure)
        return FailureProcessingResult.Continue


class _CallbackHandler(IExternalEventHandler):
    """Execute la fonction en attente dans un contexte API valide."""

    def __init__(self):
        self.callback = None
        self.error = None

    def Execute(self, uiapp):
        callback, self.callback = self.callback, None
        if callback is None:
            return
        # Une exception qui remonterait jusqu'a Revit ferait tomber
        # l'application : on la retient ici plutot que de la laisser filer.
        try:
            self.error = None
            callback(uiapp)
        except Exception as ex:
            self.error = ex

    def GetName(self):
        return "WBM Numbering external event"


class ApiContextRunner(object):
    """Execute une fonction dans le contexte API Revit.

    A construire depuis le script du bouton, jamais depuis la fenetre :
    ExternalEvent.Create exige lui aussi un contexte API valide.
    """

    def __init__(self):
        self._handler = _CallbackHandler()
        self._event = ExternalEvent.Create(self._handler)

    def run(self, callback):
        """Programme `callback(uiapp)` pour la prochaine disponibilite de
        Revit. L'appel est asynchrone : le retour ici ne signifie pas que
        le callback a deja tourne."""
        self._handler.callback = callback
        self._event.Raise()

    @property
    def last_error(self):
        return self._handler.error
