# -*- coding: utf-8 -*-
# pyRevit / IronPython 2.7
# Align Area Plan + Floor Plan viewports across sheets by a grid intersection anchor
# Example: align all matching Area Plans / Floor Plans so Grid 6 / Grid A lands at the same sheet point

import clr

from pyrevit import revit, forms
from Autodesk.Revit.DB import (
    FilteredElementCollector,
    Viewport,
    Grid,
    ViewType,
    ElementTransformUtils,
    XYZ,
    IntersectionResultArray,
    SetComparisonResult
)
from Autodesk.Revit.UI.Selection import ObjectType


doc = revit.doc
uidoc = revit.uidoc


# --------------------------------------------------
# Helpers
# --------------------------------------------------

ALLOWED_VIEW_TYPES = [ViewType.AreaPlan, ViewType.FloorPlan]


def is_supported_plan_view(view):
    """Return True if view is Area Plan or Floor Plan."""
    if not view:
        return False
    try:
        return view.ViewType in ALLOWED_VIEW_TYPES
    except:
        return False


def get_grid_by_name(name):
    """Find a grid by exact name."""
    for g in FilteredElementCollector(doc).OfClass(Grid):
        try:
            if g.Name == name:
                return g
        except:
            pass
    return None


def view_name_matches(view, keyword):
    """Case-insensitive contains check. Blank keyword matches all."""
    if not keyword:
        return True
    try:
        return keyword.lower() in (view.Name or "").lower()
    except:
        return False


def grid_intersection_point(g1, g2):
    """
    Return XYZ intersection point of two model grid curves.
    This does NOT rely on view-specific extents, so it is more robust.
    """
    ira = clr.Reference[IntersectionResultArray]()
    try:
        res = g1.Curve.Intersect(g2.Curve, ira)
        ira_val = ira.Value
        if res == SetComparisonResult.Overlap and ira_val is not None and ira_val.Size > 0:
            return ira_val.get_Item(0).XYZPoint
    except:
        pass
    return None


def model_point_to_sheet_xy(vp, view, model_pt):
    """
    Map a model point (XYZ) to a sheet point (XYZ) within this viewport,
    using the view CropBox and the viewport box outline.

    This is the key that allows different crop regions to still align
    the same grid intersection across sheets.
    """
    crop = view.CropBox
    if crop is None:
        return None

    try:
        inv = crop.Transform.Inverse
        p_local = inv.OfPoint(model_pt)

        minp = crop.Min
        maxp = crop.Max

        dx = maxp.X - minp.X
        dy = maxp.Y - minp.Y

        if abs(dx) < 1e-9 or abs(dy) < 1e-9:
            return None

        fx = (p_local.X - minp.X) / dx
        fy = (p_local.Y - minp.Y) / dy

        outline = vp.GetBoxOutline()
        o_min = outline.MinimumPoint
        o_max = outline.MaximumPoint

        sx = o_min.X + fx * (o_max.X - o_min.X)
        sy = o_min.Y + fy * (o_max.Y - o_min.Y)

        return XYZ(sx, sy, 0)
    except:
        return None


def get_matching_plan_viewports_on_sheet(sheet, keyword):
    """
    Return Area Plan / Floor Plan viewports on this sheet
    whose view name matches keyword.
    """
    vps = FilteredElementCollector(doc, sheet.Id).OfClass(Viewport).ToElements()
    out = []

    for vp in vps:
        view = doc.GetElement(vp.ViewId)
        if not is_supported_plan_view(view):
            continue

        if not view_name_matches(view, keyword):
            continue

        out.append(vp)

    return out


def view_type_label(view):
    """Readable label for reporting."""
    if not view:
        return "Unknown"
    try:
        if view.ViewType == ViewType.AreaPlan:
            return "Area Plan"
        elif view.ViewType == ViewType.FloorPlan:
            return "Floor Plan"
        else:
            return str(view.ViewType)
    except:
        return "Unknown"


# --------------------------------------------------
# UI
# --------------------------------------------------

# 1) Pick reference viewport
try:
    ref_pick = uidoc.Selection.PickObject(
        ObjectType.Element,
        "Pick REFERENCE Area Plan or Floor Plan viewport (already positioned correctly)"
    )
except:
    forms.alert("Cancelled.", exitscript=True)

ref_vp = doc.GetElement(ref_pick.ElementId)
if not isinstance(ref_vp, Viewport):
    forms.alert("That is not a viewport. Please pick a viewport placed on a sheet.", exitscript=True)

ref_view = doc.GetElement(ref_vp.ViewId)
if not is_supported_plan_view(ref_view):
    forms.alert("Reference viewport must be an Area Plan or Floor Plan viewport.", exitscript=True)

# 2) Ask for grid names
grid_a = forms.ask_for_string(
    default="6",
    prompt="Enter first grid name (example: 6)",
    title="Anchor Grid 1"
)
if not grid_a:
    forms.alert("No first grid name provided.", exitscript=True)

grid_b = forms.ask_for_string(
    default="A",
    prompt="Enter second grid name (example: A)",
    title="Anchor Grid 2"
)
if not grid_b:
    forms.alert("No second grid name provided.", exitscript=True)

g1 = get_grid_by_name(grid_a)
g2 = get_grid_by_name(grid_b)

if not g1 or not g2:
    forms.alert(
        "Could not find grid(s).\n\nGrid 1: {}\nGrid 2: {}".format(grid_a, grid_b),
        exitscript=True
    )

# 3) Ask for name filter
keyword = forms.ask_for_string(
    default="LEVEL",
    prompt=(
        "Move only Area Plan / Floor Plan views whose VIEW NAME contains this text.\n"
        "Examples: LEVEL, AREA PLAN, FLOOR PLAN, LEVEL 2\n"
        "Leave blank to move ALL matching plan viewports."
    ),
    title="View Name Filter"
)

# 4) Compute reference anchor point
ref_anchor_model = grid_intersection_point(g1, g2)
if not ref_anchor_model:
    forms.alert(
        "Could not compute the intersection of Grid {} and Grid {}.\n"
        "Check that the two grids are not parallel and that the names are correct.".format(grid_a, grid_b),
        exitscript=True
    )

ref_anchor_sheet = model_point_to_sheet_xy(ref_vp, ref_view, ref_anchor_model)
if not ref_anchor_sheet:
    forms.alert(
        "Could not map the reference anchor point to the sheet.\n"
        "Possible reasons:\n"
        "- the reference view has no active crop box\n"
        "- the crop box is invalid\n"
        "- the anchor point is outside the effective crop",
        exitscript=True
    )

# 5) Select target sheets
target_sheets = forms.select_sheets(title="Select target sheets")
if not target_sheets:
    forms.alert("No sheets selected.", exitscript=True)

# --------------------------------------------------
# Align
# --------------------------------------------------

moved = 0
failed = 0
skipped = 0
area_count = 0
floor_count = 0

with revit.Transaction("Align Plan Viewports by Grid Anchor"):
    for sh in target_sheets:
        vps = get_matching_plan_viewports_on_sheet(sh, keyword)

        if not vps:
            continue

        for vp in vps:
            if vp.Id == ref_vp.Id:
                skipped += 1
                continue

            view = doc.GetElement(vp.ViewId)
            if not is_supported_plan_view(view):
                failed += 1
                continue

            anchor_sheet = model_point_to_sheet_xy(vp, view, ref_anchor_model)
            if not anchor_sheet:
                failed += 1
                continue

            delta = XYZ(
                ref_anchor_sheet.X - anchor_sheet.X,
                ref_anchor_sheet.Y - anchor_sheet.Y,
                0
            )

            if abs(delta.X) < 1e-9 and abs(delta.Y) < 1e-9:
                skipped += 1
                continue

            try:
                ElementTransformUtils.MoveElement(doc, vp.Id, delta)
                moved += 1

                if view.ViewType == ViewType.AreaPlan:
                    area_count += 1
                elif view.ViewType == ViewType.FloorPlan:
                    floor_count += 1

            except:
                failed += 1

forms.alert(
    "Done.\n\n"
    "Reference View Type: {}\n"
    "Moved: {}\n"
    "  - Area Plans: {}\n"
    "  - Floor Plans: {}\n"
    "Skipped: {}\n"
    "Failed: {}".format(
        view_type_label(ref_view),
        moved,
        area_count,
        floor_count,
        skipped,
        failed
    )
)