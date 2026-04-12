"""Strava Training Dashboard — multi-user Streamlit app."""
from datetime import date, timedelta

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from utils.metrics import build_dataframe, compute_pmc, POWER_ZONES
from utils.plan_generator import (
    PlanConfig, RaceEvent, generate_plan, plan_to_markdown,
)
from utils.strava import (
    auth_url, exchange_code, save_tokens,
    fetch_athlete, fetch_activities,
    is_authenticated, is_configured, save_config,
    logout, current_token_key,
)

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Strava Training",
    page_icon="🚴",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
  .stMetric label { font-size: 0.75rem !important; color: #888 !important; }
  .block-container { padding-top: 1.5rem !important; }
  h1, h2, h3 { color: #FC4C02 !important; }
  .stTabs [data-baseweb="tab"] { padding: 8px 20px; border-radius: 6px 6px 0 0; }
  .stDataFrame { font-size: 0.82rem; }
</style>
""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# SETUP PAGE — shown when no Strava API credentials are configured
# ═══════════════════════════════════════════════════════════════════════════════
if not is_configured():
    # Auto-detect current app URL from request headers
    try:
        host = st.context.headers.get("host", "localhost:8501")
        scheme = "https" if ("streamlit.app" in host or "443" in host) else "http"
        auto_uri = f"{scheme}://{host}"
    except Exception:
        auto_uri = "http://localhost:8501"

    st.markdown("""
    <div style="max-width:540px; margin:60px auto;">
      <h1 style="font-size:2rem;">🚴 Strava Training — Configuration</h1>
      <p style="color:#888;">
        Pour utiliser cette app, tu as besoin d'une <b>application Strava API</b> gratuite.<br>
        C'est rapide (2 min) et ça reste sur ton compte.
      </p>
    </div>
    """, unsafe_allow_html=True)

    _, col, _ = st.columns([1, 2, 1])
    with col:
        st.info(f"🔗 URL de cette app détectée : **`{auto_uri}`**")

        with st.expander("📋 Comment créer une app Strava API ?", expanded=True):
            st.markdown(f"""
1. Va sur **[strava.com/settings/api](https://www.strava.com/settings/api)**
2. Remplis le formulaire :
   - **Application Name** : ce que tu veux (ex: *My Training App*)
   - **Category** : Training
   - **Website** : `{auto_uri}`
   - **Authorization Callback Domain** : `{auto_uri.split("://")[1]}`
     *(juste le domaine, sans `https://`)*
3. Clique **Create** → copie le **Client ID** et le **Client Secret**
""")

        with st.form("setup_form"):
            st.markdown("#### Tes credentials Strava API")
            cid     = st.text_input("Client ID", placeholder="ex: 112938")
            csecret = st.text_input("Client Secret", placeholder="ex: 3d448a40...", type="password")
            ruri    = st.text_input(
                "Redirect URI",
                value=auto_uri,
                help="Doit être EXACTEMENT l'URL de cette app. Copie-colle la valeur détectée ci-dessus.",
            )
            st.caption(f"⚠️ Le champ **Authorization Callback Domain** dans Strava doit contenir : `{auto_uri.split('://')[1]}`")
            ok = st.form_submit_button("✅ Enregistrer et continuer", use_container_width=True)
            if ok:
                if not cid or not csecret or not ruri:
                    st.error("Tous les champs sont requis.")
                else:
                    save_config(cid, csecret, ruri.rstrip("/"))
                    st.success("Configuration enregistrée !")
                    st.rerun()

        st.caption("🔒 Ces informations restent dans ta session navigateur, jamais stockées sur le serveur.")
    st.stop()


# ═══════════════════════════════════════════════════════════════════════════════
# OAUTH CALLBACK — handle ?code= from Strava redirect
# ═══════════════════════════════════════════════════════════════════════════════
params = st.query_params
if "code" in params and not is_authenticated():
    code = params["code"]
    if params.get("error"):
        st.error("Connexion Strava refusée.")
        st.query_params.clear()
    else:
        with st.spinner("Connexion à Strava…"):
            try:
                token_data = exchange_code(code)
                save_tokens(token_data)
                st.query_params.clear()
                st.rerun()
            except Exception as e:
                st.error(f"Erreur OAuth : {e}")
                st.query_params.clear()


# ═══════════════════════════════════════════════════════════════════════════════
# LOGIN PAGE
# ═══════════════════════════════════════════════════════════════════════════════
if not is_authenticated():
    st.markdown("""
    <div style="max-width:480px; margin:80px auto; text-align:center;">
      <h1 style="font-size:2.5rem; margin-bottom:0.2em;">🚴 Strava Training</h1>
      <p style="color:#888; margin-bottom:2em;">
        Analyse tes sorties et génère ton plan d'entraînement personnalisé.
      </p>
    </div>
    """, unsafe_allow_html=True)

    col = st.columns([1, 2, 1])[1]
    with col:
        st.link_button(
            "🔗 Connecter mon compte Strava",
            url=auth_url(),
            use_container_width=True,
            type="primary",
        )
        st.markdown("""
        <p style="color:#555; font-size:0.8rem; text-align:center; margin-top:1em;">
        L'app accède uniquement à tes activités en lecture seule.<br>
        Aucune donnée n'est stockée — tout reste dans ta session navigateur.
        </p>
        """, unsafe_allow_html=True)
    st.stop()


# ═══════════════════════════════════════════════════════════════════════════════
# AUTHENTICATED APP
# ═══════════════════════════════════════════════════════════════════════════════

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    athlete = fetch_athlete(current_token_key())
    name = f"{athlete.get('firstname', '')} {athlete.get('lastname', '')}".strip()
    city = athlete.get("city", "")
    st.markdown(f"### 👤 {name}")
    if city:
        st.caption(f"📍 {city}")
    st.markdown("---")
    st.markdown("## ⚙️ Configuration")
    ftp    = st.number_input("FTP (W)",    100, 500, 220, 5)
    hr_max = st.number_input("BPM max",    140, 220, 185, 1)
    n_act  = st.slider("Activités à charger", 10, 100, 60, 5)
    st.markdown("---")
    if st.button("🔄 Rafraîchir", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    if st.button("🚪 Déconnexion", use_container_width=True):
        logout()
        st.rerun()

# ── Load data ─────────────────────────────────────────────────────────────────
tok = current_token_key()

with st.spinner("Chargement des activités…"):
    try:
        raw = fetch_activities(tok, n_act)
        df  = build_dataframe(raw, ftp, hr_max)
        pmc = compute_pmc(df) if not df.empty else pd.DataFrame()
    except Exception as e:
        st.error(f"Erreur Strava : {e}")
        st.stop()

if df.empty:
    st.warning("Aucune sortie vélo avec capteur de puissance trouvée.")
    st.stop()

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown(f"# 🚴 Strava Training — {name}")
st.caption(f"{len(df)} sorties avec puissance · FTP {ftp}W · HRmax {hr_max}")
st.markdown("---")

tab_dash, tab_analyse, tab_plan = st.tabs([
    "📊 Tableau de bord",
    "🔍 Analyse des sorties",
    "📅 Plan d'entraînement",
])


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1 — DASHBOARD
# ═══════════════════════════════════════════════════════════════════════════════
with tab_dash:
    today_row = pmc[pmc["date"] == date.today()]
    ctl = float(today_row["ctl"].iloc[0]) if not today_row.empty else 0.0
    atl = float(today_row["atl"].iloc[0]) if not today_row.empty else 0.0
    tsb = float(today_row["tsb"].iloc[0]) if not today_row.empty else 0.0

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("CTL — Forme de base", f"{ctl:.0f}",
              help="42-day exponential average TSS")
    c2.metric("ATL — Fatigue",       f"{atl:.0f}",
              help="7-day exponential average TSS")
    tsb_label = "😴 Reposé" if tsb > 10 else ("⚡ En forme" if tsb > -10 else "😓 Fatigué")
    c3.metric("TSB — Forme du jour", f"{tsb:.0f}", tsb_label)
    c4.metric("TSS 7 jours", f"{df[df['date'] >= date.today()-timedelta(days=7)]['tss'].sum():.0f}")
    c5.metric("TSS 30 jours", f"{df[df['date'] >= date.today()-timedelta(days=30)]['tss'].sum():.0f}")

    st.markdown("---")
    col_l, col_r = st.columns([2, 1])

    with col_l:
        st.markdown("### PMC — 90 derniers jours")
        pmc_90 = pmc[pmc["date"] >= date.today() - timedelta(days=90)].copy()
        pmc_90["date"] = pd.to_datetime(pmc_90["date"])
        fig_pmc = go.Figure()
        fig_pmc.add_trace(go.Bar(
            x=pmc_90["date"], y=pmc_90["tss"],
            name="TSS", marker_color="rgba(255,255,255,0.12)", yaxis="y",
        ))
        fig_pmc.add_trace(go.Scatter(
            x=pmc_90["date"], y=pmc_90["ctl"],
            name="CTL (Forme)", line=dict(color="#FC4C02", width=2.5),
        ))
        fig_pmc.add_trace(go.Scatter(
            x=pmc_90["date"], y=pmc_90["atl"],
            name="ATL (Fatigue)", line=dict(color="#FF6B35", width=1.5, dash="dot"),
        ))
        fig_pmc.add_trace(go.Scatter(
            x=pmc_90["date"], y=pmc_90["tsb"],
            name="TSB (Équilibre)", line=dict(color="#4FC3F7", width=1.5, dash="dash"),
            fill="tozeroy", fillcolor="rgba(79,195,247,0.06)",
        ))
        fig_pmc.add_hrect(y0=-10, y1=10, fillcolor="rgba(129,199,132,0.07)",
                          annotation_text="Zone fraîcheur", annotation_position="top left",
                          line_width=0)
        fig_pmc.update_layout(
            template="plotly_dark", height=330,
            paper_bgcolor="#0D0D0D", plot_bgcolor="#0D0D0D",
            legend=dict(orientation="h", y=1.12),
            margin=dict(l=0, r=0, t=10, b=0),
        )
        st.plotly_chart(fig_pmc, use_container_width=True)

    with col_r:
        st.markdown("### Zones puissance (10 dernières)")
        zc = df.head(10)["pz_label"].value_counts().reset_index()
        zc.columns = ["Zone", "N"]
        fig_pie = px.pie(
            zc, values="N", names="Zone", hole=0.45,
            color_discrete_sequence=[z[3] for z in POWER_ZONES],
        )
        fig_pie.update_layout(
            template="plotly_dark", height=310,
            paper_bgcolor="#0D0D0D", plot_bgcolor="#0D0D0D",
            showlegend=True, margin=dict(l=0, r=0, t=10, b=10),
        )
        st.plotly_chart(fig_pie, use_container_width=True)

    st.markdown("### TSS — 8 dernières semaines")
    recent = df[df["date"] >= date.today() - timedelta(weeks=8)].copy()
    recent["date_dt"] = pd.to_datetime(recent["date"])
    fig_tss = px.bar(
        recent, x="date_dt", y="tss", color="tss",
        color_continuous_scale=["#81C784", "#FFD54F", "#FF8A65", "#E57373"],
        hover_data={"name": True, "dist_km": True, "IF": True},
        labels={"date_dt": "Date", "tss": "TSS"},
    )
    fig_tss.update_layout(
        template="plotly_dark", height=250,
        paper_bgcolor="#0D0D0D", plot_bgcolor="#0D0D0D",
        coloraxis_showscale=False, margin=dict(l=0, r=0, t=5, b=0),
    )
    st.plotly_chart(fig_tss, use_container_width=True)

    st.markdown("### Dernières sorties")
    cols_show = {
        "date": "Date", "name": "Nom", "dist_km": "Dist (km)",
        "duration_fmt": "Durée", "elev": "D+", "speed": "km/h",
        "np": "NP (W)", "IF": "IF", "tss": "TSS",
        "avg_hr": "BPM moy", "pz_label": "Zone P", "hrz_label": "Zone FC", "eff": "W/bpm",
    }
    st.dataframe(
        df.head(15)[[c for c in cols_show if c in df.columns]].rename(columns=cols_show),
        use_container_width=True, hide_index=True,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2 — ANALYSE DES SORTIES
# ═══════════════════════════════════════════════════════════════════════════════
with tab_analyse:
    st.markdown("### 🔍 Analyse des sorties")

    col_f1, col_f2 = st.columns(2)
    with col_f1:
        n_rides = st.slider("Nombre de sorties", 3, min(30, len(df)), min(8, len(df)))
    with col_f2:
        grp_filter = st.selectbox("Filtrer", ["Toutes", "En groupe (2+)", "Solo"])

    sub = df.head(n_rides).copy()
    if grp_filter == "En groupe (2+)":
        sub = sub[sub["athletes"] >= 2]
    elif grp_filter == "Solo":
        sub = sub[sub["athletes"] < 2]

    if sub.empty:
        st.info("Aucune sortie pour ce filtre.")
    else:
        k1,k2,k3,k4,k5,k6 = st.columns(6)
        k1.metric("Distance totale",  f"{sub['dist_km'].sum():.0f} km")
        k2.metric("D+ total",         f"{sub['elev'].sum():,} m")
        k3.metric("TSS total",        f"{sub['tss'].sum():.0f}")
        k4.metric("NP moyen",         f"{sub['np'].mean():.0f} W")
        k5.metric("IF moyen",         f"{sub['IF'].mean():.3f}")
        k6.metric("BPM moyen",        f"{sub['avg_hr'].mean():.0f}" if sub['avg_hr'].notna().any() else "—")

        st.markdown("---")
        ca, cb = st.columns(2)

        with ca:
            st.markdown("#### NP par sortie vs FTP")
            sub_p = sub.copy()
            sub_p["label"] = sub_p["date"].astype(str).str[5:]
            fig_np = go.Figure()
            fig_np.add_trace(go.Bar(
                x=sub_p["label"], y=sub_p["np"],
                marker_color="#FC4C02",
                text=sub_p["np"], textposition="outside",
            ))
            fig_np.add_hline(y=ftp, line_dash="dash", line_color="#FFD54F",
                             annotation_text=f"FTP {ftp}W")
            fig_np.update_layout(
                template="plotly_dark", height=300,
                paper_bgcolor="#0D0D0D", plot_bgcolor="#0D0D0D",
                margin=dict(l=0, r=0, t=10, b=0), showlegend=False,
            )
            st.plotly_chart(fig_np, use_container_width=True)

        with cb:
            st.markdown("#### Efficience cardiaque (NP / BPM)")
            eff_d = sub[sub["eff"].notna()].copy()
            if not eff_d.empty:
                avg_eff = eff_d["eff"].mean()
                eff_d["label"] = eff_d["date"].astype(str).str[5:]
                fig_eff = go.Figure()
                fig_eff.add_trace(go.Bar(
                    x=eff_d["label"], y=eff_d["eff"],
                    marker_color=["#81C784" if v >= avg_eff else "#FF8A65" for v in eff_d["eff"]],
                    text=[f"{v:.3f}" for v in eff_d["eff"]], textposition="outside",
                ))
                fig_eff.add_hline(y=avg_eff, line_dash="dash", line_color="#4FC3F7",
                                  annotation_text=f"Moy {avg_eff:.3f}")
                fig_eff.update_layout(
                    template="plotly_dark", height=300,
                    paper_bgcolor="#0D0D0D", plot_bgcolor="#0D0D0D",
                    margin=dict(l=0, r=0, t=10, b=0), showlegend=False,
                )
                st.plotly_chart(fig_eff, use_container_width=True)

        cc, cd = st.columns(2)

        with cc:
            st.markdown("#### Durée vs NP (taille = TSS)")
            fig_sc = px.scatter(
                sub, x="duration_s", y="np", size="tss",
                color="IF", color_continuous_scale="RdYlGn",
                hover_data={"name": True, "date": True, "tss": True},
                size_max=35,
            )
            fig_sc.add_hline(y=ftp, line_dash="dash", line_color="#FFD54F",
                             annotation_text=f"FTP {ftp}W")
            fig_sc.update_layout(
                template="plotly_dark", height=300,
                paper_bgcolor="#0D0D0D", plot_bgcolor="#0D0D0D",
                margin=dict(l=0, r=0, t=10, b=0),
            )
            st.plotly_chart(fig_sc, use_container_width=True)

        with cd:
            st.markdown("#### BPM moyen vs NP")
            hr_d = sub[sub["avg_hr"].notna()].copy()
            if not hr_d.empty:
                fig_hr = px.scatter(
                    hr_d, x="avg_hr", y="np", color="IF",
                    color_continuous_scale="Oranges",
                    hover_data={"name": True, "date": True, "tss": True},
                    size="tss", size_max=30,
                )
                fig_hr.update_layout(
                    template="plotly_dark", height=300,
                    paper_bgcolor="#0D0D0D", plot_bgcolor="#0D0D0D",
                    margin=dict(l=0, r=0, t=10, b=0),
                )
                st.plotly_chart(fig_hr, use_container_width=True)

        st.markdown("#### Tableau complet")
        tbl = {
            "date": "Date", "name": "Nom", "dist_km": "Dist",
            "duration_fmt": "Durée", "elev": "D+", "speed": "km/h",
            "avg_w": "Avg W", "np": "NP", "np_pct": "NP%FTP", "IF": "IF",
            "tss": "TSS", "avg_hr": "BPM moy", "hr_pct": "BPM%",
            "eff": "W/bpm", "vi": "VI", "cadence": "Cad", "prs": "PRs",
            "pz_label": "Zone P", "hrz_label": "Zone FC",
        }
        st.dataframe(
            sub[[c for c in tbl if c in sub.columns]].rename(columns=tbl),
            use_container_width=True, hide_index=True,
        )

        # Last ride deep-dive
        st.markdown("---")
        st.markdown("#### 🔬 Dernière sortie — analyse détaillée")
        last = sub.iloc[0]
        lc1, lc2, lc3 = st.columns(3)
        with lc1:
            st.markdown(f"**{last['name']}** — {last['date']}")
            st.metric("Distance",     f"{last['dist_km']} km")
            st.metric("D+",           f"{last['elev']} m")
            st.metric("Durée",        last["duration_fmt"])
            st.metric("Vitesse moy.", f"{last['speed']} km/h")
        with lc2:
            st.metric("NP",        f"{last['np']} W",
                      f"{last['np_pct']}% FTP → {last['pz_label']}")
            st.metric("IF",        str(last["IF"]))
            st.metric("TSS",       str(last["tss"]))
            st.metric("Max power", f"{last['max_w']} W")
        with lc3:
            if last["avg_hr"]:
                st.metric("BPM moyen", f"{last['avg_hr']:.0f}",
                          f"{last['hr_pct']}% HRmax → {last['hrz_label']}")
                st.metric("BPM max",   f"{last['max_hr']:.0f}")
            st.metric("Efficience",  f"{last['eff']:.3f} W/bpm" if last["eff"] else "—")
            if last["cadence"]:
                st.metric("Cadence", f"{last['cadence']:.0f} rpm")

        dur_h = last["duration_s"] / 3600
        expected_if = 0.95 if dur_h <= 1.5 else (0.88 if dur_h <= 2.5 else (0.82 if dur_h <= 3.5 else 0.77))
        if last["IF"] > expected_if:
            implied = round(last["np"] / expected_if)
            st.warning(
                f"⚠️ IF réel ({last['IF']:.3f}) > IF attendu pour {dur_h:.1f}h (≤{expected_if:.2f}) "
                f"→ FTP probablement sous-estimée. FTP implicite ≈ **{implied}W**."
            )
        else:
            st.success(
                f"✅ IF ({last['IF']:.3f}) cohérent avec la durée ({dur_h:.1f}h ≤{expected_if:.2f})."
            )


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 3 — PLAN D'ENTRAÎNEMENT
# ═══════════════════════════════════════════════════════════════════════════════
with tab_plan:
    st.markdown("### 📅 Générateur de plan d'entraînement")

    with st.form("plan_form"):
        st.markdown("#### 🏆 Objectif principal")
        r1, r2, r3 = st.columns(3)
        with r1:
            t_name = st.text_input("Nom de la course", "Boucles du Verdon")
            t_date = st.date_input("Date", date.today() + timedelta(weeks=5),
                                   min_value=date.today() + timedelta(days=7))
        with r2:
            t_dist = st.number_input("Distance (km)", 10, 300, 103)
            t_elev = st.number_input("Dénivelé D+ (m)", 0, 5000, 1314)
        with r3:
            st.markdown("**Course intermédiaire** (optionnel)")
            m_name = st.text_input("Nom", "")
            m_date = st.date_input("Date", date.today() + timedelta(weeks=3),
                                   min_value=date.today())
            m_dist = st.number_input("Distance (km)", 5, 200, 20, key="mdist")

        st.markdown("#### 📆 Disponibilités")
        d1, d2, d3 = st.columns(3)
        with d1:
            lun = st.checkbox("Lundi",    False)
            mar = st.checkbox("Mardi",    True)
            mer = st.checkbox("Mercredi", True)
        with d2:
            jeu = st.checkbox("Jeudi",    True)
            ven = st.checkbox("Vendredi", False)
        with d3:
            has_gym    = st.checkbox("🏋️ Accès muscu", True)
            wkend_day  = st.radio("Sortie weekend", ["Samedi", "Dimanche"], index=1)

        submitted = st.form_submit_button("🚀 Générer le plan", use_container_width=True)

    if submitted or "plan_weeks" in st.session_state:
        avail = [i for i, (_, v) in enumerate(
            [("Lundi",lun),("Mardi",mar),("Mercredi",mer),
             ("Jeudi",jeu),("Vendredi",ven)]
        ) if v]

        if not avail:
            st.error("Sélectionne au moins un jour disponible.")
        else:
            wkend_idx = 5 if wkend_day == "Samedi" else 6
            races = []
            if m_name and m_date < t_date:
                races.append(RaceEvent(m_name, m_date, m_dist, 0, is_target=False))
            target_race = RaceEvent(t_name, t_date, t_dist, t_elev, is_target=True)
            races.append(target_race)

            cfg = PlanConfig(
                ftp=ftp, hr_max=hr_max,
                available_weekdays=avail,
                has_gym=has_gym,
                weekend_ride_day=wkend_idx,
                races=races,
            )

            if submitted:
                with st.spinner("Génération…"):
                    weeks = generate_plan(cfg)
                st.session_state["plan_weeks"]  = weeks
                st.session_state["plan_cfg"]    = cfg
                st.session_state["plan_target"] = target_race

            weeks       = st.session_state.get("plan_weeks", [])
            cfg         = st.session_state.get("plan_cfg", cfg)
            plan_target = st.session_state.get("plan_target", target_race)

            if not weeks:
                st.warning("Impossible de générer un plan — vérifie la date.")
            else:
                st.markdown("---")
                st.markdown("#### Projection TSS hebdomadaire")
                phase_colors = {
                    "Récupération":         "#4FC3F7",
                    "Construction":         "#81C784",
                    "Construction / Pic":   "#FFD54F",
                    "Pic de forme":         "#FF8A65",
                    "Affûtage":             "#CE93D8",
                    "Semaine de course":    "#FC4C02",
                }
                proj_df = pd.DataFrame([{
                    "Semaine": f"S{w.week_num}\n{w.start_date.strftime('%d/%m')}",
                    "TSS": w.total_tss, "Phase": w.phase,
                } for w in weeks])
                fig_proj = px.bar(proj_df, x="Semaine", y="TSS", color="Phase",
                                  color_discrete_map=phase_colors, text="TSS")
                fig_proj.update_layout(
                    template="plotly_dark", height=270,
                    paper_bgcolor="#0D0D0D", plot_bgcolor="#0D0D0D",
                    margin=dict(l=0, r=0, t=5, b=0),
                    legend=dict(orientation="h", y=1.15),
                )
                st.plotly_chart(fig_proj, use_container_width=True)

                st.markdown("---")
                st.markdown("#### Plan détaillé")
                for w in weeks:
                    end_dt = w.start_date + timedelta(days=6)
                    with st.expander(
                        f"**S{w.week_num} — {w.phase}**  ·  "
                        f"{w.start_date.strftime('%d/%m')} → {end_dt.strftime('%d/%m')}  ·  "
                        f"TSS ~{w.total_tss}",
                        expanded=(w.week_num <= 2),
                    ):
                        rows = [{
                            "Jour": dp.weekday_fr,
                            "Date": dp.date_str,
                            "Séance": dp.session.label,
                            "Détail": dp.session.detail,
                            "TSS": dp.session.tss or "",
                            "NP cible": dp.session.np_target,
                        } for dp in w.days]
                        st.dataframe(pd.DataFrame(rows),
                                     use_container_width=True, hide_index=True)

                st.markdown("---")
                st.markdown("#### 📤 Export")
                md = plan_to_markdown(weeks, cfg, plan_target)
                ec1, ec2 = st.columns(2)
                fname = t_name.lower().replace(" ", "_")
                with ec1:
                    st.download_button("⬇️ Markdown (.md)", md.encode(),
                                       f"plan_{fname}.md", "text/markdown",
                                       use_container_width=True)
                with ec2:
                    st.download_button("⬇️ Texte (.txt)", md.encode(),
                                       f"plan_{fname}.txt", "text/plain",
                                       use_container_width=True)
