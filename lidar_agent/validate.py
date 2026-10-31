def remarks(results, minimums=None):
    """key -> remark text for the 'Sugestion /Remarks' column."""
    minimums = minimums or {}
    out = {}
    for k, r in results.items():
        t = []
        if r["conf"] == "na":
            out[k] = ""; continue
        if r["value"] is None:
            t.append("Not auto-measured - measure manually in Potree. " + r["note"])
        else:
            mn = minimums.get(k)
            if mn is not None and r["value"] < mn:
                t.append(f"BELOW MINIMUM {mn} m")
            if r["conf"] == "manual":
                t.append("Adjusted by hand in Potree.")
            elif r["conf"] == "low":
                t.append("Low confidence - verify in Potree. " + r["note"])
            elif r["conf"] == "medium":
                t.append("Auto-measured (medium confidence) - spot check recommended.")
        if k.startswith("cross") and r["value"] is not None and ":" in r["note"]:
            t.insert(0, r["note"].split(":")[0] + ".")            # "Road crossing." / "Power-line crossing."
        out[k] = " ".join(x.strip() for x in t if x.strip())
    return out
