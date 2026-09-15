# -*- coding: utf-8 -*-
"""Code-behind de la fenetre de previsualisation Window Numbering (Beta).

L'interface (PreviewWindow.xaml) reste entierement definie en XAML,
conformement a la regle du projet : ce module ne fait que la piloter
(saisie prefixe, selection du repere d'entree dans la vue, calcul,
reordonnancement manuel par glisser-deposer, application des Mark). La
fenetre regroupe en une seule fenetre non modale ce qui etait
auparavant deux invites de saisie suivies d'une previsualisation
separee.
"""

import os

from System.Collections.Generic import List
from System.Windows import DragDrop, DragDropEffects, DataObject, SystemParameters
from System.Windows.Input import MouseButtonState
from System.Windows.Media import VisualTreeHelper
from System.Windows.Controls import DataGridRow, ScrollViewer
from System.Windows.Controls.Primitives import ButtonBase

from Autodesk.Revit.DB import ElementId
from Autodesk.Revit.UI.Selection import ObjectType
from Autodesk.Revit.Exceptions import OperationCanceledException

from pyrevit import forms

from wbm_numbering.door_numbering import element_point
from wbm_numbering.window_numbering import (
    building_center,
    build_order,
    assign_marks,
    apply_marks,
    collect_windows,
)

_DRAG_FORMAT = "WBM.WindowNumbering.Row"

# Hauteur de la zone haute/basse du tableau qui declenche le defilement
# automatique pendant un glisser-deposer.
_AUTOSCROLL_MARGIN = 32.0


def _describe_element(element):
    """Libelle court affiche pour l'element repere d'entree choisi."""
    try:
        category = element.Category.Name
    except Exception:
        category = "Element"
    return "{} (Id {})".format(category, element.Id.IntegerValue)


def _find_ancestor(element, ancestor_type):
    """Remonte l'arbre visuel WPF depuis `element` jusqu'a trouver une
    instance de `ancestor_type` (ou None)."""
    while element is not None and not isinstance(element, ancestor_type):
        element = VisualTreeHelper.GetParent(element)
    return element


def _find_descendant(element, descendant_type):
    """Premier descendant de `element` du type demande dans l'arbre visuel."""
    if element is None:
        return None
    if isinstance(element, descendant_type):
        return element
    for i in range(VisualTreeHelper.GetChildrenCount(element)):
        found = _find_descendant(VisualTreeHelper.GetChild(element, i), descendant_type)
        if found is not None:
            return found
    return None


class WindowRowVM(object):
    """Objet expose au binding WPF pour une ligne de la previsualisation."""

    def __init__(self, rank, window):
        self.window = window
        self.Rank = rank
        self.Mark = window.mark
        self.Id = window.element.Id.IntegerValue
        self.element_id = window.element.Id


class WindowNumberingPreviewWindow(forms.WPFWindow):
    def __init__(self, xaml_file, doc, uidoc, view, api_runner):
        forms.WPFWindow.__init__(self, xaml_file)
        self.doc = doc
        self.uidoc = uidoc
        self.view = view
        self.api_runner = api_runner
        self.level = view.GenLevel
        self.ordered_windows = []
        self.rows = []
        self.entry_point = None
        self._drag_candidate = None
        self._drag_start_pos = None
        self._scroll_viewer = None

        self.txt_prefix.Text = "T"
        self.lbl_status.Text = (
            "Selectionnez un repere d'entree dans la vue (optionnel), "
            "puis cliquez sur Calculer."
        )

    # ------------------------------------------------------------------
    # Selection du repere d'entree dans la vue
    # ------------------------------------------------------------------
    def on_pick_entry_click(self, sender, args):
        # PickObject exige un contexte API Revit, que cette fenetre non
        # modale n'a pas : on passe par l'ExternalEvent.
        self.Hide()
        self.api_runner.run(self._pick_entry_in_context)

    def _pick_entry_in_context(self, uiapp):
        try:
            reference = self.uidoc.Selection.PickObject(
                ObjectType.Element,
                "Selectionnez l'element repere d'entree dans la vue",
            )
        except OperationCanceledException:
            reference = None
        finally:
            self.Show()

        if reference is None:
            return

        element = self.doc.GetElement(reference.ElementId)
        point = element_point(element)
        if point is None:
            forms.alert("Position introuvable pour cet element, choisissez-en un autre.")
            return

        self.entry_point = point
        self.lbl_entry_marker.Text = _describe_element(element)
        self.lbl_status.Text = "Repere selectionne : {}. Cliquez sur Calculer.".format(
            self.lbl_entry_marker.Text
        )

    # ------------------------------------------------------------------
    # Calcul de la numerotation proposee
    # ------------------------------------------------------------------
    def on_calculate_click(self, sender, args):
        prefix = (self.txt_prefix.Text or "").strip()
        if not prefix:
            forms.alert("Merci de saisir un prefixe de numerotation.")
            return

        windows = collect_windows(self.doc, self.view)
        if not windows:
            self.ordered_windows = []
            self.rows = []
            self.grid_preview.ItemsSource = self.rows
            self.lbl_status.Text = "Aucune fenetre trouvee dans la vue active."
            return

        pivot = building_center(self.doc, self.view)
        ordered = build_order(windows, pivot, self.entry_point)
        assign_marks(ordered, prefix, self.level.Name)

        self.ordered_windows = ordered
        self._refresh_rows()

        status = "{} fenetre(s) a numeroter. Verifiez l'ordre avant de valider.".format(
            len(self.rows)
        )
        if pivot is None:
            status += (
                " Centre du batiment introuvable (aucun mur dans la vue, ni"
                " CropBox) : ordre non calcule."
            )
        elif self.entry_point is None:
            status += " Aucun repere d'entree selectionne : depart pris au nord."
        self.lbl_status.Text = status

    # ------------------------------------------------------------------
    # Reordonnancement manuel (glisser-deposer)
    # ------------------------------------------------------------------
    def _refresh_rows(self, select_index=None):
        self.rows = [WindowRowVM(i + 1, w) for i, w in enumerate(self.ordered_windows)]
        self.grid_preview.ItemsSource = self.rows
        if select_index is not None and 0 <= select_index < len(self.rows):
            self.grid_preview.SelectedItem = self.rows[select_index]
            self.grid_preview.ScrollIntoView(self.rows[select_index])

    def on_grid_preview_mouse_down(self, sender, args):
        self._drag_candidate = None
        if _find_ancestor(args.OriginalSource, ButtonBase) is not None:
            return
        row = _find_ancestor(args.OriginalSource, DataGridRow)
        if row is not None:
            self._drag_candidate = row.Item
            self._drag_start_pos = args.GetPosition(None)

    def on_grid_mouse_move(self, sender, args):
        if self._drag_candidate is None:
            return
        if args.LeftButton != MouseButtonState.Pressed:
            return
        pos = args.GetPosition(None)
        dx = abs(pos.X - self._drag_start_pos.X)
        dy = abs(pos.Y - self._drag_start_pos.Y)
        if (
            dx < SystemParameters.MinimumHorizontalDragDistance
            and dy < SystemParameters.MinimumVerticalDragDistance
        ):
            return
        data = DataObject(_DRAG_FORMAT, self._drag_candidate)
        self._drag_candidate = None
        DragDrop.DoDragDrop(self.grid_preview, data, DragDropEffects.Move)

    def on_grid_drag_over(self, sender, args):
        args.Effects = DragDropEffects.Move
        args.Handled = True
        # Le DataGrid WPF ne fait pas defiler la liste de lui-meme pendant un
        # glisser-deposer : sans ca, impossible de deplacer une ligne au-dela
        # de la portion visible du tableau.
        if self._scroll_viewer is None:
            self._scroll_viewer = _find_descendant(self.grid_preview, ScrollViewer)
        if self._scroll_viewer is None:
            return
        y = args.GetPosition(self.grid_preview).Y
        if y < _AUTOSCROLL_MARGIN:
            self._scroll_viewer.LineUp()
        elif y > self.grid_preview.ActualHeight - _AUTOSCROLL_MARGIN:
            self._scroll_viewer.LineDown()

    def on_grid_drop(self, sender, args):
        if not args.Data.GetDataPresent(_DRAG_FORMAT):
            return
        source_row = args.Data.GetData(_DRAG_FORMAT)
        target_dgrow = _find_ancestor(args.OriginalSource, DataGridRow)
        if target_dgrow is None:
            return
        target_row = target_dgrow.Item
        if source_row is target_row:
            return
        try:
            src_idx = self.ordered_windows.index(source_row.window)
            dst_idx = self.ordered_windows.index(target_row.window)
        except ValueError:
            return
        window = self.ordered_windows.pop(src_idx)
        self.ordered_windows.insert(dst_idx, window)
        prefix = (self.txt_prefix.Text or "").strip() or "T"
        assign_marks(self.ordered_windows, prefix, self.level.Name)
        self._refresh_rows(select_index=dst_idx)

    # ------------------------------------------------------------------
    # Selection / application
    # ------------------------------------------------------------------
    def on_row_selected(self, sender, args):
        row = self.grid_preview.SelectedItem
        if not row:
            return
        try:
            ids = List[ElementId]([row.element_id])
            self.uidoc.Selection.SetElementIds(ids)
        except Exception:
            pass

    def on_show_click(self, sender, args):
        row = sender.Tag
        if not row:
            return
        try:
            ids = List[ElementId]([row.element_id])
            self.uidoc.Selection.SetElementIds(ids)
            self.uidoc.ShowElements(row.element_id)
        except Exception:
            pass

    def on_apply_click(self, sender, args):
        if not self.ordered_windows:
            forms.alert("Rien a appliquer : calculez d'abord une previsualisation valide.")
            return
        confirmed = forms.alert(
            "Appliquer les {} valeurs Mark proposees au modele ?".format(
                len(self.ordered_windows)
            ),
            yes=True,
            no=True,
        )
        if not confirmed:
            return
        # Ouvrir une transaction depuis cette fenetre non modale ferait
        # planter Revit : l'ecriture passe par l'ExternalEvent.
        self.lbl_status.Text = "Application en cours..."
        self.api_runner.run(self._apply_in_context)

    def _apply_in_context(self, uiapp):
        try:
            apply_marks(self.doc, self.ordered_windows)
        except Exception as ex:
            self.lbl_status.Text = "Echec de l'application : {}".format(ex)
            forms.alert("Echec de l'application des Mark :\n{}".format(ex))
            return
        self.lbl_status.Text = "Mark applique sur {} fenetre(s).".format(
            len(self.ordered_windows)
        )

    def on_close_click(self, sender, args):
        self.Close()


def show_preview_window(doc, uidoc, view, api_runner):
    """Cree et affiche la fenetre de previsualisation (non modale)."""
    xaml_file = os.path.join(os.path.dirname(__file__), "PreviewWindow.xaml")
    window = WindowNumberingPreviewWindow(xaml_file, doc, uidoc, view, api_runner)
    window.Show()
    return window
