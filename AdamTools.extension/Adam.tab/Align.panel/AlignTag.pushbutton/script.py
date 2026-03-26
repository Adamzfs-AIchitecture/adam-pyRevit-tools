# -*- coding: utf-8 -*-
from pyrevit import revit, forms
from Autodesk.Revit.DB import XYZ, ElementTransformUtils
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
    return a.X * b.X + a.Y * b.Y + a.Z * b.Z


def to_view_coords(p, right, up, viewdir):
    return dot(p, right), dot(p, up), dot(p, viewdir)


def from_view_delta(du, dv, dw, right, up, viewdir):
    return XYZ(
        right.X * du + up.X * dv + viewdir.X * dw,
        right.Y * du + up.Y * dv + viewdir.Y * dw,
        right.Z * du + up.Z * dv + viewdir.Z * dw
    )


def get_bbox_corners_in_model(bb):
    if not bb:
        return []

    mn = bb.Min
    mx = bb.Max

    return [
        XYZ(mn.X, mn.Y, mn.Z),
        XYZ(mn.X, mn.Y, mn.Z),
        XYZ(mn.X, mx.Y, mn.Z),
        XYZ(mx.X, mn.Y, mn.Z),
        XYZ(mx.X, mx.Y, mn.Z),
        XYZ(mn.X, mn.Y, mx.Z),
        XYZ(mn.X, mx.Y, mx.Z),
        XYZ(mx.X, mn.Y, mx.Z),
        XYZ(mx.X, mx.Y, mx.Z),
    ]


def get_visual_metrics(tag, view, right, up, viewdir):
    p = tag.TagHeadPosition
    head_u, head_v, head_w = to_view_coords(p, right, up, viewdir)

    bb = tag.get_BoundingBox(view)

    if bb:
        corners = get_bbox_corners_in_model(bb)
        uvw = [to_view_coords(c, right, up, viewdir) for c in corners]

        us = [x[0] for x in uvw]
        vs = [x[1] for x in uvw]

        left = min(us)
        right_m = max(us)
        bottom = min(vs)
        top = max(vs)
        center_u = (left + right_m) / 2.0
        center_v = (bottom + top) / 2.0

        return {
            "tag": tag,
            "head_u": head_u,
            "head_v": head_v,
            "head_w": head_w,
            "left": left,
            "right": right_m,
            "bottom": bottom,
            "top": top,
            "center_u": center_u,
            "center_v": center_v,
            "has_bbox": True
        }

    return {
        "tag": tag,
        "head_u": head_u,
        "head_v": head_v,
        "head_w": head_w,
        "left": head_u,
        "right": head_u,
        "bottom": head_v,
        "top": head_v,
        "center_u": head_u,
        "center_v": head_v,
        "has_bbox": False
    }


def move_tag_by_delta_uv(tag, du, dv, right, up, viewdir):
    delta_xyz = from_view_delta(du, dv, 0.0, right, up, viewdir)
    if delta_xyz.GetLength() > 1e-9:
        ElementTransformUtils.MoveElement(doc, tag.Id, delta_xyz)
        return True
    return False


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

items = []
bbox_count = 0

for t in tags:
    try:
        m = get_visual_metrics(t, view, right, up, viewdir)
        items.append(m)
        if m["has_bbox"]:
            bbox_count += 1
    except Exception as ex:
        print("Failed to read tag {}: {}".format(t.Id.IntegerValue, ex))

if len(items) < 2:
    forms.alert("Could not read enough tag positions.", exitscript=True)

moved_count = 0

with revit.Transaction("Align/Distribute Tags (Visual BBox)"):
    if action == "Align Left":
        target = min(i["left"] for i in items)
        for i in items:
            du = target - i["left"]
            if move_tag_by_delta_uv(i["tag"], du, 0.0, right, up, viewdir):
                moved_count += 1

    elif action == "Align Right":
        target = max(i["right"] for i in items)
        for i in items:
            du = target - i["right"]
            if move_tag_by_delta_uv(i["tag"], du, 0.0, right, up, viewdir):
                moved_count += 1

    elif action == "Align Top":
        target = max(i["top"] for i in items)
        for i in items:
            dv = target - i["top"]
            if move_tag_by_delta_uv(i["tag"], 0.0, dv, right, up, viewdir):
                moved_count += 1

    elif action == "Align Bottom":
        target = min(i["bottom"] for i in items)
        for i in items:
            dv = target - i["bottom"]
            if move_tag_by_delta_uv(i["tag"], 0.0, dv, right, up, viewdir):
                moved_count += 1

    elif action == "Distribute Horizontal":
        items_sorted = sorted(items, key=lambda x: x["center_u"])
        count = len(items_sorted)
        if count > 2:
            u_min = items_sorted[0]["center_u"]
            u_max = items_sorted[-1]["center_u"]
            if abs(u_max - u_min) > 1e-9:
                step = (u_max - u_min) / float(count - 1)
                for idx, i in enumerate(items_sorted):
                    target_center = u_min + step * idx
                    du = target_center - i["center_u"]
                    if move_tag_by_delta_uv(i["tag"], du, 0.0, right, up, viewdir):
                        moved_count += 1

    elif action == "Distribute Vertical":
        items_sorted = sorted(items, key=lambda x: x["center_v"])
        count = len(items_sorted)
        if count > 2:
            v_min = items_sorted[0]["center_v"]
            v_max = items_sorted[-1]["center_v"]
            if abs(v_max - v_min) > 1e-9:
                step = (v_max - v_min) / float(count - 1)
                for idx, i in enumerate(items_sorted):
                    target_center = v_min + step * idx
                    dv = target_center - i["center_v"]
                    if move_tag_by_delta_uv(i["tag"], 0.0, dv, right, up, viewdir):
                        moved_count += 1

msg = "Done.\n\nMoved {} tag(s).".format(moved_count)

if bbox_count < len(items):
    msg += "\nSome tags had no view bounding box, so they fell back to tag head position."

forms.alert(msg, title="pyRevit")