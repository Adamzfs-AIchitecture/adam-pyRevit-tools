# -*- coding: utf-8 -*-

from pyrevit import revit, DB, script
from Autodesk.Revit.UI.Selection import ObjectType

doc = revit.doc
uidoc = revit.uidoc
output = script.get_output()


def get_selected_or_pick_one():
    """Allow either preselection or pick-after-run."""
    sel_ids = list(uidoc.Selection.GetElementIds())

    if sel_ids:
        return doc.GetElement(sel_ids[0])

    try:
        picked_ref = uidoc.Selection.PickObject(
            ObjectType.Element,
            "Select one family instance"
        )
        if picked_ref:
            return doc.GetElement(picked_ref.ElementId)
    except:
        return None

    return None


def safe_element_name(elem):
    """Safely get Revit element name in IronPython."""
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


def safe_get_level(element):
    """Try several common ways to get level."""
    try:
        level_id = element.LevelId
        if level_id and level_id != DB.ElementId.InvalidElementId:
            return doc.GetElement(level_id)
    except:
        pass

    try:
        p = element.get_Parameter(DB.BuiltInParameter.FAMILY_LEVEL_PARAM)
        if p and p.HasValue:
            level_id = p.AsElementId()
            if level_id and level_id != DB.ElementId.InvalidElementId:
                return doc.GetElement(level_id)
    except:
        pass

    try:
        p = element.get_Parameter(DB.BuiltInParameter.INSTANCE_REFERENCE_LEVEL_PARAM)
        if p and p.HasValue:
            level_id = p.AsElementId()
            if level_id and level_id != DB.ElementId.InvalidElementId:
                return doc.GetElement(level_id)
    except:
        pass

    return None


def safe_get_host(element):
    """Safely get host if available."""
    try:
        host = element.Host
        if host:
            return host
    except:
        pass
    return None


def safe_get_workplane_info(element):
    """Try to read sketch/work plane related info."""
    try:
        if hasattr(element, "SketchPlane") and element.SketchPlane:
            return element.SketchPlane.Name
    except:
        pass
    return None


def safe_get_symbol_and_family(element):
    """Get type and family safely."""
    symbol = None
    family = None

    try:
        symbol = element.Symbol
    except:
        pass

    if symbol:
        try:
            family = symbol.Family
        except:
            pass

    return symbol, family


def safe_get_param_value(param):
    """Safely convert parameter value to readable text."""
    if not param or not param.HasValue:
        return None

    try:
        val = param.AsValueString()
        if val:
            return val
    except:
        pass

    try:
        val = param.AsString()
        if val:
            return val
    except:
        pass

    try:
        return str(param.AsInteger())
    except:
        pass

    try:
        return str(param.AsDouble())
    except:
        pass

    try:
        eid = param.AsElementId()
        if eid and eid != DB.ElementId.InvalidElementId:
            return str(eid.IntegerValue)
    except:
        pass

    return "(unreadable)"


def report_parameter(element, bip, label):
    """Print built-in parameter if available."""
    try:
        p = element.get_Parameter(bip)
        val = safe_get_param_value(p)
        if val is not None:
            output.print_md("**{}:** {}".format(label, val))
            return
    except:
        pass

    output.print_md("**{}:** None".format(label))


def bool_text(val):
    try:
        return "Yes" if val else "No"
    except:
        return "Unknown"


def safe_attr(obj, attr_name, default=None):
    try:
        return getattr(obj, attr_name)
    except:
        return default


def collect_family_doc_info(family):
    """
    Open the family document for inspection.
    Return a dict of family-definition properties.
    """
    info = {
        "family_doc_title": None,
        "family_category": None,
        "is_work_plane_based": None,
        "is_always_vertical": None,
        "is_shared": None,
        "placement_type": None,
        "error": None
    }

    famdoc = None

    try:
        famdoc = doc.EditFamily(family)

        info["family_doc_title"] = famdoc.Title

        owner_family = None
        try:
            owner_family = famdoc.OwnerFamily
        except:
            owner_family = None

        if not owner_family:
            info["error"] = "Could not access OwnerFamily from family document."
            return info

        # Family category
        try:
            fam_cat = owner_family.FamilyCategory
            if fam_cat:
                info["family_category"] = safe_element_name(fam_cat)
        except:
            pass

        # Family properties
        try:
            info["is_work_plane_based"] = owner_family.IsWorkPlaneBased
        except:
            pass

        try:
            info["is_always_vertical"] = owner_family.IsAlwaysVertical
        except:
            pass

        try:
            info["is_shared"] = owner_family.IsShared
        except:
            pass

        try:
            placement_type = owner_family.FamilyPlacementType
            if placement_type is not None:
                info["placement_type"] = str(placement_type)
        except:
            pass

    except Exception as ex:
        info["error"] = str(ex)

    finally:
        if famdoc:
            try:
                famdoc.Close(False)  # close without saving
            except:
                pass

    return info


# -----------------------------
# Main
# -----------------------------

el = get_selected_or_pick_one()

if not el:
    output.print_md("## ❌ No element selected")
    output.print_md("Please preselect one family instance, or run the tool and pick one.")
    script.exit()

if not isinstance(el, DB.FamilyInstance):
    output.print_md("## ⚠ Selected element is not a FamilyInstance")
    output.print_md("**Element Id:** {}".format(el.Id.IntegerValue))
    output.print_md("**Category:** {}".format(el.Category.Name if el.Category else "N/A"))
    output.print_md("Please select a placed family instance, such as your switch.")
    script.exit()

symbol, family = safe_get_symbol_and_family(el)
host = safe_get_host(el)
level = safe_get_level(el)
work_plane = safe_get_workplane_info(el)

# -----------------------------
# A. Instance Report
# -----------------------------
output.print_md("# 🔍 Family Inspector v2")
output.print_md("## A. Instance Report")
output.print_md("---")

output.print_md("**Element Id:** {}".format(el.Id.IntegerValue))
output.print_md("**Category:** {}".format(el.Category.Name if el.Category else "N/A"))
output.print_md("**Class:** {}".format(el.GetType().Name))

if family:
    output.print_md("**Family Name:** {}".format(safe_element_name(family)))
else:
    output.print_md("**Family Name:** Could not read")

if symbol:
    output.print_md("**Type Name:** {}".format(safe_element_name(symbol)))
else:
    output.print_md("**Type Name:** Could not read")

output.print_md("---")
output.print_md("### Host / Placement Clues")

if host:
    host_cat = host.Category.Name if host.Category else "N/A"
    host_name = safe_element_name(host)
    output.print_md("**Host:** {} | Category: {} | Id: {}".format(
        host_name, host_cat, host.Id.IntegerValue
    ))
else:
    output.print_md("**Host:** None")

if level:
    output.print_md("**Level:** {}".format(safe_element_name(level)))
else:
    output.print_md("**Level:** None")

output.print_md("**Work Plane:** {}".format(work_plane if work_plane else "None"))

output.print_md("---")
output.print_md("### Parameter Clues")
report_parameter(el, DB.BuiltInParameter.INSTANCE_ELEVATION_PARAM, "Instance Elevation")
report_parameter(el, DB.BuiltInParameter.FAMILY_BASE_LEVEL_PARAM, "Base Level")
report_parameter(el, DB.BuiltInParameter.FAMILY_LEVEL_PARAM, "Family Level")

output.print_md("---")
output.print_md("### Instance-Based Hosting Analysis")

if host:
    if isinstance(host, DB.Wall):
        output.print_md("➡️ This instance is currently **hosted by a wall**.")
        output.print_md("It is likely **wall-hosted** or another host-based family placed on a wall face.")
    else:
        output.print_md("➡️ This instance has a **host element**, but not a wall.")
        output.print_md("It is some kind of **host-based family**.")
elif work_plane:
    output.print_md("➡️ This looks more like a **work-plane-based family**.")
elif level:
    output.print_md("➡️ This looks like a **level-based / non-hosted family**.")
else:
    output.print_md("➡️ Hosting type could not be confidently inferred from the instance.")

# -----------------------------
# B. Family Definition Report
# -----------------------------
output.print_md("")
output.print_md("## B. Family Definition Report")
output.print_md("---")

if not family:
    output.print_md("❌ Could not access the family definition.")
    script.exit()

fam_info = collect_family_doc_info(family)

if fam_info["error"]:
    output.print_md("**Family Definition Read Error:** `{}`".format(fam_info["error"]))
else:
    output.print_md("**Family Document:** {}".format(fam_info["family_doc_title"] or "Unknown"))
    output.print_md("**Family Category:** {}".format(fam_info["family_category"] or "Unknown"))
    output.print_md("**FamilyPlacementType:** {}".format(fam_info["placement_type"] or "Unknown"))
    output.print_md("**IsWorkPlaneBased:** {}".format(bool_text(fam_info["is_work_plane_based"])))
    output.print_md("**IsAlwaysVertical:** {}".format(bool_text(fam_info["is_always_vertical"])))
    output.print_md("**IsShared:** {}".format(bool_text(fam_info["is_shared"])))

    output.print_md("---")
    output.print_md("### Family-Definition Interpretation")

    placement = fam_info["placement_type"]
    wpb = fam_info["is_work_plane_based"]

    if placement:
        output.print_md("➡️ Revit reports the family placement behavior as: **{}**".format(placement))

    if wpb is True:
        output.print_md("➡️ The family definition says it is **work-plane-based**.")
    elif wpb is False:
        output.print_md("➡️ The family definition says it is **not work-plane-based**.")

    if placement and "ViewBased" in placement:
        output.print_md("➡️ This is view-based content, not a model-hosting case.")
    elif placement and ("OneLevelBased" in placement or "TwoLevelsBased" in placement):
        output.print_md("➡️ This confirms a **level-based family pattern**, which matches your instance report.")
    elif placement and "WorkPlaneBased" in placement:
        output.print_md("➡️ This confirms a **work-plane-based family pattern**.")
    elif placement and "CurveBased" in placement:
        output.print_md("➡️ This is a curve-based family pattern.")
    elif placement and "Hosted" in placement:
        output.print_md("➡️ This is a host-based family pattern.")

output.print_md("")
output.print_md("## Next Step Suggestion")
output.print_md("If both the instance report and the family-definition report indicate a level-based pattern,")
output.print_md("then your old switch family should be treated as a **non-hosted family that needs replacement**, not direct conversion.")