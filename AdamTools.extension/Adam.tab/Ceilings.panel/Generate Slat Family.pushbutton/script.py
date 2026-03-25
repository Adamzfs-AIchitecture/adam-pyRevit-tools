# -*- coding: utf-8 -*-
# pyRevit (IronPython) - Revit 2024.2 SAFE VERSION
# Fixes "There is no current type." by ensuring a family type exists before fm.Set()

from pyrevit import forms
from Autodesk.Revit.DB import (
    Transaction, SaveAsOptions, Plane, XYZ, SketchPlane,
    CurveArray, CurveArrArray, Line,
    ElementTransformUtils, UnitUtils
)

try:
    from Autodesk.Revit.DB import UnitTypeId, GroupTypeId, SpecTypeId
    HAS_NEW_PARAMS_API = True
except:
    HAS_NEW_PARAMS_API = False

app = __revit__.Application


def inches_to_internal(inches_val):
    try:
        return UnitUtils.ConvertToInternalUnits(float(inches_val), UnitTypeId.Inches)
    except:
        return float(inches_val) / 12.0


def ask_num(prompt, default_str):
    msg = "{}\n(Leave blank for default: {})".format(prompt, default_str)
    val = forms.ask_for_string(msg)
    if val is None:
        return None
    val = val.strip()
    if val == "":
        val = default_str
    return val


def ensure_length_param(fm, name, is_instance=True):
    existing = fm.get_Parameter(name)
    if existing:
        return existing
    if not HAS_NEW_PARAMS_API:
        raise Exception("This script expects Revit 2022+ API (SpecTypeId).")
    return fm.AddParameter(name, GroupTypeId.Geometry, SpecTypeId.Length, is_instance)


def ensure_current_type(fm):
    """
    Ensure FamilyManager has a CurrentType.
    Some templates open without an active type => fm.Set crashes.
    """
    try:
        ct = fm.CurrentType
        if ct:
            return ct
    except:
        pass

    # If no current type, try to create one
    # NewType returns a FamilyType and sets it current in most cases
    try:
        newt = fm.NewType("Default")
        try:
            fm.CurrentType = newt
        except:
            pass
        return newt
    except:
        # If "Default" exists, try setting it
        try:
            types = fm.Types  # FamilyTypeSet
            for t in types:
                if t.Name == "Default":
                    fm.CurrentType = t
                    return t
        except:
            pass

    raise Exception("Could not create or set a current family type. Try a different .rft template.")


# --------------------------
# Inputs
# --------------------------
width_in = ask_num("Slat width (in)", "1")
gap_in   = ask_num("Gap between slats (in)", "2")
depth_in = ask_num("Slat depth/height (in)", "4")
len_in   = ask_num("Panel length (in)", "96")
count_s  = ask_num("Slat count (integer)", "20")

if not all([width_in, gap_in, depth_in, len_in, count_s]):
    raise Exception("Cancelled.")

try:
    width_in = float(width_in)
    gap_in   = float(gap_in)
    depth_in = float(depth_in)
    len_in   = float(len_in)
    count    = int(float(count_s))
except:
    raise Exception("Invalid input. Please enter numeric values (count must be integer).")

if count < 1:
    raise Exception("Slat count must be >= 1")

template_path = forms.pick_file(
    file_ext='rft',
    title="Pick FAMILY TEMPLATE (.rft) - 'Generic Model face based.rft'"
)
if not template_path:
    raise Exception("Cancelled (no template selected).")

save_path = forms.save_file(
    file_ext='rfa',
    title="Save generated slat family as..."
)
if not save_path:
    raise Exception("Cancelled (no save path).")


# --------------------------
# Create family doc
# --------------------------
famdoc = app.NewFamilyDocument(template_path)

t = Transaction(famdoc, "Generate Slat Ceiling Panel")
t.Start()

fm = famdoc.FamilyManager

# ✅ CRITICAL: ensure a family type exists before fm.Set
ensure_current_type(fm)

# Family parameters (SAFE: Length only)
p_slat_w = ensure_length_param(fm, "Slat_Width", True)
p_gap    = ensure_length_param(fm, "Slat_Gap", True)
p_depth  = ensure_length_param(fm, "Slat_Depth", True)
p_len    = ensure_length_param(fm, "Panel_Length", True)

# Set defaults
fm.Set(p_slat_w, inches_to_internal(width_in))
fm.Set(p_gap,    inches_to_internal(gap_in))
fm.Set(p_depth,  inches_to_internal(depth_in))
fm.Set(p_len,    inches_to_internal(len_in))

# Runtime values
W = inches_to_internal(width_in)
G = inches_to_internal(gap_in)
D = inches_to_internal(depth_in)
L = inches_to_internal(len_in)
module = W + G

# Sketch plane at origin
plane = Plane.CreateByNormalAndOrigin(XYZ.BasisZ, XYZ(0, 0, 0))
sketch = SketchPlane.Create(famdoc, plane)

# Slat profile rectangle
p0 = XYZ(0, 0, 0)
p1 = XYZ(W, 0, 0)
p2 = XYZ(W, L, 0)
p3 = XYZ(0, L, 0)

curves = CurveArray()
curves.Append(Line.CreateBound(p0, p1))
curves.Append(Line.CreateBound(p1, p2))
curves.Append(Line.CreateBound(p2, p3))
curves.Append(Line.CreateBound(p3, p0))

profile = CurveArrArray()
profile.Append(curves)

# Extrusion
slat = famdoc.FamilyCreate.NewExtrusion(True, profile, sketch, D)

# Copy across X
for i in range(1, count):
    delta = XYZ(module * i, 0, 0)
    ElementTransformUtils.CopyElement(famdoc, slat.Id, delta)

t.Commit()

# Save + close
so = SaveAsOptions()
so.OverwriteExistingFile = True
famdoc.SaveAs(save_path, so)
famdoc.Close(False)

forms.alert(u"✅ Done!\nSaved family to:\n{}".format(save_path), title="Generate Slat Family")
