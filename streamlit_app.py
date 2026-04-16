"""
streamlit_app.py — Football Play Predictor — Streamlit visual interface

Run with:
    streamlit run streamlit_app.py

Requires football_play_predictor.py in the same directory.
Install deps:
    pip install streamlit plotly
"""

import streamlit as st
import plotly.graph_objects as go

from football_play_predictor import (
    FootballPlayPredictor, GameContext, DriveLogger,
    PlayResult, RUN_FAMILIES, FG_RANGE_YARDLINE,
)

st.set_page_config(
    page_title="Play Caller — Sideline OC",
    page_icon="🏈",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
  .block-container { padding-top: 1.5rem; }
  .stMetric label { font-size: 0.7rem !important; text-transform: uppercase; letter-spacing: 0.06em; }
</style>
""", unsafe_allow_html=True)

# ── Session state ────────────────────────────────────────────────────────────

if "predictor"  not in st.session_state: st.session_state.predictor  = FootballPlayPredictor()
if "drive_log"  not in st.session_state: st.session_state.drive_log  = DriveLogger()
if "result"     not in st.session_state: st.session_state.result     = None

predictor = st.session_state.predictor
drive_log = st.session_state.drive_log

# ── Colours ──────────────────────────────────────────────────────────────────

FAM_COLOR = {
    "inside_zone":"#16a34a","outside_zone":"#22c55e","duo":"#15803d","power":"#166534","draw":"#4ade80",
    "quick_game":"#3b82f6","dropback_pass":"#2563eb","screen":"#60a5fa",
    "play_action":"#8b5cf6","fade_iso":"#a78bfa","two_point":"#f59e0b",
}
FAM_LABEL = {
    "inside_zone":"Inside Zone","outside_zone":"Outside Zone","duo":"Duo","power":"Power","draw":"Draw",
    "quick_game":"Quick Game","dropback_pass":"Dropback","screen":"Screen",
    "play_action":"Play Action","fade_iso":"Fade/Iso",
}

# ── Field SVG ────────────────────────────────────────────────────────────────

def render_field(ctx):
    YPX,EZ,W,H = 5.2,44,624,86
    FL,FR = EZ, W-EZ
    bx  = FL+ctx.yardline*YPX if ctx.territory=="own" else FR-ctx.yardline*YPX
    fd_raw = bx+ctx.distance*YPX if ctx.territory=="own" else bx-ctx.distance*YPX
    fdx = max(FL+2, min(FR-2, fd_raw))
    rzL = FR-20*YPX

    stripes = "".join(
        f'<rect x="{FL+i*10*YPX}" y="0" width="{10*YPX}" height="{H}" fill="{"#0c1a0f" if i%2==0 else "#0e1f12"}"/>'
        for i in range(10))
    ylines = "".join(
        f'<line x1="{FL+i*10*YPX}" y1="0" x2="{FL+i*10*YPX}" y2="{H}" stroke="rgba(255,255,255,0.18)" stroke-width="1"/>'
        for i in range(11))
    hashes = "".join(
        f'<line x1="{FL+i*5*YPX}" y1="{H*.28}" x2="{FL+i*5*YPX}" y2="{H*.42}" stroke="rgba(255,255,255,0.1)" stroke-width="0.5"/>'
        f'<line x1="{FL+i*5*YPX}" y1="{H*.58}" x2="{FL+i*5*YPX}" y2="{H*.72}" stroke="rgba(255,255,255,0.1)" stroke-width="0.5"/>'
        for i in range(21))
    ydlbls = "".join(
        f'<text x="{FL+y*YPX}" y="{H/2+3.5}" fill="rgba(255,255,255,0.2)" font-size="8" text-anchor="middle" font-family="monospace">{y}</text>'
        for y in [10,20,30,40,50]) + "".join(
        f'<text x="{FL+y*YPX}" y="{H/2+3.5}" fill="rgba(255,255,255,0.2)" font-size="8" text-anchor="middle" font-family="monospace">{100-y}</text>'
        for y in [60,70,80,90])
    rz = (f'<rect x="{rzL+3}" y="3" width="32" height="10" rx="2" fill="rgba(220,38,38,0.35)"/>'
          f'<text x="{rzL+19}" y="10.5" fill="#fca5a5" font-size="6.5" text-anchor="middle" font-family="monospace">RED ZONE</text>'
          if ctx.territory=="opponents" and ctx.yardline<=20 else "")

    return f"""<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg"
     style="width:100%;display:block;border-radius:6px;border:1px solid #1e2836">
  <rect width="{W}" height="{H}" fill="#090e0b"/>
  {stripes}
  <rect x="0" y="0" width="{EZ}" height="{H}" fill="#0b1a0c"/>
  <rect x="{FR}" y="0" width="{EZ}" height="{H}" fill="#1a0b0b"/>
  <rect x="{rzL}" y="0" width="{20*YPX}" height="{H}" fill="rgba(220,38,38,0.06)"/>
  <line x1="{rzL}" y1="0" x2="{rzL}" y2="{H}" stroke="rgba(220,38,38,0.3)" stroke-width="1" stroke-dasharray="3 2"/>
  {ylines}{hashes}{ydlbls}
  <text x="{EZ/2}" y="{H/2+3}" fill="rgba(255,255,255,0.22)" font-size="7" text-anchor="middle" font-family="monospace">OWN</text>
  <text x="{W-EZ/2}" y="{H/2+3}" fill="rgba(255,255,255,0.22)" font-size="7" text-anchor="middle" font-family="monospace">OPP</text>
  <line x1="{fdx}" y1="0" x2="{fdx}" y2="{H}" stroke="#f5c518" stroke-width="1.5" stroke-dasharray="4 3" opacity="0.65"/>
  <line x1="{bx}" y1="4" x2="{bx}" y2="{H-4}" stroke="#f5c518" stroke-width="2.5"/>
  <ellipse cx="{bx}" cy="{H/2}" rx="6" ry="3.8" fill="#c47e3a" stroke="#e09050" stroke-width="0.5" transform="rotate(-20 {bx} {H/2})"/>
  <rect x="{bx-14}" y="4" width="28" height="12" rx="2" fill="rgba(0,0,0,0.8)"/>
  <text x="{bx}" y="13" fill="#f5c518" font-size="8" text-anchor="middle" font-family="monospace">{ctx.down}&amp;{ctx.distance}</text>
  {rz}
</svg>"""

# ── Charts ───────────────────────────────────────────────────────────────────

def score_chart(scores):
    items  = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    labels = [FAM_LABEL.get(f,f) for f,_ in items]
    vals   = [round(s*100,1) for _,s in items]
    colors = [FAM_COLOR.get(f,"#6b7280") for f,_ in items]
    fig = go.Figure(go.Bar(
        x=vals, y=labels, orientation="h",
        marker=dict(color=colors, cornerradius=3),
        text=[f"{v}%" for v in vals], textposition="outside",
        textfont=dict(size=10, color="#9ca3af", family="Courier New"),
        hovertemplate="%{y}: %{x}%<extra></extra>",
    ))
    fig.update_layout(
        margin=dict(l=0,r=50,t=10,b=10), height=max(160,len(items)*30+20),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(range=[20,75],showgrid=False,showticklabels=False,zeroline=False),
        yaxis=dict(showgrid=False,tickfont=dict(size=11,color="#9ca3af",family="Courier New")),
        showlegend=False,
    )
    return fig

def drive_chart(log):
    counts = log.family_counts
    if not counts: return None
    runs   = sum(v for f,v in counts.items() if f in RUN_FAMILIES)
    passes = sum(v for f,v in counts.items() if f not in RUN_FAMILIES)
    fig = go.Figure(go.Bar(
        x=list(counts.keys()), y=list(counts.values()),
        marker=dict(color=[FAM_COLOR.get(f,"#6b7280") for f in counts]),
        text=list(counts.values()), textposition="outside",
        textfont=dict(size=11,color="#9ca3af"),
        hovertemplate="%{x}: %{y} plays<extra></extra>",
    ))
    fig.update_layout(
        title=dict(text=f"Concept frequency — {runs}R / {passes}P", font=dict(size=12,color="#9ca3af")),
        margin=dict(l=0,r=0,t=30,b=0), height=180,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(showgrid=False,tickfont=dict(size=10,color="#9ca3af"),tickangle=-20),
        yaxis=dict(showgrid=False,showticklabels=False,zeroline=False),
        showlegend=False,
    )
    return fig

# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("### 🏈 Play Caller")
    st.caption("Sideline OC assistant")
    st.divider()

    st.markdown("#### Down & Distance")
    c1,c2 = st.columns(2)
    down     = c1.selectbox("Down",     [1,2,3,4], index=0)
    distance = c2.selectbox("Distance", [1,2,3,4,5,6,7,8,9,10,12,15,20], index=9)

    st.markdown("#### Field Position")
    territory = st.radio("Territory",["own","opponents"],horizontal=True,format_func=lambda x:"Own" if x=="own" else "Opp.")
    yardline  = st.slider("Yardline", 1, 50, 25)

    st.divider()
    st.markdown("#### Defensive Read")
    def_personnel  = st.selectbox("Personnel",["unknown","nickel","base","dime","goal_line"],format_func=lambda x:x.replace("_"," ").title())
    box_count      = st.slider("Box count", 4, 9, 7, format="%d in box")
    coverage_shell = st.selectbox("Coverage",["unknown","cover_0","cover_1","cover_2","cover_3","cover_4","quarters"],
                                  format_func=lambda x:x.replace("_"," ").upper() if x!="unknown" else "Unknown")
    safeties       = st.selectbox("Safeties",["unknown","single_high","two_high"],format_func=lambda x:x.replace("_"," ").title())
    blitz_likely   = st.toggle("Blitz expected", value=False)

    st.divider()
    st.markdown("#### Game Script")
    c3,c4 = st.columns(2)
    quarter    = c3.selectbox("Quarter",[1,2,3,4],index=1)
    score_diff = c4.number_input("Score diff.",value=0,min_value=-28,max_value=28,step=1)
    mins       = st.slider("Minutes remaining",0,60,30)
    secs_extra = st.slider("+ seconds",0,59,0)
    seconds_remaining = mins*60 + secs_extra
    c5,c6 = st.columns(2)
    own_timeouts = c5.selectbox("Own TOs",[0,1,2,3],index=3)
    opp_timeouts = c6.selectbox("Opp TOs",[0,1,2,3],index=3)

    st.divider()
    st.markdown("#### Extras")
    weather    = st.selectbox("Weather",["clear","wind","rain","snow"])
    wind_mph   = st.slider("Wind (mph)",0,40,0) if weather=="wind" else 0
    qb_limited = st.toggle("QB limited",value=False)
    game_mode  = st.selectbox("Override mode",["normal","must_score","drain_clock","two_minute","two_point"],
                              format_func=lambda x:x.replace("_"," ").title())
    mismatch   = st.text_input("Mismatch note",placeholder="e.g. slot CB is undersized...")
    st.divider()

    generate = st.button("Generate play call", type="primary", use_container_width=True)
    if st.button("New drive", use_container_width=True):
        drive_log.reset()
        st.session_state.result = None
        st.rerun()

# ── Build context and generate ────────────────────────────────────────────────

ctx = GameContext(
    down=down, distance=distance, yardline=yardline, territory=territory,
    def_personnel=def_personnel, box_count=box_count, coverage_shell=coverage_shell,
    blitz_likely=blitz_likely, safeties=safeties,
    score_diff=score_diff, quarter=quarter, seconds_remaining=seconds_remaining,
    own_timeouts=own_timeouts, opp_timeouts=opp_timeouts,
    weather=weather, wind_mph=wind_mph, qb_limited=qb_limited,
    mismatch=mismatch or None, game_mode=game_mode,
    plays_this_drive=len(drive_log.results),
    shown_concepts=list(drive_log.family_counts.keys()),
    run_plays_this_drive=drive_log.run_count(),
)

if generate:
    st.session_state.result = predictor.recommend(ctx, drive_log)

result = st.session_state.result

# ── Main page ─────────────────────────────────────────────────────────────────

st.markdown("## Play Caller — Sideline OC")

MODE_BANNERS = {
    "two_minute":  ("🚨 Two-Minute Drill",     "#ef4444"),
    "must_score":  ("🚨 Must Score",            "#ef4444"),
    "drain_clock": ("⏱ Drain the Clock",       "#22c55e"),
    "two_point":   ("🎯 Two-Point Conversion",  "#f59e0b"),
}
eff_mode = result["ctx"].game_mode if result else predictor.derive_game_mode(ctx)
if eff_mode in MODE_BANNERS:
    bt, bc = MODE_BANNERS[eff_mode]
    st.markdown(f'<div style="background:{bc}18;border:1px solid {bc}44;border-radius:6px;padding:8px 14px;margin-bottom:12px;color:{bc};font-weight:600;font-size:16px">{bt}</div>', unsafe_allow_html=True)

# Metrics row
def fmt_t(s): return f"{s//60}:{s%60:02d}"
sc_lbl = f"+{score_diff}" if score_diff>0 else str(score_diff)
m1,m2,m3,m4,m5 = st.columns(5)
m1.metric("Situation",  f"{down}&{distance}")
m2.metric("Position",   f"{'Opp.' if territory=='opponents' else 'Own'} {yardline}")
m3.metric("Score",      sc_lbl)
m4.metric("Q / Clock",  f"Q{quarter} {fmt_t(seconds_remaining)}")
m5.metric("TOs",        f"{own_timeouts}–{opp_timeouts}")
st.divider()

left, right = st.columns([1,1], gap="large")

with left:
    st.markdown("**Field position**")
    display_ctx = result["ctx"] if result else ctx
    st.markdown(render_field(display_ctx), unsafe_allow_html=True)
    if result:
        bkt = result["bucket"].replace("_"," ").title()
        cov = result["ctx"].coverage_shell.replace("_"," ").upper() if result["ctx"].coverage_shell!="unknown" else "Coverage unknown"
        blz = " · Blitz expected" if result["ctx"].blitz_likely else ""
        st.caption(f"Bucket: {bkt}  ·  {cov}{blz}")

    # 4th down
    if result and result.get("fourth_down"):
        fd = result["fourth_down"]
        fd_clrs = {"GO FOR IT":"#22c55e","FIELD GOAL":"#3b82f6","PUNT":"#9ca3af"}
        fc = fd_clrs.get(fd.get("recommendation","PUNT"),"#9ca3af")
        fgd = f"  <span style='font-size:12px;color:#9ca3af'>(~{fd['fg_distance']} yds)</span>" if fd.get("fg_distance") else ""
        st.markdown(
            f'<div style="margin-top:12px;padding:10px 14px;border-radius:6px;background:{fc}10;border:1px solid {fc}33">'
            f'<div style="color:{fc};font-size:16px;font-weight:600">4th down: {fd.get("recommendation","")}{fgd}</div>'
            f'<div style="color:#9ca3af;font-size:13px;margin-top:3px">{fd.get("reasoning","")}</div></div>',
            unsafe_allow_html=True)

    # Score chart
    if result and result.get("scores"):
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("**Family scores**")
        st.plotly_chart(score_chart(result["scores"]), use_container_width=True, config={"displayModeBar":False})

with right:
    if not result:
        st.info("Configure the situation in the sidebar, then click **Generate play call**.")
    else:
        play   = result["play"]
        family = result["play_family"]
        fctx   = result["ctx"]
        fc     = FAM_COLOR.get(family,"#6b7280")

        # Header
        td_badge = f"  ·  TD {round(play['td_pct']*100)}%" if "td_pct" in play else ""
        st.markdown(
            f'<div style="background:{fc}12;border:1px solid {fc}33;border-radius:6px;padding:12px 16px;margin-bottom:12px">'
            f'<div style="font-size:22px;font-weight:700;color:#f0f4f8">{play.get("name","")}</div>'
            f'<div style="font-size:11px;color:{fc};text-transform:uppercase;letter-spacing:0.1em;margin-top:2px">'
            f'{FAM_LABEL.get(family,family)}{td_badge}</div></div>',
            unsafe_allow_html=True)

        # Formation / blocking row
        fi = st.columns(3)
        if play.get("formation"):
            fi[0].caption("Formation"); fi[0].markdown(f"`{play['formation']}`")
        if play.get("protection") or play.get("blocking"):
            fi[1].caption("Protection / Blocking"); fi[1].markdown(f"`{play.get('protection') or play.get('blocking')}`")
        if play.get("run_scheme"):
            fi[2].caption("Scheme"); fi[2].markdown(f"`{play['run_scheme']}`")

        # Routes
        if play.get("routes"):
            st.markdown("**Routes**")
            ritems = list(play["routes"].items())
            rc1,rc2 = st.columns(2)
            for i,(pos,route) in enumerate(ritems):
                (rc1 if i<(len(ritems)+1)//2 else rc2).markdown(f"**`{pos}`** {route}")

        # Why
        st.markdown(
            f'<div style="border-left:2px solid {fc};background:rgba(255,255,255,0.025);padding:6px 10px;'
            f'border-radius:0 4px 4px 0;margin:10px 0;font-size:13px;color:#d1d5db">'
            f'<strong style="color:#9ca3af;font-size:10px;text-transform:uppercase">Why:</strong> {play.get("why","")}</div>',
            unsafe_allow_html=True)

        # Coaching notes helper
        def note(icon, label, text, color="#9ca3af"):
            st.markdown(
                f'<div style="display:flex;gap:6px;padding:5px 8px;border-radius:4px;background:rgba(255,255,255,0.02);margin-bottom:4px;font-size:12px">'
                f'<span style="color:{color};min-width:70px;font-size:10px;text-transform:uppercase;letter-spacing:0.06em;padding-top:1px">{icon} {label}</span>'
                f'<span style="color:#d1d5db">{text}</span></div>',
                unsafe_allow_html=True)

        is_man   = fctx.coverage_shell in ("cover_0","cover_1")
        cov_note = (play.get("vs_man") if is_man else play.get("vs_zone")) if fctx.coverage_shell!="unknown" else None
        shell_l  = fctx.coverage_shell.replace("_"," ").upper() if fctx.coverage_shell!="unknown" else ""

        if cov_note:                                             note(">",f"vs. {shell_l}",cov_note,"#3b82f6")
        else:
            if play.get("vs_man"):                               note(">","vs. Man",play["vs_man"],"#3b82f6")
            if play.get("vs_zone"):                              note(">","vs. Zone",play["vs_zone"],"#60a5fa")
        if play.get("kill_look"):                                note("X","Kill look",play["kill_look"],"#ef4444")
        if play.get("post_snap_alert"):                          note("*","Post-snap",play["post_snap_alert"],"#8b5cf6")
        if family=="play_action" and fctx.run_plays_this_drive<3:
            note("!","PA warn",f"Run not established ({fctx.run_plays_this_drive} runs) — fake may not freeze LBs.","#f59e0b")
        if fctx.weather in ("wind","rain","snow") and family in ("dropback_pass","play_action"):
            wx = (f"Wind {fctx.wind_mph}mph — shorten the route tree." if fctx.weather=="wind"
                  else "Wet conditions — prioritize short throws." if fctx.weather=="rain"
                  else "Snow — consider running instead.")
            note("~","Weather",wx,"#60a5fa")
        if fctx.mismatch:                                        note("*","Mismatch",fctx.mismatch,"#f59e0b")
        if fctx.game_mode=="two_minute":                         note(">","Tempo",f"Hurry-up — {fctx.own_timeouts} TOs left. Spike or go OOB.","#f59e0b")
        if fctx.game_mode=="drain_clock":                        note(">","Tempo","Milk it — long cadence, stay in bounds.","#22c55e")
        if fctx.blitz_likely:                                    note(">","Snap count","Hard count — see if they jump before the snap.","#f59e0b")

        ov_cnt = drive_log.family_counts.get(family, 0)
        if ov_cnt >= 3:
            st.warning(f"**Tendency:** {FAM_LABEL.get(family,family)} called {ov_cnt}x this drive — defense is keying on it.")

        # Log result
        st.divider()
        st.markdown("**Log result**")
        lc1,lc2 = st.columns([3,1])
        yards_input = lc1.number_input("Yards", value=0, step=1, label_visibility="collapsed")
        if lc2.button("Log", use_container_width=True):
            outcome = "first_down" if yards_input>=distance else "sack" if yards_input<-3 else "short"
            drive_log.log(PlayResult(concept_name=play.get("name",""),family=family,yards_gained=yards_input,outcome=outcome))
            st.toast(f"Logged: {yards_input:+d} yards ({outcome})")

# Drive log
st.divider()
st.markdown("### Drive log")
if not drive_log.results:
    st.caption("No plays logged. Use **Log** after each snap.")
else:
    dc = drive_chart(drive_log)
    if dc: st.plotly_chart(dc, use_container_width=True, config={"displayModeBar":False})
    chips = " ".join(
        f'<span style="padding:2px 8px;border-radius:3px;background:{FAM_COLOR.get(r.family,"#6b7280")}22;'
        f'border:1px solid {FAM_COLOR.get(r.family,"#6b7280")}55;color:{FAM_COLOR.get(r.family,"#9ca3af")};font-size:11px">'
        f'{FAM_LABEL.get(r.family,r.family)} {r.yards_gained:+d}</span>'
        for r in drive_log.results)
    st.markdown(f'<div style="display:flex;flex-wrap:wrap;gap:4px;margin-top:8px">{chips}</div>', unsafe_allow_html=True)
    runs_c, passes_c = drive_log.run_pass_split()
    st.caption(f"{len(drive_log.results)} plays · {runs_c} run / {passes_c} pass")
