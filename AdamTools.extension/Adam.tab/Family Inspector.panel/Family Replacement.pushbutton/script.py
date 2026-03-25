# -*- coding: utf-8 -*-

from pyrevit import revit, DB, script, forms
from Autodesk.Revit.UI.Selection import ObjectType

doc = revit.doc
uidoc = revit.uidoc
output = script.get_output()


# -------------------------------------------------------
# Selection
# -------------------------------------------------------
def get_selected_or_pick_one():
    sel_ids = list(uidoc.Selection.GetElementIds())

    if sel_ids:
        return doc.GetElement(sel_ids[0])

    try:
        picked_ref = uidoc.Selection.PickObject(
            ObjectType.Element,
            "Select old switch instance"
        )
        if picked_ref:
            return doc.GetElement(picked_ref.ElementId)
    except:
        return None

    return None


def pick_target_face_reference():
    """
    Let user pick a face/point on element.
    Works for local or linked model faces in many Revit cases.
    """
    try:
        picked_ref = uidoc.Selection.PickObject(
            ObjectType.PointOnElement,
            "Pick target face on wall (local or linked model)"
        )
        return picked_ref
    except:
        return None


# -------------------------------------------------------
# Safe naming
# -------------------------------------------------------
def safe_element_name(elem):
    if not elem:
        return None

    try:
        return elem.Name
    except:
        pass

    try:
        return DB.Element.Name.GetValue(elem)
    except:
        pass

    try:
        p = elem.get_Parameter(DB.BuiltInParameter.ALL_MODEL_TYPE_NAME)
        if p and p.HasValue:
            return p.AsString()
    except:
        pass

    try:
        p = elem.get_Parameter(DB.BuiltInParameter.SYMBOL_NAME_PARAM)
        if p and p.HasValue:
            return p.AsString()
    except:
        pass

    return "(could not read name)"


# -------------------------------------------------------
# Point / vector helpers
# -------------------------------------------------------
def get_location_point(el):
    try:
        loc = el.Location
        if isinstance(loc, DB.LocationPoint):
            return loc.Point
    except:
        pass
    return None


def xyz_to_str(pt):
    if not pt:
        return "None"
    return "X: {:.3f}, Y: {:.3f}, Z: {:.3f}".format(pt.X, pt.Y, pt.Z)


def vector_to_str(v):
    if not v:
        return "None"
    return "X: {:.3f}, Y: {:.3f}, Z: {:.3f}".format(v.X, v.Y, v.Z)


def safe_normalize(vec):
    try:
        if vec and vec.GetLength() > 1e-9:
            return vec.Normalize()
    except:
        pass
    return None


def get_old_rotation(old_inst):
    try:
        loc = old_inst.Location
        if isinstance(loc, DB.LocationPoint):
            return loc.Rotation
    except:
        pass
    return 0.0


# -------------------------------------------------------
# Target symbol picker
# -------------------------------------------------------
class SymbolOption(object):
    def __init__(self, symbol):
        self.symbol = symbol
        self.family_name = safe_element_name(symbol.Family)
        self.type_name = safe_element_name(symbol)

    @property
    def name(self):
        return "{} | {}".format(self.family_name, self.type_name)


def get_selectable_target_symbols():
    symbols = []

    collector = DB.FilteredElementCollector(doc).OfClass(DB.FamilySymbol)

    for sym in collector:
        try:
            fam_name = safe_element_name(sym.Family)
            type_name = safe_element_name(sym)
            cat_name = safe_element_name(sym.Category) if sym.Category else ""

            if not fam_name or not type_name:
                continue

            if cat_name not in ["Electrical Fixtures", "Generic Models", "Specialty Equipment"]:
                continue

            symbols.append(SymbolOption(sym))
        except:
            pass

    symbols = sorted(symbols, key=lambda x: (x.family_name or "", x.type_name or ""))
    return symbols


def pick_target_symbol():
    options = get_selectable_target_symbols()

    if not options:
        return None

    picked = forms.SelectFromList.show(
        options,
        name_attr='name',
        title='Select target replacement family/type',
        width=700,
        button_name='Use Selected Type',
        multiselect=False
    )

    if not picked:
        return None

    return picked.symbol


# -------------------------------------------------------
# Reference direction from picked face
# -------------------------------------------------------
def get_face_and_ref_dir_from_reference(picked_ref, fallback_rot=0.0):
    """
    Try to derive:
    - placement point
    - face normal
    - safe reference direction (not parallel to normal)
    """
    placement_pt = None
    face_normal = None
    ref_dir = None

    try:
        placement_pt = picked_ref.GlobalPoint
    except:
        pass

    # Try to get geometry object from picked reference in host doc
    face = None
    try:
        geom_obj = doc.GetElement(picked_ref.ElementId).GetGeometryObjectFromReference(picked_ref)
        face = geom_obj
    except:
        face = None

    if face:
        try:
            proj = face.Project(placement_pt)
            if proj:
                uv = proj.UVPoint
                n = face.ComputeNormal(uv)
                face_normal = safe_normalize(n)
        except:
            pass

    # Build reference direction
    if face_normal:
        try:
            up = DB.XYZ.BasisZ
            cand = up.CrossProduct(face_normal)
            cand = safe_normalize(cand)
            if cand and cand.GetLength() > 1e-9:
                ref_dir = cand
        except:
            pass

    if not ref_dir:
        try:
            import math
            ref_dir = DB.XYZ(math.cos(fallback_rot), math.sin(fallback_rot), 0.0)
            ref_dir = safe_normalize(ref_dir)
        except:
            pass

    if not ref_dir:
        ref_dir = DB.XYZ.BasisX

    return placement_pt, face_normal, ref_dir


# -------------------------------------------------------
# Level / parameter helpers
# -------------------------------------------------------
def ask_delete_old_option():
    res = forms.alert(
        "After successful placement, do you want to delete the old instance?",
        title="Old Instance Option",
        yes=True,
        no=True
    )
    return True if res else False


def ask_elevation_from_level():
    val = forms.ask_for_string(
        default="0.0",
        prompt="Input Elevation from Level in decimal feet.\nExample: 0.0 or 4.0",
        title="Elevation from Level"
    )
    if val is None:
        return None

    try:
        return float(val)
    except:
        return None


def get_param_value_as_element(doc_, param):
    if not param or not param.HasValue:
        return None

    try:
        if param.StorageType == DB.StorageType.ElementId:
            eid = param.AsElementId()
            if eid and eid != DB.ElementId.InvalidElementId:
                return doc_.GetElement(eid)
    except:
        pass

    return None


def get_level_from_element(el, el_doc):
    """
    Try a few common level-ish parameters on an element.
    """
    if not el:
        return None

    bip_list = [
        DB.BuiltInParameter.WALL_BASE_CONSTRAINT,
        DB.BuiltInParameter.FAMILY_LEVEL_PARAM,
        DB.BuiltInParameter.INSTANCE_REFERENCE_LEVEL_PARAM,
        DB.BuiltInParameter.INSTANCE_SCHEDULE_ONLY_LEVEL_PARAM,
        DB.BuiltInParameter.SCHEDULE_LEVEL_PARAM,
        DB.BuiltInParameter.LEVEL_PARAM,
    ]

    for bip in bip_list:
        try:
            p = el.get_Parameter(bip)
            lvl = get_param_value_as_element(el_doc, p)
            if isinstance(lvl, DB.Level):
                return lvl
        except:
            pass

    try:
        lvl_id = el.LevelId
        if lvl_id and lvl_id != DB.ElementId.InvalidElementId:
            lvl = el_doc.GetElement(lvl_id)
            if isinstance(lvl, DB.Level):
                return lvl
    except:
        pass

    return None


def get_old_instance_level(old_inst):
    return get_level_from_element(old_inst, doc)


def get_level_from_picked_reference(picked_ref):
    """
    Try to infer a level from the picked host element.
    Works for local host or linked host.
    Returns:
        level_in_main_doc, host_elem_name, host_context
    """
    # local element path
    try:
        host_elem = doc.GetElement(picked_ref.ElementId)
        if host_elem and not isinstance(host_elem, DB.RevitLinkInstance):
            lvl = get_level_from_element(host_elem, doc)
            return lvl, safe_element_name(host_elem), "Local"
    except:
        pass

    # linked element path
    try:
        link_inst = doc.GetElement(picked_ref.ElementId)
        if isinstance(link_inst, DB.RevitLinkInstance):
            linked_doc = link_inst.GetLinkDocument()
            if linked_doc:
                linked_elem_id = picked_ref.LinkedElementId
                linked_elem = linked_doc.GetElement(linked_elem_id)
                linked_lvl = get_level_from_element(linked_elem, linked_doc)

                if linked_lvl:
                    linked_lvl_name = safe_element_name(linked_lvl)

                    # match by level name in main doc
                    for lvl in DB.FilteredElementCollector(doc).OfClass(DB.Level):
                        if safe_element_name(lvl) == linked_lvl_name:
                            return lvl, safe_element_name(linked_elem), "Linked (matched by name)"

                    return None, safe_element_name(linked_elem), "Linked (level found in link only)"
    except:
        pass

    return None, None, "Unknown"


def set_param_if_possible(param, value):
    if not param:
        return False, "missing"

    try:
        if param.IsReadOnly:
            return False, "read-only"
    except:
        return False, "could-not-check-readonly"

    try:
        st = param.StorageType

        if st == DB.StorageType.Double:
            param.Set(float(value))
            return True, "ok"

        if st == DB.StorageType.ElementId:
            if isinstance(value, DB.ElementId):
                param.Set(value)
                return True, "ok"
            return False, "wrong-value-type"

        if st == DB.StorageType.Integer:
            param.Set(int(value))
            return True, "ok"

        if st == DB.StorageType.String:
            param.Set(str(value))
            return True, "ok"

        return False, "unsupported-storage-type"

    except Exception as ex:
        return False, str(ex)


def try_set_level_params(inst, target_level):
    logs = []
    success_any = False

    candidates = [
        ("INSTANCE_SCHEDULE_ONLY_LEVEL_PARAM", DB.BuiltInParameter.INSTANCE_SCHEDULE_ONLY_LEVEL_PARAM),
        ("SCHEDULE_LEVEL_PARAM", DB.BuiltInParameter.SCHEDULE_LEVEL_PARAM),
        ("FAMILY_LEVEL_PARAM", DB.BuiltInParameter.FAMILY_LEVEL_PARAM),
        ("INSTANCE_REFERENCE_LEVEL_PARAM", DB.BuiltInParameter.INSTANCE_REFERENCE_LEVEL_PARAM),
        ("LEVEL_PARAM", DB.BuiltInParameter.LEVEL_PARAM),
    ]

    for label, bip in candidates:
        try:
            p = inst.get_Parameter(bip)
            ok, msg = set_param_if_possible(p, target_level.Id)
            logs.append("{} -> {}".format(label, msg))
            if ok:
                success_any = True
        except Exception as ex:
            logs.append("{} -> {}".format(label, str(ex)))

    return success_any, logs


def try_set_elevation_params(inst, elev_ft):
    logs = []
    success_any = False

    candidates = [
        ("INSTANCE_ELEVATION_PARAM", DB.BuiltInParameter.INSTANCE_ELEVATION_PARAM),
        ("INSTANCE_FREE_HOST_OFFSET_PARAM", DB.BuiltInParameter.INSTANCE_FREE_HOST_OFFSET_PARAM),
        ("FAMILY_BASE_LEVEL_OFFSET_PARAM", DB.BuiltInParameter.FAMILY_BASE_LEVEL_OFFSET_PARAM),
    ]

    for label, bip in candidates:
        try:
            p = inst.get_Parameter(bip)
            ok, msg = set_param_if_possible(p, elev_ft)
            logs.append("{} -> {}".format(label, msg))
            if ok:
                success_any = True
        except Exception as ex:
            logs.append("{} -> {}".format(label, str(ex)))

    return success_any, logs


def get_param_display(inst, bip):
    try:
        p = inst.get_Parameter(bip)
        if not p:
            return "<missing>"

        try:
            val_str = p.AsValueString()
            if val_str:
                return val_str
        except:
            pass

        try:
            if p.StorageType == DB.StorageType.ElementId:
                eid = p.AsElementId()
                if eid and eid != DB.ElementId.InvalidElementId:
                    elem = doc.GetElement(eid)
                    return safe_element_name(elem) or str(eid.IntegerValue)
        except:
            pass

        try:
            if p.StorageType == DB.StorageType.Double:
                return str(p.AsDouble())
        except:
            pass

        try:
            if p.StorageType == DB.StorageType.String:
                return p.AsString()
        except:
            pass

        try:
            if p.StorageType == DB.StorageType.Integer:
                return str(p.AsInteger())
        except:
            pass
    except:
        pass

    return "<unreadable>"


# -------------------------------------------------------
# Main
# -------------------------------------------------------
old = get_selected_or_pick_one()

if not old:
    output.print_md("## ❌ No element selected")
    output.print_md("Please preselect one old switch, or run the tool and pick one.")
    script.exit()

if not isinstance(old, DB.FamilyInstance):
    output.print_md("## ⚠ Selected element is not a FamilyInstance")
    output.print_md("**Element Id:** {}".format(old.Id.IntegerValue))
    script.exit()

old_pt = get_location_point(old)
if not old_pt:
    output.print_md("## ❌ Could not read insertion point from selected instance")
    script.exit()

target_symbol = pick_target_symbol()
if not target_symbol:
    output.print_md("## ❌ No target family/type selected")
    script.exit()

delete_old = ask_delete_old_option()

elev_from_level_ft = ask_elevation_from_level()
if elev_from_level_ft is None:
    output.print_md("## ❌ Invalid or cancelled elevation input")
    script.exit()

picked_face_ref = pick_target_face_reference()
if not picked_face_ref:
    output.print_md("## ❌ No target face picked")
    script.exit()

old_symbol = None
old_family = None

try:
    old_symbol = old.Symbol
except:
    pass

try:
    old_family = old_symbol.Family if old_symbol else None
except:
    pass

old_rot = get_old_rotation(old)

placement_pt, face_normal, ref_dir = get_face_and_ref_dir_from_reference(
    picked_face_ref,
    fallback_rot=old_rot
)

if not placement_pt:
    output.print_md("## ❌ Could not determine placement point from picked face")
    script.exit()

# infer level
inferred_level = None
level_source = None
host_elem_name = None
host_context = None

inferred_level, host_elem_name, host_context = get_level_from_picked_reference(picked_face_ref)

if inferred_level:
    level_source = "Picked host"
else:
    inferred_level = get_old_instance_level(old)
    if inferred_level:
        level_source = "Old instance fallback"

output.print_md("# 🔁 Replace Switch v8")
output.print_md("---")
output.print_md("## Source Instance")
output.print_md("**Old Element Id:** {}".format(old.Id.IntegerValue))
output.print_md("**Old Family:** {}".format(safe_element_name(old_family) if old_family else "Unknown"))
output.print_md("**Old Type:** {}".format(safe_element_name(old_symbol) if old_symbol else "Unknown"))
output.print_md("**Old Point:** {}".format(xyz_to_str(old_pt)))

output.print_md("---")
output.print_md("## Target Replacement")
output.print_md("**New Family:** {}".format(safe_element_name(target_symbol.Family)))
output.print_md("**New Type:** {}".format(safe_element_name(target_symbol)))
output.print_md("**Delete Old After Success:** {}".format("Yes" if delete_old else "No"))
output.print_md("**Requested Elevation from Level:** {:.3f} ft".format(elev_from_level_ft))

output.print_md("---")
output.print_md("## Picked Face Info")
output.print_md("**Picked Reference Element Id:** {}".format(
    picked_face_ref.ElementId.IntegerValue if picked_face_ref.ElementId else "Unknown"
))
output.print_md("**Placement Point:** {}".format(xyz_to_str(placement_pt)))
output.print_md("**Old Rotation (rad):** {:.6f}".format(old_rot))
output.print_md("**Reference Direction:** {}".format(vector_to_str(ref_dir)))
output.print_md("**Face Normal:** {}".format(vector_to_str(face_normal) if face_normal else "Unknown"))
output.print_md("**Picked Host Context:** {}".format(host_context if host_context else "Unknown"))
output.print_md("**Picked Host Element:** {}".format(host_elem_name if host_elem_name else "Unknown"))

output.print_md("---")
output.print_md("## Level Inference")
if inferred_level:
    output.print_md("**Inferred Level:** {}".format(safe_element_name(inferred_level)))
    output.print_md("**Level Source:** {}".format(level_source if level_source else "Unknown"))
else:
    output.print_md("**Inferred Level:** None")
    output.print_md("**Level Source:** Could not infer from picked host or old instance")

new_inst = None
error_msg = None
level_set_success = False
level_set_logs = []
elev_set_success = False
elev_set_logs = []
delete_msg = "Old instance kept."

t = DB.Transaction(doc, "Replace switch v8")
t.Start()

try:
    if not target_symbol.IsActive:
        target_symbol.Activate()
        doc.Regenerate()

    new_inst = doc.Create.NewFamilyInstance(
        picked_face_ref,
        placement_pt,
        ref_dir,
        target_symbol
    )

    doc.Regenerate()

    if inferred_level:
        level_set_success, level_set_logs = try_set_level_params(new_inst, inferred_level)

    elev_set_success, elev_set_logs = try_set_elevation_params(new_inst, elev_from_level_ft)

    doc.Regenerate()

    if delete_old and new_inst:
        try:
            doc.Delete(old.Id)
            delete_msg = "Old instance deleted."
        except Exception as delete_ex:
            delete_msg = "New instance placed, but old instance was NOT deleted: {}".format(str(delete_ex))
    else:
        delete_msg = "Old instance kept."

    t.Commit()

except Exception as ex:
    error_msg = str(ex)
    try:
        t.RollBack()
    except:
        pass

output.print_md("---")

if new_inst:
    output.print_md("## ✅ Placement Succeeded")
    output.print_md("**New Element Id:** {}".format(new_inst.Id.IntegerValue))
    output.print_md("**Old Instance Result:** {}".format(delete_msg))
else:
    output.print_md("## ❌ Placement Failed")
    output.print_md("**Error:** `{}`".format(error_msg if error_msg else "Unknown error"))

if new_inst:
    output.print_md("---")
    output.print_md("## Parameter Write Result")

    if inferred_level:
        output.print_md("**Level Write Success:** {}".format("Yes" if level_set_success else "No"))
    else:
        output.print_md("**Level Write Success:** Not attempted (no inferred level)")

    output.print_md("**Elevation Write Success:** {}".format("Yes" if elev_set_success else "No"))

    output.print_md("### Level Parameter Attempts")
    if level_set_logs:
        for line in level_set_logs:
            output.print_md("- {}".format(line))
    else:
        output.print_md("- Not attempted")

    output.print_md("### Elevation Parameter Attempts")
    if elev_set_logs:
        for line in elev_set_logs:
            output.print_md("- {}".format(line))
    else:
        output.print_md("- Not attempted")

    output.print_md("### Readback")
    for label, bip in [
        ("INSTANCE_SCHEDULE_ONLY_LEVEL_PARAM", DB.BuiltInParameter.INSTANCE_SCHEDULE_ONLY_LEVEL_PARAM),
        ("SCHEDULE_LEVEL_PARAM", DB.BuiltInParameter.SCHEDULE_LEVEL_PARAM),
        ("FAMILY_LEVEL_PARAM", DB.BuiltInParameter.FAMILY_LEVEL_PARAM),
        ("INSTANCE_REFERENCE_LEVEL_PARAM", DB.BuiltInParameter.INSTANCE_REFERENCE_LEVEL_PARAM),
        ("LEVEL_PARAM", DB.BuiltInParameter.LEVEL_PARAM),
        ("INSTANCE_ELEVATION_PARAM", DB.BuiltInParameter.INSTANCE_ELEVATION_PARAM),
        ("INSTANCE_FREE_HOST_OFFSET_PARAM", DB.BuiltInParameter.INSTANCE_FREE_HOST_OFFSET_PARAM),
        ("FAMILY_BASE_LEVEL_OFFSET_PARAM", DB.BuiltInParameter.FAMILY_BASE_LEVEL_OFFSET_PARAM),
    ]:
        output.print_md("- **{}:** {}".format(label, get_param_display(new_inst, bip)))

output.print_md("---")
output.print_md("## Notes")
output.print_md("This version still uses manual picked-face hosting.")
output.print_md("It now adds:")
output.print_md("- keep/delete old instance option")
output.print_md("- inferred level from picked host, with old instance fallback")
output.print_md("- user input for elevation from level")
output.print_md("- post-placement parameter write attempts and reporting")
output.print_md("It still does NOT yet handle:")
output.print_md("- batch replacement")
output.print_md("- broad parameter transfer")
output.print_md("- auto wall finding without manual picked face")