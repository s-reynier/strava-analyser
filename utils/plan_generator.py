"""Training plan generator."""
from dataclasses import dataclass, field
from datetime import date, timedelta

WEEKDAYS_FR = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]

EMOJIS = {
    "rest":     "🛌",
    "z1":       "🚴",
    "z2":       "🚴",
    "tempo":    "🚴",
    "threshold":"🚴",
    "vo2":      "🚴",
    "long":     "🚴",
    "race":     "⚡",
    "target":   "🏆",
    "gym_force":"🏋️",
    "gym_act":  "🏋️",
    "gym_mob":  "🧘",
}


@dataclass
class Session:
    type: str          # rest | z1 | z2 | tempo | threshold | vo2 | long | gym_force | gym_act | gym_mob | race | target
    title: str
    detail: str
    duration_min: int = 0
    tss: int = 0
    np_target: str = ""
    hr_target: str = ""
    emoji: str = ""

    def __post_init__(self):
        if not self.emoji:
            self.emoji = EMOJIS.get(self.type, "📅")

    @property
    def label(self) -> str:
        return f"{self.emoji} {self.title}"


@dataclass
class DayPlan:
    date: date
    session: Session

    @property
    def weekday_fr(self) -> str:
        return WEEKDAYS_FR[self.date.weekday()]

    @property
    def date_str(self) -> str:
        return self.date.strftime("%d/%m")


@dataclass
class WeekPlan:
    week_num: int
    start_date: date
    phase: str
    days: list[DayPlan] = field(default_factory=list)

    @property
    def total_tss(self) -> int:
        return sum(d.session.tss for d in self.days)

    @property
    def label(self) -> str:
        return f"Semaine {self.week_num} — {self.phase} ({self.start_date.strftime('%d/%m')})"


# ── Session templates ─────────────────────────────────────────────────────────

def make_rest() -> Session:
    return Session("rest", "Repos", "Récupération complète", 0, 0)

def make_walk() -> Session:
    return Session("z1", "Repos actif / marche", "30min de marche, aucun effort vélo.", 30, 10)

def make_z1(ftp: int) -> Session:
    return Session("z1", "Z1 – Récup active",
                   f"30-45min. NP < {int(ftp*0.55)}W. BPM < 110. Cadence 85rpm.",
                   40, 15, f"< {int(ftp*0.55)}W")

def make_z2(ftp: int, hr_max: int, duration_min: int = 75) -> Session:
    tss = int(duration_min * 0.5)
    return Session("z2", f"Z2 – Endurance ({duration_min}min)",
                   f"{duration_min}min. NP {int(ftp*0.60)}-{int(ftp*0.72)}W. BPM 115-130. Cadence 80-85rpm.",
                   duration_min, tss,
                   f"{int(ftp*0.60)}-{int(ftp*0.72)}W", "115-130")

def make_tempo(ftp: int, intervals: str = "2×15min", pct: float = 0.85) -> Session:
    target = int(ftp * pct)
    tss = 90
    return Session("tempo", f"Tempo – {intervals} @ {int(pct*100)}% FTP",
                   f"1h15. Échauffement 15min Z1. {intervals} @ {target}W. Récup 5min entre. Retour Z1.",
                   75, tss, f"{target}W", "148-158")

def make_threshold(ftp: int, intervals: str = "2×10min") -> Session:
    target = int(ftp * 0.97)
    return Session("threshold", f"Seuil – {intervals} @ 97% FTP",
                   f"1h10. Écha 15min. {intervals} @ {target}W. Récup 5min. Retour Z1.",
                   70, 95, f"{target}W", "158-168")

def make_vo2(ftp: int, intervals: str = "4×4min") -> Session:
    target = int(ftp * 1.10)
    return Session("vo2", f"VO2max – {intervals} @ 110% FTP",
                   f"1h. Écha 15min. {intervals} @ {target}W. Récup 4min. Retour Z1.",
                   60, 85, f"{target}W", "> 165")

def make_sharpening(ftp: int) -> Session:
    """Short intense session for taper."""
    target = int(ftp * 1.05)
    return Session("vo2", "Vivacité – 4×1min @ 105% FTP",
                   f"1h. Écha 20min. 4×1min @ {target}W. Récup 3min. Retour Z1. Court mais vif.",
                   60, 50, f"{target}W", "")

def make_activation(ftp: int) -> Session:
    target = int(ftp * 0.90)
    return Session("z2", "Activation pré-course",
                   f"30min max. Cadence haute 90-95rpm. 3×1min @ {target}W. Récup 2min. Confirmer les sensations.",
                   30, 25, f"{target}W", "")

def make_long(ftp: int, hr_max: int, hours: float = 2.5, with_col: bool = False) -> Session:
    target_lo = int(ftp * 0.65)
    target_hi = int(ftp * 0.78)
    duration_min = int(hours * 60)
    tss = int(hours * 60 * 0.65)
    col_note = " Inclure 1 col ou montée si possible." if with_col else ""
    return Session("long", f"Longue sortie – {int(hours)}h{'30' if hours%1 else ''}",
                   f"{duration_min}min. Z2/Z3 majoritairement. NP {target_lo}-{target_hi}W. BPM < 150.{col_note} Finir en ayant encore de l'énergie.",
                   duration_min, tss, f"{target_lo}-{target_hi}W", "< 150")

def make_gym_force() -> Session:
    return Session("gym_force", "Muscu – Force",
                   "Squat barre 4×8 @ 70-75% 1RM · Romanian DL 3×10 · Leg press unilatéral 3×12 · Hip thrust 3×12 · Step-up 3×10 · Planche 3×45s. 65-70min.",
                   70, 20)

def make_gym_act() -> Session:
    return Session("gym_act", "Muscu – Activation",
                   "Goblet squat 3×15 (léger) · Fentes marchées 3×10 · Hip thrust 3×15 · Planche 3×45s · Dead bug 3×10 · Mobilité hanches 10min. 45min.",
                   45, 10)

def make_gym_mob() -> Session:
    return Session("gym_mob", "Mobilité / Étirements",
                   "Foam roller jambes 10min · Stretching quad/ischio/mollets 2×30s · Mobilité hanches (pigeon, 90/90) 10min. 30min. Aucune charge.",
                   30, 5)

def make_race(name: str, detail: str, tss: int = 55) -> Session:
    return Session("race", f"⚡ COURSE — {name}", detail, 35, tss)

def make_target(name: str, detail: str) -> Session:
    return Session("target", f"🏆 OBJECTIF — {name}", detail, 0, 0)


# ── Plan generation ───────────────────────────────────────────────────────────

@dataclass
class RaceEvent:
    name: str
    date: date
    distance_km: float
    elevation_m: int
    is_target: bool = True  # False = intermediate race


@dataclass
class PlanConfig:
    ftp: int
    hr_max: int
    available_weekdays: list[int]  # 0=Mon … 6=Sun
    has_gym: bool
    weekend_ride_day: int          # 5=Sat or 6=Sun
    races: list[RaceEvent]
    current_weekly_tss: float = 200.0


def generate_plan(config: PlanConfig) -> list[WeekPlan]:
    today = date.today()
    target = next((r for r in sorted(config.races, key=lambda r: r.date) if r.is_target), None)
    if not target:
        return []

    weeks_to_race = max(1, (target.date - today).days // 7)

    # ── Phase assignment ────────────────────────────────────────────────────
    if weeks_to_race >= 8:
        phases = (["recovery"] + ["build"] * 3 + ["build_peak"]
                  + ["peak"] * (weeks_to_race - 6) + ["taper", "race_week"])
    elif weeks_to_race >= 5:
        phases = ["recovery", "build", "build_peak", "peak", "taper", "race_week"][:(weeks_to_race + 1)]
        phases = phases[:weeks_to_race] + ["race_week"]
    elif weeks_to_race >= 3:
        phases = ["build", "taper", "race_week"]
    elif weeks_to_race == 2:
        phases = ["taper", "race_week"]
    else:
        phases = ["race_week"]

    phases = phases[:weeks_to_race]
    if phases[-1] != "race_week":
        phases[-1] = "race_week"

    # ── Build weekly plans ──────────────────────────────────────────────────
    weeks = []
    for w_idx, phase in enumerate(phases):
        week_start = today + timedelta(weeks=w_idx)
        week = WeekPlan(w_idx + 1, week_start, _phase_label(phase))
        _fill_week(week, phase, config, target, w_idx == len(phases) - 1)
        weeks.append(week)

    return weeks


def _phase_label(phase: str) -> str:
    return {
        "recovery":   "Récupération",
        "build":      "Construction",
        "build_peak": "Construction / Pic",
        "peak":       "Pic de forme",
        "taper":      "Affûtage",
        "race_week":  "Semaine de course",
    }.get(phase, phase)


def _fill_week(week: WeekPlan, phase: str, cfg: PlanConfig,
               target: RaceEvent, is_last_week: bool) -> None:
    ftp, hr = cfg.ftp, cfg.hr_max
    week_start = week.start_date

    # intermediate races this week
    mid_races = {r.date: r for r in cfg.races if not r.is_target
                 and week_start <= r.date < week_start + timedelta(days=7)}
    target_in_week = target.date >= week_start and target.date < week_start + timedelta(days=7)

    for offset in range(7):
        d = week_start + timedelta(days=offset)
        wd = d.weekday()  # 0=Mon

        # Fixed events
        if d in mid_races:
            r = mid_races[d]
            est_tss = int(r.distance_km * 0.5)
            s = make_race(r.name, f"{r.distance_km:.0f}km / +{r.elevation_m}m", est_tss)
            week.days.append(DayPlan(d, s))
            continue

        if d == target.date:
            s = make_target(target.name,
                            f"{target.distance_km:.0f}km / +{target.elevation_m}m D+. Objectif principal.")
            week.days.append(DayPlan(d, s))
            continue

        # Race week: most days rest/easy except activation day before
        if is_last_week:
            days_before = (target.date - d).days
            if days_before == 1:
                s = make_activation(ftp)
            elif days_before <= 5 and wd in cfg.available_weekdays:
                s = make_sharpening(ftp) if days_before == 5 else make_z1(ftp)
            elif days_before == 6 and cfg.has_gym:
                s = make_gym_mob()
            else:
                s = make_rest()
            week.days.append(DayPlan(d, s))
            continue

        # Weekend long ride
        if wd == cfg.weekend_ride_day:
            if phase == "recovery":
                s = make_z2(ftp, hr, 90)
            elif phase in ("build", "build_peak"):
                s = make_long(ftp, hr, 2.5, with_col=True)
            elif phase == "peak":
                s = make_long(ftp, hr, 3.0, with_col=True)
            elif phase == "taper":
                s = make_z2(ftp, hr, 90)
            else:
                s = make_rest()
            week.days.append(DayPlan(d, s))
            continue

        # Other weekend day: rest
        if wd in (5, 6) and wd != cfg.weekend_ride_day:
            week.days.append(DayPlan(d, make_rest()))
            continue

        # Weekday — only on available days
        if wd not in cfg.available_weekdays:
            week.days.append(DayPlan(d, make_rest()))
            continue

        # Available weekday — assign sessions based on phase
        s = _assign_weekday_session(wd, phase, cfg, ftp, hr)
        week.days.append(DayPlan(d, s))


def _assign_weekday_session(wd: int, phase: str, cfg: PlanConfig, ftp: int, hr: int) -> Session:
    avail = sorted(cfg.available_weekdays)
    pos = avail.index(wd) if wd in avail else 0
    n = len(avail)

    # Distribute: first slot = quality, middle = gym or z2, last = z2/z1
    if phase == "recovery":
        if pos == 0:
            return make_z2(ftp, hr, 60)
        elif cfg.has_gym and pos == 1:
            return make_gym_mob()
        else:
            return make_z1(ftp)

    if phase == "build":
        if pos == 0:
            return make_tempo(ftp, "2×15min", 0.85)
        elif pos == 1:
            return make_gym_force() if cfg.has_gym else make_z2(ftp, hr, 75)
        else:
            return make_z2(ftp, hr, 60)

    if phase == "build_peak":
        if pos == 0:
            return make_tempo(ftp, "2×20min", 0.87)
        elif pos == 1:
            return make_gym_force() if cfg.has_gym else make_threshold(ftp)
        else:
            return make_z2(ftp, hr, 75)

    if phase == "peak":
        if pos == 0:
            return make_threshold(ftp, "2×10min")
        elif pos == 1:
            return make_gym_act() if cfg.has_gym else make_tempo(ftp, "2×15min", 0.85)
        else:
            return make_z2(ftp, hr, 60)

    if phase == "taper":
        if pos == 0:
            return make_sharpening(ftp)
        elif cfg.has_gym and pos == 1:
            return make_gym_act()
        else:
            return make_z1(ftp)

    return make_rest()


# ── Markdown export ───────────────────────────────────────────────────────────

def plan_to_markdown(weeks: list[WeekPlan], config: PlanConfig, target: RaceEvent) -> str:
    lines = [
        f"# Plan d'entraînement — {target.name}",
        f"> FTP : {config.ftp}W · BPM max : {config.hr_max} · Généré le {date.today().strftime('%d/%m/%Y')}",
        "",
        "---",
        "",
        "## Vue d'ensemble",
        "",
        "| Semaine | Dates | Phase | TSS estimé |",
        "|---|---|---|---:|",
    ]
    for w in weeks:
        end = w.start_date + timedelta(days=6)
        lines.append(
            f"| S{w.week_num} | {w.start_date.strftime('%d/%m')} → {end.strftime('%d/%m')} "
            f"| {w.phase} | ~{w.total_tss} |"
        )

    lines += ["", "---", ""]

    for w in weeks:
        lines.append(f"## S{w.week_num} — {w.phase} | TSS ~{w.total_tss}")
        lines.append("")
        lines.append("| Jour | Date | Séance | Détail |")
        lines.append("|---|---|---|---|")
        for dp in w.days:
            lines.append(
                f"| {dp.weekday_fr} | {dp.date_str} | {dp.session.label} | {dp.session.detail} |"
            )
        lines += ["", "---", ""]

    return "\n".join(lines)
