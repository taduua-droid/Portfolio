"""
run_edit_checks.py
Offline edit checks for the YKP3089C017 mock study.

Implements every programmed check and review listing in YKP3089C017_DM_Spec_v0.1,
plus two amendments found while building the test data:
  1. SZ06 anchors the baseline on the Visit 1 (consent) date, because the listing
     runs before randomization exists.
  2. Baseline = all diary days before randomization (not a fixed Day -56), because
     a delayed Visit 3 makes baseline longer than 56 days. Inclusion 6 is still
     checked on the first 56 days from Visit 1 (two 28-day segments), because the
     protocol writes the criterion against an 8-week baseline. Days 57 onward stay
     in baseline but do not count toward eligibility.

Usage:
    python run_edit_checks.py <study_data.xlsx> <discrepancy_listing.xlsx> [YYYY-MM-DD]

The optional date is "today" for DM04 (defaults to the real current date).
All data is synthetic. No real subject data.
"""
import sys
import datetime as dt
import pandas as pd

COUNT_FIELDS = ["SZSPM", "SZSPNM", "SZCP", "SZSG"]
ELIG_DAYS = 56     # Inclusion 6 is written against an 8-week baseline
SEGMENT_DAYS = 28  # ...split into two consecutive 4-week segments
CRITERIA = ["AESDTH", "AESLIFE", "AESHOSP", "AESDISAB", "AESCONG", "AESMIE"]


def fmt(d):
    """Format a date the way the spec does: DD-MMM-YYYY."""
    return pd.Timestamp(d).strftime("%d-%b-%Y").upper() if pd.notna(d) else "(blank)"


def load(path):
    """Read the three forms. IDs stay text so leading zeros survive."""
    ids = {"SUBJID": str, "SITEID": str}
    dm = pd.read_excel(path, sheet_name="DM", dtype=ids)
    sz = pd.read_excel(path, sheet_name="SZ", dtype=ids)
    ae = pd.read_excel(path, sheet_name="AE", dtype=ids)
    for df, cols in [(dm, ["RFICDAT", "BRTHDAT", "RANDDAT", "EXSTDAT"]),
                     (sz, ["VISDAT", "SZDAT"]),
                     (ae, ["AESTDAT", "AEENDAT"])]:
        for c in cols:
            df[c] = pd.to_datetime(df[c])
    return dm, sz, ae


class Listing:
    """Collects one row per check hit."""
    def __init__(self, dm):
        self.rows = []
        self.site = dict(zip(dm.SUBJID, dm.SITEID))

    def add(self, check, severity, sid, form, record, field, value, text, kind="Query"):
        self.rows.append({
            "Check ID": check, "Hard / Soft": severity, "SUBJID": sid,
            "SITEID": self.site.get(sid), "Form": form, "Record": record,
            "Field(s)": field, "Value Found": value, "Query Text": text, "Action Type": kind})

    def frame(self):
        cols = ["Check ID", "Hard / Soft", "SUBJID", "SITEID", "Form", "Record",
                "Field(s)", "Value Found", "Query Text", "Action Type"]
        return pd.DataFrame(self.rows, columns=cols).sort_values(["Check ID", "SUBJID"]).reset_index(drop=True)


# ---------------------------------------------------------------- DM checks
def dm_checks(dm, out, today):
    for _, r in dm.iterrows():
        sid = r.SUBJID
        if r.AGE < 18 or r.AGE > 70:
            out.add("DM01", "Soft", sid, "DM", "Demographics", "AGE", str(r.AGE),
                    f"Age at consent ({r.AGE}) is outside the protocol range of 18-70 years (Inclusion 1). "
                    "Please verify date of birth and date of consent against source.")
        if len(sid) != 8 or not sid.isdigit() or sid[2:5] != r.SITEID:
            out.add("DM02", "Hard", sid, "DM", "Demographics", "SUBJID, SITEID", f"SITEID {r.SITEID}",
                    "Screening number must be 8 digits, with digits 3-5 matching the site number. Please correct.")
        if (r.SEX == "F" and pd.isna(r.CHILDPOT)) or (r.SEX == "M" and pd.notna(r.CHILDPOT)):
            out.add("DM03", "Hard", sid, "DM", "Demographics", "SEX, CHILDPOT",
                    f"SEX {r.SEX}, CHILDPOT {r.CHILDPOT if pd.notna(r.CHILDPOT) else '(blank)'}",
                    "Childbearing potential must be answered for female subjects and left blank for male subjects. Please review.")
        if r.BRTHDAT >= r.RFICDAT or r.RFICDAT > today:
            out.add("DM04", "Hard", sid, "DM", "Demographics", "BRTHDAT, RFICDAT",
                    f"{fmt(r.BRTHDAT)} / {fmt(r.RFICDAT)}",
                    "Date of birth is on or after the consent date, or the consent date is in the future. Please verify against source.")
        if pd.notna(r.RANDDAT):
            gap = (r.RANDDAT - r.RFICDAT).days
            if gap <= 0 or gap < 54 or gap > 58:
                out.add("DM05", "Hard" if gap <= 0 else "Soft", sid, "DM", "Demographics", "RFICDAT, RANDDAT",
                        f"{gap} days",
                        f"Randomization date is {gap} days after informed consent. The protocol specifies an 8-week "
                        "baseline (Visit 1, Day -56 to Visit 3, Day 1, +/-2 days). Please verify both dates.")
            expected = r.RANDDAT if r.FDOSSITE == "Y" else r.RANDDAT + pd.Timedelta(days=1)
            if r.EXSTDAT != expected:
                lag = (r.EXSTDAT - r.RANDDAT).days
                out.add("DM06", "Soft", sid, "DM", "Demographics", "RANDDAT, EXSTDAT, FDOSSITE",
                        f"First dose {lag} day(s) after randomization; FDOSSITE {r.FDOSSITE}",
                        f"Date of first dose is {lag} day(s) after randomization. Per protocol, dosing begins the morning "
                        "after randomization, or on Day 1 if given at the site. Please verify.")


# ---------------------------------------------------------------- SZ checks
def sz_checks(sz, dm, out):
    consent = dict(zip(dm.SUBJID, dm.RFICDAT))
    rand = dict(zip(dm.SUBJID, dm.RANDDAT))

    for _, r in sz.iterrows():
        sid, day = r.SUBJID, fmt(r.SZDAT)
        blank = [c for c in COUNT_FIELDS if pd.isna(r[c])]
        filled = [c for c in COUNT_FIELDS if pd.notna(r[c])]
        if (r.SZDIARY == "Y" and blank) or (r.SZDIARY == "N" and filled):
            state = f"missing ({', '.join(blank)})" if r.SZDIARY == "Y" else "entered"
            out.add("SZ01", "Hard", sid, "SZ", f"SZDAT {day}", "SZDIARY, counts",
                    f"SZDIARY {r.SZDIARY}; counts {state}",
                    f"Diary data recorded for this day is {r.SZDIARY}, but the seizure counts are {state}. "
                    "Please review against the diary page.")
        if r.SZDAT < consent[sid] or r.SZDAT > r.VISDAT:
            out.add("SZ03", "Hard", sid, "SZ", f"SZDAT {day}", "SZDAT, VISDAT",
                    f"SZDAT {day}; diary returned {fmt(r.VISDAT)}",
                    "Diary date is before informed consent or after the visit at which the diary was returned. "
                    "Please verify the date against the diary.")
        for c in filled:
            if r[c] > 20:
                out.add("SZ04", "Soft", sid, "SZ", f"SZDAT {day}", c, str(int(r[c])),
                        f"{int(r[c])} seizures ({c}) are recorded on {day}. Please confirm against the source diary.")

    dupes = sz.groupby(["SUBJID", "SZDAT"]).size()
    for (sid, d), n in dupes[dupes > 1].items():
        out.add("SZ02", "Hard", sid, "SZ", f"SZDAT {fmt(d)}", "SUBJID, SZDAT", f"{n} records",
                "A diary record already exists for this date. Please remove the duplicate or correct the date.")

    for sid, g in sz.groupby("SUBJID"):
        # SZ05: every day from Visit 1 to the day before the latest diary return
        expected = pd.date_range(consent[sid], g.VISDAT.max() - pd.Timedelta(days=1))
        missing = expected.difference(pd.DatetimeIndex(g.SZDAT))
        if len(missing):
            # report each run of consecutive missing days as one hit
            runs, start = [], missing[0]
            for prev, cur in zip(missing[:-1], missing[1:]):
                if (cur - prev).days > 1:
                    runs.append((start, prev)); start = cur
            runs.append((start, missing[-1]))
            for a, b in runs:
                span = fmt(a) if a == b else f"{fmt(a)} to {fmt(b)}"
                out.add("SZ05", "Soft", sid, "SZ", span, "SZDAT", f"{(b - a).days + 1} day(s) missing",
                        f"No diary record exists for {span}. Please enter the diary data, or enter records with "
                        "'diary data recorded' = No if the diary was not completed for those days.")

        # SZ06: baseline eligibility (amended: anchor on Visit 1, end the day before randomization/Visit 3)
        if pd.notna(rand[sid]):
            end = rand[sid]
        else:
            v3 = g.loc[g.VISIT == "VISIT 3", "VISDAT"]
            end = v3.iloc[0] if len(v3) else g.VISDAT.max()
        base = (g[(g.SZDAT >= consent[sid]) & (g.SZDAT < end)]
                .drop_duplicates("SZDAT").set_index("SZDAT")
                .reindex(pd.date_range(consent[sid], end - pd.Timedelta(days=1))))
        counts = base.SZCOUNT  # NaN = no usable data for that day
        # Eligibility window: the first 56 days from Visit 1. A late Visit 3 adds
        # baseline days, but they do not extend the second 4-week segment.
        window = counts.iloc[:ELIG_DAYS]
        late = counts.iloc[ELIG_DAYS:]                 # Day 57 onward, if any
        half1 = window.iloc[:SEGMENT_DAYS].sum()       # days 1-28
        half2 = window.iloc[SEGMENT_DAYS:].sum()       # days 29-56
        longest = run = 0
        for x in window:  # longest run of recorded seizure-free days
            run = run + 1 if x == 0 else 0
            longest = max(longest, run)
        fails = []
        if half1 + half2 < 8: fails.append(f"total {int(half1 + half2)} < 8")
        if half1 < 3: fails.append(f"weeks 1-4 = {int(half1)} < 3")
        if half2 < 3: fails.append(f"weeks 5-8 = {int(half2)} < 3")
        if longest > 25: fails.append(f"seizure-free run of {longest} days > 25")
        if fails and len(late):  # tell the reviewer what was left out of the count
            fails.append(f"{int(late.sum())} seizure(s) on {len(late)} baseline day(s) after Day 56 not counted")
        if fails:
            randomized = pd.notna(rand[sid])
            out.add("SZ06", "Soft", sid, "SZ", "Baseline period", "SZCOUNT (derived)", "; ".join(fails),
                    "Per the diary data entered, the subject does not appear to meet the baseline seizure criteria "
                    f"(Inclusion 6): {'; '.join(fails)}. Please verify the diary entries against source.",
                    kind="Query" if randomized else "Listing review (not randomized)")


# ---------------------------------------------------------------- AE checks
def ae_checks(ae, dm, out):
    m = ae.merge(dm[["SUBJID", "RFICDAT", "RANDDAT", "EXSTDAT"]], on="SUBJID", how="left")
    for _, r in m.iterrows():
        sid, rec = r.SUBJID, f"AESPID {r.AESPID}: {r.AETERM}"
        if pd.notna(r.AEENDAT) and r.AEENDAT < r.AESTDAT:
            out.add("AE01", "Hard", sid, "AE", rec, "AESTDAT, AEENDAT", f"{fmt(r.AESTDAT)} / {fmt(r.AEENDAT)}",
                    "AE end date is before the start date. Please verify both dates against source.")
        if (r.AEONGO == "Y" and pd.notna(r.AEENDAT)) or (r.AEONGO == "N" and pd.isna(r.AEENDAT)):
            out.add("AE02", "Hard", sid, "AE", rec, "AEONGO, AEENDAT", f"AEONGO {r.AEONGO}; end {fmt(r.AEENDAT)}",
                    "The ongoing status, end date and outcome for this event are inconsistent. Please review.")
        if (r.AEONGO == "Y" and r.AEOUT in ("RECOVERED/RESOLVED", "RECOVERED/RESOLVED WITH SEQUELAE", "FATAL")) or \
           (r.AEONGO == "N" and r.AEOUT in ("NOT RECOVERED/NOT RESOLVED", "RECOVERING/RESOLVING")):
            out.add("AE02", "Soft", sid, "AE", rec, "AEONGO, AEOUT", f"AEONGO {r.AEONGO}; outcome {r.AEOUT}",
                    "The ongoing status, end date and outcome for this event are inconsistent. Please review.")
        flags = [r[c] for c in CRITERIA]
        if (r.AESER == "Y" and "Y" not in flags) or (r.AESER == "N" and "Y" in flags):
            out.add("AE03", "Hard", sid, "AE", rec, "AESER, criteria", f"AESER {r.AESER}",
                    "This event's seriousness and seriousness criteria are inconsistent. Please review.")
        if r.AESTDAT < r.RFICDAT:
            out.add("AE04", "Soft", sid, "AE", rec, "AESTDAT", f"{(r.RFICDAT - r.AESTDAT).days} days before consent",
                    "AE start date is before informed consent. Please verify the start date, or confirm whether this "
                    "condition should be recorded as medical history.")
        if pd.notna(r.EXSTDAT) and r.AESTDAT < r.EXSTDAT and r.AEREL != "UNRELATED":
            out.add("AE05", "Soft", sid, "AE", rec, "AESTDAT, AEREL", f"Before first dose; AEREL {r.AEREL}",
                    f"This event started before the first dose of study drug, and relationship is recorded as {r.AEREL}. "
                    "Please review the relationship assessment per protocol section 10.3.")
        if any(w in str(r.AETERM).upper() for w in ("SEIZURE", "CONVULSION", "STATUS EPILEPTICUS")):
            out.add("AE06", "Soft", sid, "AE", rec, "AETERM", r.AETERM,
                    "Seizures are normally recorded in the seizure diary. Please confirm this event meets the AE "
                    "definition in protocol section 10.4.1 (a measurable increase in frequency or duration, or a "
                    "pattern distinguishable from the subject's usual seizures).")
        if r.AEOUT == "FATAL" and (r.AESER != "Y" or r.AESDTH != "Y"):
            out.add("AE07", "Hard", sid, "AE", rec, "AEOUT, AESER, AESDTH", "FATAL",
                    "Outcome is Fatal, but the event is not marked serious with 'results in death'. Please review.")
        if r.AEACN == "DOSE REDUCED" and pd.notna(r.RANDDAT):
            study_day = (r.AESTDAT - r.RANDDAT).days + 1
            if 2 <= study_day <= 8 or study_day >= 58:
                out.add("ML01", "-", sid, "AE", rec, "AEACN, AESTDAT", f"Dose reduced; AE start Study Day {study_day}",
                        "Reviewer: confirm the reduction date from dosing records. Reductions in Week 1 or after "
                        "Week 8 are not permitted.", kind="Listing review")


def main():
    data_path, out_path = sys.argv[1], sys.argv[2]
    today = pd.Timestamp(sys.argv[3]) if len(sys.argv) > 3 else pd.Timestamp(dt.date.today())
    dm, sz, ae = load(data_path)
    out = Listing(dm)
    dm_checks(dm, out, today)
    sz_checks(sz, dm, out)
    ae_checks(ae, dm, out)
    listing = out.frame()
    listing.to_excel(out_path, index=False)
    print(f"{len(listing)} hits written to {out_path}")
    print(listing.groupby(["Check ID", "Action Type"]).size().to_string())


if __name__ == "__main__":
    main()
