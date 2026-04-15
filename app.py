from typing import Dict, Any, List, Optional, Tuple

import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import streamlit as st

from football_play_predictor_claude_final import (
    FootballPlayPredictor,
    GameContext,
    DriveLogger,
    RUN_FAMILIES,
    PASS_FAMILIES,
    FG_RANGE_YARDLINE,
)


st.set_page_config(
    page_title="Football Play Predictor",
    page_icon="🏈",
    layout="wide",
)

st.markdown(
    """
    <style>
    .call-card {
        padding: 0.85rem;
        border: 1px solid #374151;
        border-radius: 12px;
        background: #0f172a;
        margin-bottom: 0.75rem;
        height: 100%;
    }
    .call-title {
        font-size: 1.05rem;
        font-weight: 700;
        margin-bottom: 0.35rem;
    }
    .indicator-row {
        display: flex;
        gap: 0.5rem;
        flex-wrap: wrap;
        margin: 0.4rem 0 0.8rem 0;
    }
    .indicator-pill {
        padding: 0.35rem 0.6rem;
        border-radius: 999px;
        border: 1px solid #374151;
        background: #111827;
        font-size: 0.85rem;
    }
    .compact-card {
        padding: 0.7rem;
        border: 1px solid #374151;
        border-radius: 12px;
        background: #0f172a;
        height: 100%;
    }
    .compact-title {
        font-size: 0.95rem;
        font-weight: 700;
        margin-bottom: 0.25rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------- Session state ----------
if "predictor" not in st.session_state:
    st.session_state.predictor = FootballPlayPredictor()

if "drive_log" not in st.session_state:
    st.session_state.drive_log = DriveLogger()

if "last_input" not in st.session_state:
    st.session_state.last_input = ""

if "last_result" not in st.session_state:
    st.session_state.last_result = None

if "compact_mode" not in st.session_state:
    st.session_state.compact_mode = True

if "show_debug" not in st.session_state:
    st.session_state.show_debug = False

predictor: FootballPlayPredictor = st.session_state.predictor
drive_log: DriveLogger = st.session_state.drive_log


# ---------- Helpers ----------
def format_score(score: float) -> str:
    return f"{score:.2f}"


def territory_label(territory: str) -> str:
    return "Own" if territory == "own" else "Opp."


def yardline_to_absolute(territory: str, yardline: int) -> int:
    return yardline if territory == "own" else 100 - yardline


def field_zone_from_ctx(ctx: GameContext) -> str:
    if ctx.territory == "own":
        if ctx.yardline <= 10:
            return "backed_up"
        if ctx.yardline <= 20:
            return "coming_out"
        return "open_field"

    if ctx.yardline >= 41:
        return "plus_territory"
    if 21 <= ctx.yardline <= 30:
        return "fringe_red"
    if 11 <= ctx.yardline <= 20:
        return "high_red"
    return "low_red"


def distance_profile_from_ctx(ctx: GameContext) -> str:
    if ctx.down == 1 and ctx.distance == 10:
        return "base_first_and_10"
    if ctx.distance <= 2:
        return "short_yardage"
    if 3 <= ctx.distance <= 6:
        return "medium_yardage"
    if 7 <= ctx.distance <= 9:
        return "long_yardage"
    return "extra_long"


def calc_indicators(ctx: GameContext, fourth_down: Dict[str, Any]) -> Dict[str, str]:
    zone = field_zone_from_ctx(ctx)
    red_zone = "Yes" if zone in {"high_red", "low_red"} else "Near" if zone == "fringe_red" else "No"
    fg_range = "Yes" if ctx.territory == "opponents" and ctx.yardline <= FG_RANGE_YARDLINE else "No"
    four_down = fourth_down.get("recommendation", "No") if ctx.down == 4 else ("Likely" if ctx.territory == "opponents" and ctx.yardline <= 45 else "No")
    return {
        "Red Zone": red_zone,
        "FG Range": fg_range,
        "4-Down": four_down,
        "Mode": ctx.game_mode.replace("_", " ").title(),
    }


def render_indicator_strip(ctx: GameContext, fourth_down: Dict[str, Any]) -> None:
    indicators = calc_indicators(ctx, fourth_down)
    html = ['<div class="indicator-row">']
    for label, value in indicators.items():
        html.append(f'<div class="indicator-pill"><strong>{label}:</strong> {value}</div>')
    html.append('</div>')
    st.markdown("".join(html), unsafe_allow_html=True)


def draw_field_position(ctx: GameContext):
    abs_yard = yardline_to_absolute(ctx.territory, ctx.yardline)

    fig, ax = plt.subplots(figsize=(10, 1.8))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 1)
    ax.axis("off")

    ax.add_patch(Rectangle((0, 0.1), 100, 0.8, fill=False, linewidth=2))
    zones = [
        (0, 10, "Backed Up"),
        (10, 20, "Coming Out"),
        (20, 50, "Open Field"),
        (50, 70, "Plus Territory"),
        (70, 80, "Fringe Red"),
        (80, 90, "High Red"),
        (90, 100, "Low Red"),
    ]
    for start, end, label in zones:
        ax.add_patch(Rectangle((start, 0.1), end - start, 0.8, fill=False, linewidth=1))
        ax.text((start + end) / 2, 0.88, label, ha="center", va="top", fontsize=8)

    for x in range(0, 101, 5):
        ax.plot([x, x], [0.1, 0.9], linewidth=0.5)
    for x in range(0, 101, 10):
        ax.text(x, 0.02, str(x), ha="center", va="bottom", fontsize=8)

    ax.scatter([abs_yard], [0.5], s=160, marker="o")
    ax.text(abs_yard, 0.58, "Ball", ha="center", fontsize=9)
    ax.set_title("Field Position", fontsize=12)
    return fig


def draw_family_rankings(scores: Dict[str, float]):
    rankings = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:8]
    labels = [family.replace("_", " ").title() for family, _ in rankings]
    values = [score for _, score in rankings]

    fig, ax = plt.subplots(figsize=(8, 3.2))
    ax.barh(labels[::-1], values[::-1])
    ax.set_xlabel("Score")
    ax.set_title("Top Family Rankings")
    return fig


def _route_path(start_x, start_y, kind):
    if kind == "slant":
        return [start_x, start_x + 10], [start_y, start_y + 8]
    if kind == "flat":
        return [start_x, start_x + 8], [start_y, start_y]
    if kind == "hitch":
        return [start_x, start_x + 7], [start_y, start_y]
    if kind == "hook":
        return [start_x, start_x + 8, start_x + 8], [start_y, start_y, start_y + 4]
    if kind == "go":
        return [start_x, start_x + 20], [start_y, start_y]
    if kind == "fade":
        return [start_x, start_x + 18], [start_y, start_y + 6]
    if kind == "out":
        return [start_x, start_x + 12, start_x + 12], [start_y, start_y, start_y + 8]
    if kind == "dig":
        return [start_x, start_x + 14, start_x + 14], [start_y, start_y, start_y - 8]
    if kind == "cross":
        return [start_x, start_x + 6, start_x + 18], [start_y, start_y - 2, 26]
    if kind == "bubble":
        return [start_x, start_x - 2, start_x + 5], [start_y, start_y + 3, start_y + 6]
    if kind == "screen":
        return [start_x, start_x - 3, start_x + 2], [start_y, start_y, start_y]
    return [start_x, start_x + 8], [start_y, start_y]


def concept_diagram_data(play_name: str):
    concepts = {
        "Stick": [("X", 2, 8, "slant"), ("H", 2, 20, "hook"), ("Y", 2, 28, "flat"), ("Z", 2, 40, "fade"), ("RB", 0, 24, "flat")],
        "Spacing": [("X", 2, 8, "hitch"), ("H", 2, 18, "hook"), ("Y", 2, 30, "hook"), ("Z", 2, 42, "hitch"), ("RB", 0, 25, "hook")],
        "Slant-Flat": [("X", 2, 8, "slant"), ("H", 2, 20, "flat"), ("Y", 2, 30, "go"), ("Z", 2, 42, "dig"), ("RB", 0, 24, "flat")],
        "Drive": [("X", 2, 8, "dig"), ("H", 2, 20, "cross"), ("Y", 2, 28, "hook"), ("Z", 2, 42, "go"), ("RB", 0, 24, "flat")],
        "Dagger": [("X", 2, 8, "hitch"), ("H", 2, 20, "go"), ("Y", 2, 28, "dig"), ("Z", 2, 42, "go"), ("RB", 0, 24, "flat")],
        "Y-Cross": [("X", 2, 8, "hitch"), ("H", 2, 20, "cross"), ("Y", 2, 28, "cross"), ("Z", 2, 42, "go"), ("RB", 0, 24, "flat")],
        "RB Middle Screen": [("X", 2, 8, "go"), ("H", 2, 20, "go"), ("Y", 2, 30, "go"), ("Z", 2, 42, "go"), ("RB", 0, 24, "screen")],
        "Trips Bubble": [("X", 2, 8, "slant"), ("H", 2, 20, "bubble"), ("Y", 2, 30, "flat"), ("Z", 2, 40, "flat"), ("RB", 0, 24, "flat")],
        "Boot Flood": [("X", 2, 8, "go"), ("Y", 2, 28, "out"), ("H", 2, 20, "flat"), ("Z", 2, 40, "cross"), ("RB", 0, 24, "flat")],
        "Y-Leak": [("X", 2, 8, "go"), ("Y", 2, 28, "cross"), ("H", 2, 20, "cross"), ("Z", 2, 40, "out"), ("RB", 0, 24, "flat")],
        "Rub / Pick Slant": [("X", 2, 8, "go"), ("H", 2, 20, "flat"), ("Y", 2, 28, "slant"), ("Z", 2, 40, "flat"), ("RB", 0, 24, "hook")],
    }
    return concepts.get(play_name)


def draw_play_diagram(play: Dict[str, Any]):
    data = concept_diagram_data(play.get("name", ""))
    if not data:
        return None

    fig, ax = plt.subplots(figsize=(8, 4.2))
    ax.set_xlim(0, 30)
    ax.set_ylim(0, 50)
    ax.axis("off")

    ax.add_patch(Rectangle((0, 0), 30, 50, fill=False, linewidth=2))
    for y in range(0, 51, 5):
        ax.plot([0, 30], [y, y], linewidth=0.4)

    ax.plot([2, 2], [0, 50], linewidth=2)
    ax.text(1.5, 48, "LOS", fontsize=9, rotation=90)

    for label, sx, sy, route_kind in data:
        ax.scatter([sx], [sy], s=60)
        ax.text(sx - 1.2, sy + 1.5, label, fontsize=8)
        px, py = _route_path(sx, sy, route_kind)
        ax.plot(px, py, linewidth=2)

    ax.set_title(f"Concept Diagram: {play.get('name', 'Play')}", fontsize=12)
    return fig


def build_context_from_ui(
    situation_text: str,
    score_state: str,
    quarter: int,
    clock_mode: str,
    own_tos: int,
    opp_tos: int,
    def_personnel: str,
    shell: str,
    safeties: str,
    box_count: int,
    blitz_likely: bool,
    offensive_personnel: str,
    weather: str,
    turf: str,
    qb_limited: bool,
    matchup: str,
) -> GameContext:
    down, distance, yardline, territory = predictor.parse_situation(situation_text)

    score_map = {
        "Leading": 7,
        "Tied": 0,
        "Trailing": -7,
        "Big Lead": 14,
        "Big Deficit": -14,
    }

    mode_map = {
        "Normal": "normal",
        "2-Minute": "two_minute",
        "Must Score": "must_score",
        "Drain Clock": "drain_clock",
        "Two-Point": "two_point",
    }

    shell_map = {
        "Unknown": "unknown",
        "Cover 1": "cover_1",
        "Cover 2": "cover_2",
        "Cover 3": "cover_3",
        "Cover 4": "cover_4",
        "Quarters": "quarters",
        "Cover 0": "cover_0",
    }

    safety_map = {
        "Unknown": "unknown",
        "1 High": "single_high",
        "2 High": "two_high",
    }

    def_personnel_map = {
        "Unknown": "unknown",
        "Base": "base",
        "Nickel": "nickel",
        "Dime": "dime",
        "Goal Line": "goal_line",
    }

    weather_map = {
        "Clear": "clear",
        "Wind": "wind",
        "Rain": "rain",
        "Snow": "snow",
    }

    mismatch_text = None
    if matchup == "WR Matchup":
        mismatch_text = "Outside WR advantage"
    elif matchup == "Slot Matchup":
        mismatch_text = "Slot matchup advantage"
    elif matchup == "Run Box":
        mismatch_text = "Favorable run box look"

    ctx = GameContext(
        down=down,
        distance=distance,
        yardline=yardline,
        territory=territory,
        score_diff=score_map[score_state],
        quarter=quarter,
        seconds_remaining=120 if clock_mode == "2-Minute" else (180 if clock_mode == "Must Score" else 900),
        own_timeouts=own_tos,
        opp_timeouts=opp_tos,
        def_personnel=def_personnel_map[def_personnel],
        box_count=box_count,
        coverage_shell=shell_map[shell],
        blitz_likely=blitz_likely,
        safeties=safety_map[safeties],
        weather=weather_map[weather],
        wind_mph=20 if weather == "Wind" else 0,
        turf=turf.lower(),
        personnel_group=offensive_personnel,
        mismatch=mismatch_text,
        qb_limited=qb_limited,
        plays_this_drive=len(drive_log.results),
        shown_concepts=list(drive_log.family_counts.keys()),
        run_plays_this_drive=drive_log.run_count(),
        game_mode=mode_map[clock_mode],
    )
    return ctx


def play_summary_lines(call: Dict[str, Any], compact: bool = False) -> List[str]:
    play = call["play"]
    lines = [
        f"**Family:** {call['family'].replace('_', ' ').title()}",
        f"**Score:** {format_score(call['score'])}",
        f"**Personnel:** {play.get('personnel', 'N/A')}",
        f"**Formation:** {play.get('formation', 'N/A')}",
    ]

    if play.get("run_scheme"):
        lines.append(f"**Run:** {play['run_scheme']}")
        if not compact and play.get("blocking"):
            lines.append(f"**Blocking:** {play['blocking']}")
    else:
        if play.get("protection"):
            lines.append(f"**Protection:** {play['protection']}")

    if not compact and play.get("routes"):
        lines.append("**Routes:**")
        for player, route in play["routes"].items():
            lines.append(f"- {player}: {route}")

    if call.get("why"):
        lines.append(f"**Why:** {call['why']}")
    if not compact and call.get("coverage_note"):
        lines.append(f"**Coverage note:** {call['coverage_note']}")
    if not compact and call.get("kill_look"):
        lines.append(f"**Kill look:** {call['kill_look']}")
    return lines


def render_call_card(label: str, call: Optional[Dict[str, Any]], compact: bool = False) -> None:
    st.markdown(f"### {label}")
    if call is None:
        st.info("No clearly distinct option available.")
        return

    play = call["play"]
    css_class = "compact-card" if compact else "call-card"
    title_class = "compact-title" if compact else "call-title"

    st.markdown(f'<div class="{css_class}">', unsafe_allow_html=True)
    st.markdown(f'<div class="{title_class}">{play.get("name", "Call")}</div>', unsafe_allow_html=True)
    for line in play_summary_lines(call, compact=compact):
        st.markdown(line)
    st.markdown("</div>", unsafe_allow_html=True)


def make_candidate(family: str, score: float, play: Dict[str, Any], ctx: GameContext) -> Dict[str, Any]:
    coverage_note = predictor.coverage_note(play, ctx)
    return {
        "family": family,
        "score": score,
        "play": play,
        "why": play.get("why", ""),
        "coverage_note": coverage_note,
        "kill_look": play.get("kill_look", ""),
    }


def build_alternative_calls(result: Dict[str, Any], ctx: GameContext) -> Dict[str, Optional[Dict[str, Any]]]:
    scores = result["scores"]
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    best = make_candidate(result["play_family"], scores[result["play_family"]], result["play"], ctx)
    excluded_names = {best["play"].get("name", "")}

    candidates = []
    for family, score in ranked:
        play = predictor.choose_play(family, ctx)
        candidates.append(make_candidate(family, score, play, ctx))

    def first_distinct(filter_fn):
        for c in candidates:
            name = c["play"].get("name", "")
            if name in excluded_names:
                continue
            if filter_fn(c):
                excluded_names.add(name)
                return c
        return None

    safe = first_distinct(lambda c: c["family"] in {"quick_game", "screen", "inside_zone", "duo"})
    aggressive = first_distinct(lambda c: c["family"] in {"dropback_pass", "play_action", "fade_iso", "power"})
    run_alt = first_distinct(lambda c: c["family"] in RUN_FAMILIES)

    return {
        "best": best,
        "safe": safe,
        "aggressive": aggressive,
        "run_alt": run_alt,
        "ranked": ranked,
    }


def build_context_effects(ctx: GameContext) -> List[str]:
    effects = []

    if ctx.game_mode == "two_minute":
        effects.append("2-minute mode favors quick game and dropback answers.")
    elif ctx.game_mode == "must_score":
        effects.append("Must-score mode boosts chunk-play and pass families.")
    elif ctx.game_mode == "drain_clock":
        effects.append("Drain-clock mode boosts run game and lowers pass aggression.")

    if ctx.blitz_likely:
        effects.append("Blitz look boosts screens and fast answers.")
    if ctx.coverage_shell in {"cover_2", "cover_4", "quarters"}:
        effects.append(f"{ctx.coverage_shell.replace('_', ' ').title()} nudges value toward underneath answers.")
    elif ctx.coverage_shell in {"cover_0", "cover_1", "cover_3"}:
        effects.append(f"{ctx.coverage_shell.replace('_', ' ').title()} increases value for man-beaters or seam stress.")

    if ctx.box_count <= 6:
        effects.append("Light box increases run value.")
    elif ctx.box_count >= 8:
        effects.append("Heavy box lowers run value and boosts quick/pass options.")

    if ctx.weather in {"wind", "rain", "snow"}:
        effects.append(f"{ctx.weather.title()} reduces deep pass comfort and raises run value.")
    if ctx.qb_limited:
        effects.append("QB-limited toggle reduces slower-developing calls.")
    if ctx.mismatch:
        effects.append(f"Mismatch focus: {ctx.mismatch}.")

    return effects


def render_compact_mode(ctx: GameContext, result: Dict[str, Any], calls: Dict[str, Optional[Dict[str, Any]]]) -> None:
    top1, top2, top3, top4 = st.columns(4)
    top1.metric("Down", str(ctx.down))
    top2.metric("Distance", str(ctx.distance))
    top3.metric("Zone", field_zone_from_ctx(ctx).replace("_", " ").title())
    top4.metric("Profile", distance_profile_from_ctx(ctx).replace("_", " ").title())

    render_indicator_strip(ctx, result.get("fourth_down", {}))

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        render_call_card("Best", calls["best"], compact=True)
    with c2:
        render_call_card("Safe", calls["safe"], compact=True)
    with c3:
        render_call_card("Aggressive", calls["aggressive"], compact=True)
    with c4:
        render_call_card("Run", calls["run_alt"], compact=True)

    left, right = st.columns([1.05, 0.95])

    with left:
        st.pyplot(draw_field_position(ctx), clear_figure=True)

    with right:
        diagram = draw_play_diagram(calls["best"]["play"])
        if diagram is None:
            st.info("No custom concept diagram yet for this play.")
        else:
            st.pyplot(diagram, clear_figure=True)

    effects = build_context_effects(ctx)
    if effects:
        st.subheader("Why the context changed this call")
        for item in effects:
            st.write(f"- {item}")

    if result.get("fourth_down"):
        st.subheader("4th Down Advisor")
        st.write(f"**{result['fourth_down'].get('recommendation', '')}** — {result['fourth_down'].get('reasoning', '')}")

    if st.session_state.show_debug:
        st.pyplot(draw_family_rankings(result["scores"]), clear_figure=True)


def render_standard_mode(ctx: GameContext, result: Dict[str, Any], calls: Dict[str, Optional[Dict[str, Any]]]) -> None:
    top1, top2, top3, top4 = st.columns(4)
    top1.metric("Down", str(ctx.down))
    top2.metric("Distance", str(ctx.distance))
    top3.metric("Field Zone", field_zone_from_ctx(ctx).replace("_", " ").title())
    top4.metric("Profile", distance_profile_from_ctx(ctx).replace("_", " ").title())

    render_indicator_strip(ctx, result.get("fourth_down", {}))

    left, right = st.columns([1.15, 0.85])

    with left:
        st.subheader("Recommendations")
        render_call_card("Best Call", calls["best"])
        render_call_card("Safe Call", calls["safe"])
        render_call_card("Aggressive Call", calls["aggressive"])
        render_call_card("Run Alternative", calls["run_alt"])

    with right:
        st.subheader("Situation Visuals")
        st.pyplot(draw_field_position(ctx), clear_figure=True)
        st.pyplot(draw_family_rankings(result["scores"]), clear_figure=True)

    st.subheader("Best Call Diagram")
    diagram = draw_play_diagram(calls["best"]["play"])
    if diagram is None:
        st.info("No custom concept diagram yet for this play.")
    else:
        st.pyplot(diagram, clear_figure=True)

    effects = build_context_effects(ctx)
    if effects:
        st.subheader("Why the context changed this call")
        for item in effects:
            st.write(f"- {item}")

    if result.get("coverage_note") or result.get("pa_warning") or result.get("overuse_warning"):
        st.subheader("Coordinator Notes")
        if result.get("coverage_note"):
            st.write(f"**Coverage note:** {result['coverage_note']}")
        if result.get("pa_warning"):
            st.write(result["pa_warning"])
        if result.get("overuse_warning"):
            st.write(result["overuse_warning"])

    if result.get("fourth_down"):
        st.subheader("4th Down Advisor")
        st.write(f"**{result['fourth_down'].get('recommendation', '')}** — {result['fourth_down'].get('reasoning', '')}")

    if st.session_state.show_debug:
        st.subheader("Debug Rankings")
        for family, score in sorted(result["scores"].items(), key=lambda x: x[1], reverse=True):
            st.write(f"- {family.replace('_', ' ').title()}: {format_score(score)}")


# ---------- Sidebar ----------
st.sidebar.title("Controls")

st.session_state.compact_mode = st.sidebar.toggle(
    "One-screen mode",
    value=st.session_state.compact_mode,
)

example = st.sidebar.radio(
    "Quick examples",
    [
        "2nd & 7 at the opponents 43",
        "3rd & 6 at own 38",
        "1st & 10 at the opponents 24",
        "4th & 1 at the opponents 8",
        "2nd & 10 at own 40",
    ],
    index=0,
)

if st.sidebar.button("Use selected example"):
    st.session_state.last_input = example
    st.rerun()

if st.sidebar.button("New drive"):
    drive_log.reset()

st.session_state.show_debug = st.sidebar.toggle(
    "Show debug rankings",
    value=st.session_state.show_debug,
)

# ---------- Main ----------
st.title("🏈 Football Play Predictor")

situation_text = st.text_input(
    "Situation",
    value=st.session_state.last_input,
    placeholder="Enter a situation, e.g. 2nd & 7 at the opponents 43",
)

st.markdown("#### Game Context")
gc1, gc2, gc3, gc4, gc5 = st.columns(5)
with gc1:
    quarter = st.radio("Quarter", [1, 2, 3, 4], horizontal=True, index=1)
with gc2:
    clock_mode = st.selectbox("Clock Mode", ["Normal", "2-Minute", "Must Score", "Drain Clock", "Two-Point"], index=0)
with gc3:
    score_state = st.radio("Score State", ["Leading", "Tied", "Trailing", "Big Lead", "Big Deficit"], horizontal=False, index=1)
with gc4:
    own_tos = st.radio("Own TOs", [0, 1, 2, 3], horizontal=True, index=3)
with gc5:
    opp_tos = st.radio("Opp TOs", [0, 1, 2, 3], horizontal=True, index=3)

st.markdown("#### Defensive Read")
d1, d2, d3, d4, d5 = st.columns(5)
with d1:
    def_personnel = st.selectbox("Def Personnel", ["Unknown", "Base", "Nickel", "Dime", "Goal Line"], index=0)
with d2:
    shell = st.selectbox("Shell", ["Unknown", "Cover 0", "Cover 1", "Cover 2", "Cover 3", "Cover 4", "Quarters"], index=0)
with d3:
    safeties = st.radio("Safeties", ["Unknown", "1 High", "2 High"], horizontal=True, index=0)
with d4:
    box_count = st.radio("Box", [6, 7, 8, 9], horizontal=True, index=1)
with d5:
    blitz_likely = st.toggle("Blitz Likely", value=False)

st.markdown("#### Offense / Environment")
o1, o2, o3, o4, o5 = st.columns(5)
with o1:
    offensive_personnel = st.radio("Off Personnel", ["10", "11", "12", "21", "22"], horizontal=True, index=1)
with o2:
    weather = st.radio("Weather", ["Clear", "Wind", "Rain", "Snow"], horizontal=False, index=0)
with o3:
    turf = st.radio("Surface", ["Turf", "Grass"], horizontal=True, index=0)
with o4:
    qb_limited = st.toggle("QB Limited", value=False)
with o5:
    matchup = st.selectbox("Matchup Focus", ["None", "WR Matchup", "Slot Matchup", "Run Box"], index=0)

a1, a2, a3 = st.columns([1, 1, 1])
with a1:
    run_btn = st.button("Predict Call", use_container_width=True)
with a2:
    clear_btn = st.button("Clear Screen", use_container_width=True)
with a3:
    log_run_btn = st.button("Log + Run", use_container_width=True)

if clear_btn:
    st.session_state.last_input = ""
    st.session_state.last_result = None
    st.rerun()

if log_run_btn and st.session_state.last_result is not None:
    play = st.session_state.last_result["play"]
    family = st.session_state.last_result["play_family"]
    drive_log.log(
        type("PlayResult", (), {
            "concept_name": play.get("name", ""),
            "family": family,
            "yards_gained": 0,
            "outcome": "short",
        })()
    )

if run_btn:
    cleaned = situation_text.strip()
    if not cleaned:
        st.warning("Enter a situation first.")
    else:
        st.session_state.last_input = cleaned
        try:
            ctx = build_context_from_ui(
                cleaned,
                score_state,
                quarter,
                clock_mode,
                own_tos,
                opp_tos,
                def_personnel,
                shell,
                safeties,
                box_count,
                blitz_likely,
                offensive_personnel,
                weather,
                turf,
                qb_limited,
                matchup,
            )
            result = predictor.recommend(ctx, drive_log)
            calls = build_alternative_calls(result, ctx)
            st.session_state.last_result = {
                "ctx": ctx,
                "result": result,
                "calls": calls,
            }
        except Exception as e:
            st.session_state.last_result = None
            st.error(str(e))

if st.session_state.last_result is not None:
    payload = st.session_state.last_result
    ctx = payload["ctx"]
    result = payload["result"]
    calls = payload["calls"]

    if st.session_state.compact_mode:
        render_compact_mode(ctx, result, calls)
    else:
        render_standard_mode(ctx, result, calls)
else:
    st.info("Enter a situation, tap the context buttons you want, then click Predict Call.")