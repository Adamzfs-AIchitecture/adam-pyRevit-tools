# -*- coding: utf-8 -*-
from pyrevit import revit, forms
from Autodesk.Revit.DB import IndependentTag, SpatialElementTag, XYZ
from Autodesk.Revit.UI import Selection

doc = revit.doc
uidoc = revit.uidoc
view = doc.ActiveView


class TagSelectionFilter(Selection.ISelectionFilter):
    def AllowElement(self, elem):
        return hasattr(elem, "TagHeadPosition")
    def AllowReference(self, ref, point):
        return False


def get_selected_tags():
    # Use pre-selection if any, otherwise prompt selection
    sel_ids = list(uidoc.Selection.GetElementIds())
    tags = []
    for eid in sel_ids:
        e = doc.GetElement(eid)
        if hasattr(e, "TagHeadPosition"):
            tags.append(e)

    if tags:
        return tags

    picked = uidoc.Selection.PickElementsByRectangle(
        TagSelectionFilter(),
        "Window-select tags to align/distribute"
    )
    return list(picked)


def dot(a, b):
    return a.X*b.X + a.Y*b.Y + a.Z*b.Z


def to_view_coords(p, right, up, viewdir):
    # (u, v, w) in the view's orthonormal basis
    return dot(p, right), dot(p, up), dot(p, viewdir)


def from_view_coords(u, v, w, right, up, viewdir):
    return XYZ(
        right.X*u + up.X*v + viewdir.X*w,
        right.Y*u + up.Y*v + viewdir.Y*w,
        right.Z*u + up.Z*v + viewdir.Z*w
    )


# --- Main ---
tags = get_selected_tags()
if len(tags) < 2:
    forms.alert("Select at least 2 tags.", exitscript=True)

action = forms.CommandSwitchWindow.show(
    [
        "Align Left",
        "Align Right",
        "Align Top",
        "Align Bottom",
        "Distribute Horizontal",
        "Distribute Vertical",
    ],
    message="Choose an action for selected tags:"
)

if not action:
    forms.alert("No action selected.", exitscript=True)

right = view.RightDirection
up = view.UpDirection
viewdir = view.ViewDirection

# Collect positions in view coordinates
items = []
for t in tags:
    print("Selected:", t.GetType().FullName)
    print("Collected movable items", len(items))
    try:
        p = t.TagHeadPosition
        u, v, w = to_view_coords(p, right, up, viewdir)
        items.append((t, p, u, v, w))
    except Exception as ex:
        print("Failed", type(t), ex)
        # Some rare tag types can fail; skip safely
        pass

if len(items) < 2:
    forms.alert("Could not read tag head positions for enough tags.", exitscript=True)

with revit.Transaction("Align/Distribute Tags"):
    if action == "Align Left":
        target_u = min(i[2] for i in items)
        for t, p, u, v, w in items:
            t.TagHeadPosition = from_view_coords(target_u, v, w, right, up, viewdir)

    elif action == "Align Right":
        target_u = max(i[2] for i in items)
        for t, p, u, v, w in items:
            t.TagHeadPosition = from_view_coords(target_u, v, w, right, up, viewdir)

    elif action == "Align Top":
        target_v = max(i[3] for i in items)
        for t, p, u, v, w in items:
            t.TagHeadPosition = from_view_coords(u, target_v, w, right, up, viewdir)

    elif action == "Align Bottom":
        target_v = min(i[3] for i in items)
        for t, p, u, v, w in items:
            t.TagHeadPosition = from_view_coords(u, target_v, w, right, up, viewdir)

    elif action == "Distribute Horizontal":
        # Sort by u (left -> right)
        items_sorted = sorted(items, key=lambda x: x[2])
        u_min = items_sorted[0][2]
        u_max = items_sorted[-1][2]
        count = len(items_sorted)

        if count > 2 and abs(u_max - u_min) > 1e-9:
            step = (u_max - u_min) / float(count - 1)
            for idx, (t, p, u, v, w) in enumerate(items_sorted):
                new_u = u_min + step * idx
                t.TagHeadPosition = from_view_coords(new_u, v, w, right, up, viewdir)

    elif action == "Distribute Vertical":
        # Sort by v (bottom -> top)
        items_sorted = sorted(items, key=lambda x: x[3])
        v_min = items_sorted[0][3]
        v_max = items_sorted[-1][3]
        count = len(items_sorted)

        if count > 2 and abs(v_max - v_min) > 1e-9:
            step = (v_max - v_min) / float(count - 1)
            for idx, (t, p, u, v, w) in enumerate(items_sorted):
                new_v = v_min + step * idx
                t.TagHeadPosition = from_view_coords(u, new_v, w, right, up, viewdir)

forms.alert("Done.", title="pyRevit")