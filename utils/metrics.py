"""Training metrics: TSS, IF, zones, CTL/ATL/TSB."""
from datetime import date, datetime, timedelta

import pandas as pd


# ── Zone definitions ──────────────────────────────────────────────────────────

POWER_ZONES = [
    (0,    0.55, "Z1 Récup",     "#4FC3F7"),
    (0.55, 0.75, "Z2 Endurance", "#81C784"),
    (0.75, 0.90, "Z3 Tempo",     "#FFD54F"),
    (0.90, 1.05, "Z4 Seuil",     "#FF8A65"),
    (1.05, 1.20, "Z5 VO2max",    "#E57373"),
    (1.20, 9.99, "Z6 Anaérobie", "#CE93D8"),
]

HR_ZONES = [
    (0,    0.60, "Z1 Récup",     "#4FC3F7"),
    (0.60, 0.70, "Z2 Endurance", "#81C784"),
    (0.70, 0.80, "Z3 Aérobie",   "#FFD54F"),
    (0.80, 0.90, "Z4 Seuil",     "#FF8A65"),
    (0.90, 1.00, "Z5 VO2max",    "#E57373"),
]


def power_zone(np_w: float, ftp: int) -> tuple[int, str, str]:
    pct = np_w / ftp
    for i, (lo, hi, label, color) in enumerate(POWER_ZONES, 1):
        if lo <= pct < hi:
            return i, label, color
    return 6, "Z6 Anaérobie", "#CE93D8"


def hr_zone(avg_hr: float, hr_max: int) -> tuple[int, str, str]:
    pct = avg_hr / hr_max
    for i, (lo, hi, label, color) in enumerate(HR_ZONES, 1):
        if lo <= pct < hi:
            return i, label, color
    return 5, "Z5 VO2max", "#E57373"


# ── Core metrics ──────────────────────────────────────────────────────────────

def calc_tss(duration_s: int, np_w: float, ftp: int) -> float:
    IF = np_w / ftp
    return (duration_s * np_w * IF) / (ftp * 3600) * 100


def calc_if(np_w: float, ftp: int) -> float:
    return np_w / ftp


def fmt_duration(s: int) -> str:
    h, m = divmod(s // 60, 60)
    return f"{h}h{m:02d}"


def parse_activity(a: dict, ftp: int, hr_max: int) -> dict | None:
    """Extract and enrich a single Strava activity dict."""
    if a.get("type") not in ("Ride", "VirtualRide"):
        return None
    if not a.get("device_watts") or not a.get("weighted_average_watts"):
        return None

    np_w = a["weighted_average_watts"]
    dur = a["moving_time"]
    dist_km = a["distance"] / 1000
    elev = a.get("total_elevation_gain", 0)
    avg_hr = a.get("average_heartrate")
    max_hr_val = a.get("max_heartrate")
    avg_w = a.get("average_watts", 0)
    cadence = a.get("average_cadence")

    tss = calc_tss(dur, np_w, ftp)
    IF = calc_if(np_w, ftp)
    speed = dist_km / (dur / 3600)
    vi = np_w / avg_w if avg_w > 0 else None

    pz_num, pz_label, pz_color = power_zone(np_w, ftp)
    hrz_num, hrz_label, hrz_color = hr_zone(avg_hr, hr_max) if avg_hr else (0, "—", "#888")

    eff = np_w / avg_hr if avg_hr else None

    start = datetime.fromisoformat(a["start_date_local"].replace("Z", ""))

    return {
        "id": a["id"],
        "date": start.date(),
        "datetime": start,
        "name": a["name"],
        "dist_km": round(dist_km, 1),
        "duration_s": dur,
        "duration_fmt": fmt_duration(dur),
        "elev": int(elev),
        "avg_w": round(avg_w, 1),
        "np": np_w,
        "tss": round(tss),
        "IF": round(IF, 3),
        "speed": round(speed, 1),
        "avg_hr": avg_hr,
        "max_hr": max_hr_val,
        "hr_pct": round(avg_hr / hr_max * 100, 1) if avg_hr else None,
        "cadence": cadence,
        "vi": round(vi, 3) if vi else None,
        "eff": round(eff, 3) if eff else None,
        "pz_num": pz_num, "pz_label": pz_label, "pz_color": pz_color,
        "hrz_num": hrz_num, "hrz_label": hrz_label, "hrz_color": hrz_color,
        "athletes": a.get("athlete_count", 1),
        "prs": a.get("pr_count", 0),
        "max_w": a.get("max_watts", 0),
        "np_pct": round(np_w / ftp * 100),
    }


def build_dataframe(activities: list[dict], ftp: int, hr_max: int) -> pd.DataFrame:
    rows = []
    for a in activities:
        parsed = parse_activity(a, ftp, hr_max)
        if parsed:
            rows.append(parsed)
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values("date", ascending=False).reset_index(drop=True)


# ── CTL / ATL / TSB (PMC) ────────────────────────────────────────────────────

def compute_pmc(df: pd.DataFrame) -> pd.DataFrame:
    """Compute Performance Management Chart (CTL, ATL, TSB)."""
    if df.empty:
        return pd.DataFrame()

    today = date.today()
    start = df["date"].min() - timedelta(days=7)
    date_range = pd.date_range(start, today, freq="D").date

    # Daily TSS
    daily = df.groupby("date")["tss"].sum().reindex(date_range, fill_value=0)

    ctl = 0.0  # 42-day exp average
    atl = 0.0  # 7-day exp average
    k_ctl = 1 / 42
    k_atl = 1 / 7

    records = []
    for d, tss_val in daily.items():
        ctl = ctl + (tss_val - ctl) * k_ctl
        atl = atl + (tss_val - atl) * k_atl
        tsb = ctl - atl
        records.append({"date": d, "tss": tss_val, "ctl": round(ctl, 1),
                         "atl": round(atl, 1), "tsb": round(tsb, 1)})

    return pd.DataFrame(records)
