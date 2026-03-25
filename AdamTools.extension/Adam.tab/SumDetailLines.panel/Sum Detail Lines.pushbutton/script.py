# -*- coding: utf-8 -*-
from pyrevit import revit, script
from Autodesk.Revit.DB import DetailCurve

uidoc = revit.uidoc
doc = revit.doc
out = script.get_output()

sel_ids = list(uidoc.Selection.GetElementIds())
if not sel_ids:
    script.exit()

total = 0.0
count = 0

for eid in sel_ids:
    el = doc.GetElement(eid)
    if isinstance(el, DetailCurve):
        crv = el.GeometryCurve
        if crv:
            total += crv.Length
            count += 1


# ---------- CONVERT TO FEET + INCHES (nearest 1/2") ----------

feet = int(total)
inches_decimal = (total - feet) * 12.0

inches = round(inches_decimal * 2) / 2.0

if inches >= 12.0:
    feet += int(inches // 12)
    inches = inches % 12.0


def fmt_inches(in_val):

    whole = int(in_val)
    frac = in_val - whole

    if abs(frac) < 1e-9:
        return '{}"'.format(whole)

    elif abs(frac - 0.5) < 1e-9:

        if whole == 0:
            return '1/2"'

        return '{} 1/2"'.format(whole)

    else:
        return '{:.2f}"'.format(in_val)


formatted = "{}' - {}".format(feet, fmt_inches(inches))


# ---------- OUTPUT ----------

out.print_md("### Sum Detail Lines")

out.print_md("- Count: **{}**".format(count))

out.print_md("- Total: **{}**  ({:.2f} ft)".format(formatted, total))