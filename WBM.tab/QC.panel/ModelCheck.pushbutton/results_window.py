# -*- coding: utf-8 -*-
"""Code-behind de la fenetre de resultats du controle modele.

L'interface (ResultsWindow.xaml) reste entierement definie en XAML,
conformement a la regle du projet : ce module ne fait que la piloter
(donnees, filtres, actions sur clic).
"""

import os
import io
import csv

from System.Collections.Generic import List
from System.Windows.Media import Color, SolidColorBrush

from Autodesk.Revit.DB import ElementId

from pyrevit import forms

from wbm_qc.models import SEVERITY_ERROR, SEVERITY_INFO, SEVERITY_WARNING
from wbm_qc.engine import run_checks

_SEVERITY_COLORS = {
    SEVERITY_ERROR: Color.FromRgb(0xDC, 0x26, 0x26),
    SEVERITY_WARNING: Color.FromRgb(0xD9, 0x77, 0x06),
    SEVERITY_INFO: Color.FromRgb(0x08, 0x91, 0xB2),
}
_DEFAULT_SEVERITY_COLOR = Color.FromRgb(0x64, 0x74, 0x8B)

_ALL_LABEL = "(Tous)"


class IssueRowVM(object):
    """Objet expose au binding WPF pour une ligne de resultat."""

    def __init__(self, issue):
        self.issue = issue
        self.Severity = issue.severity
        self.Category = issue.category
        self.Rule = issue.rule_name
        self.Description = issue.description
        self.ElementIdText = (
            str(issue.element_id.IntegerValue) if issue.element_id else "-"
        )
        self.SeverityBrush = SolidColorBrush(
            _SEVERITY_COLORS.get(issue.severity, _DEFAULT_SEVERITY_COLOR)
        )


class QCResultsWindow(forms.WPFWindow):
    def __init__(self, xaml_file, doc, uidoc, api_runner, issues, rule_errors=None):
        forms.WPFWindow.__init__(self, xaml_file)
        self.doc = doc
        self.uidoc = uidoc
        self.api_runner = api_runner
        self.all_rows = []
        self._loading_filters = False
        self.load_issues(issues, rule_errors)

    # ------------------------------------------------------------------
    # Chargement / rafraichissement des donnees
    # ------------------------------------------------------------------
    def load_issues(self, issues, rule_errors=None):
        self.all_rows = [IssueRowVM(issue) for issue in issues]
        self._populate_filters()
        self._apply_filters()
        self._update_summary()
        self._update_status(rule_errors)

    def _populate_filters(self):
        self._loading_filters = True

        severities = sorted(set(row.Severity for row in self.all_rows))
        categories = sorted(set(row.Category for row in self.all_rows))

        self.cmb_severity.ItemsSource = [_ALL_LABEL] + severities
        self.cmb_severity.SelectedIndex = 0

        self.cmb_category.ItemsSource = [_ALL_LABEL] + categories
        self.cmb_category.SelectedIndex = 0

        self._loading_filters = False

    def _update_summary(self):
        self.lbl_error_count.Text = str(
            sum(1 for row in self.all_rows if row.Severity == SEVERITY_ERROR)
        )
        self.lbl_warning_count.Text = str(
            sum(1 for row in self.all_rows if row.Severity == SEVERITY_WARNING)
        )
        self.lbl_info_count.Text = str(
            sum(1 for row in self.all_rows if row.Severity == SEVERITY_INFO)
        )
        self.lbl_total_count.Text = str(len(self.all_rows))
        self.lbl_model_name.Text = "- {}".format(self.doc.Title) if self.doc else ""

    def _update_status(self, rule_errors):
        if rule_errors:
            self.lbl_status.Text = (
                "{} regle(s) de controle n'ont pas pu etre executees "
                "(voir la console de sortie pyRevit).".format(len(rule_errors))
            )
        else:
            self.lbl_status.Text = "Controle termine."

    # ------------------------------------------------------------------
    # Filtres (recherche texte + severite + categorie)
    # ------------------------------------------------------------------
    def _apply_filters(self):
        search = (self.txt_search.Text or "").strip().lower()
        severity = self.cmb_severity.SelectedItem
        category = self.cmb_category.SelectedItem

        rows = self.all_rows
        if severity and severity != _ALL_LABEL:
            rows = [row for row in rows if row.Severity == severity]
        if category and category != _ALL_LABEL:
            rows = [row for row in rows if row.Category == category]
        if search:
            rows = [
                row
                for row in rows
                if search in row.Description.lower()
                or search in row.Rule.lower()
                or search in row.Category.lower()
            ]

        self.grid_results.ItemsSource = rows

    def on_filter_changed(self, sender, args):
        if self._loading_filters:
            return
        self._apply_filters()

    # ------------------------------------------------------------------
    # Actions utilisateur
    # ------------------------------------------------------------------
    # Fenetre non modale : tout appel a l'API Revit passe par l'ExternalEvent
    # (voir wbm_numbering.revit_context).
    def on_show_click(self, sender, args):
        row = sender.Tag
        issue = row.issue if row else None

        if not issue or not issue.element_id:
            forms.alert("Aucun element Revit n'est associe a cette anomalie.")
            return

        element_id = issue.element_id
        self.api_runner.run(lambda uiapp: self._show_in_context(element_id))

    def _show_in_context(self, element_id):
        try:
            self.uidoc.Selection.SetElementIds(List[ElementId]([element_id]))
            self.uidoc.ShowElements(element_id)
        except Exception as ex:
            forms.alert("Impossible d'afficher l'element : {}".format(ex))

    def on_rerun_click(self, sender, args):
        self.lbl_status.Text = "Controle en cours..."
        self.api_runner.run(self._rerun_in_context)

    def _rerun_in_context(self, uiapp):
        issues, rule_errors = run_checks(self.doc)
        self.load_issues(issues, rule_errors)

    def on_export_click(self, sender, args):
        rows = self.grid_results.ItemsSource or self.all_rows
        if not rows:
            forms.alert("Aucune anomalie a exporter.")
            return

        dest = forms.save_file(file_ext="csv")
        if not dest:
            return

        with io.open(dest, "w", encoding="utf-8-sig", newline="") as csv_file:
            writer = csv.writer(csv_file, delimiter=";")
            writer.writerow(["Severite", "Categorie", "Regle", "Description", "Id"])
            for row in rows:
                writer.writerow(
                    [row.Severity, row.Category, row.Rule, row.Description, row.ElementIdText]
                )

        forms.alert("Export termine :\n{}".format(dest))

    def on_close_click(self, sender, args):
        self.Close()


def show_results_window(doc, uidoc, api_runner, issues, rule_errors=None):
    """Cree et affiche la fenetre de resultats (non modale)."""
    xaml_file = os.path.join(os.path.dirname(__file__), "ResultsWindow.xaml")
    window = QCResultsWindow(xaml_file, doc, uidoc, api_runner, issues, rule_errors)
    window.Show()
    return window
