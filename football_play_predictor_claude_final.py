"""
football_play_predictor.py — Sideline OC play-calling assistant
Enhanced with defensive reads, game script, drive logging, 4th-down advisor,
two-point shelf, weather/turf adjustments, coverage-specific notes, and
tendency tracking.
"""

import re
import random
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Tuple


# ──────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ──────────────────────────────────────────────────────────────────────────────

RUN_FAMILIES  = {"inside_zone", "outside_zone", "duo", "power", "draw"}
PASS_FAMILIES = {"quick_game", "dropback_pass", "screen", "play_action", "fade_iso"}
FG_RANGE_YARDLINE = 35   # opponents' 35 ≈ 52-yard attempt — makeable for most kickers


# ──────────────────────────────────────────────────────────────────────────────
# DATA STRUCTURES
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class GameContext:
    """Everything an OC would see at the line of scrimmage."""

    # ── Core situation ────────────────────────────────────────────────────────
    down: int
    distance: int
    yardline: int
    territory: str              # "own" | "opponents"

    # ── Game script ───────────────────────────────────────────────────────────
    score_diff: int = 0         # positive = offense winning
    quarter: int = 2
    seconds_remaining: int = 1800
    own_timeouts: int = 3
    opp_timeouts: int = 3

    # ── Defensive pre-snap read ───────────────────────────────────────────────
    def_personnel: str = "unknown"    # base | nickel | dime | goal_line | unknown
    box_count: int = 7
    coverage_shell: str = "unknown"   # cover_0|cover_1|cover_2|cover_3|cover_4|quarters|unknown
    blitz_likely: bool = False
    safeties: str = "unknown"         # single_high | two_high | unknown

    # ── Environment ───────────────────────────────────────────────────────────
    weather: str = "clear"            # clear | wind | rain | snow
    wind_mph: int = 0
    turf: str = "turf"                # grass | turf

    # ── Personnel & matchup ───────────────────────────────────────────────────
    personnel_group: str = "11"       # 10 | 11 | 12 | 21 | 22
    mismatch: Optional[str] = None    # free text, e.g. "slot CB is undersized"
    qb_limited: bool = False

    # ── Drive state ───────────────────────────────────────────────────────────
    plays_this_drive: int = 0
    shown_concepts: List[str] = field(default_factory=list)
    run_plays_this_drive: int = 0     # used by play-action qualifier

    # ── Game mode ─────────────────────────────────────────────────────────────
    game_mode: str = "normal"         # normal | must_score | drain_clock | two_minute | two_point


@dataclass
class PlayResult:
    concept_name: str
    family: str
    yards_gained: int
    outcome: str    # first_down | td | incomplete | sack | penalty | turnover | short


# ──────────────────────────────────────────────────────────────────────────────
# PLAY LIBRARY
# Each entry now includes: vs_man, vs_zone, kill_look, vulnerabilities,
# post_snap_alert, and optionally td_pct (red zone).
# ──────────────────────────────────────────────────────────────────────────────

PLAY_LIBRARY: Dict[str, List[Dict[str, Any]]] = {

    # ── QUICK GAME ────────────────────────────────────────────────────────────
    "quick_game": [
        {
            "name": "Stick",
            "personnel": "11",
            "formation": "Shotgun Trips Right",
            "protection": "6-man half-slide protection",
            "routes": {
                "X":  "Backside slant",
                "H":  "Stick route",
                "Y":  "Flat / arrow",
                "Z":  "Outside clear fade",
                "RB": "Check-release weak",
            },
            "vs_man":          "H should win the stick vs. press — attack the flat combo immediately.",
            "vs_zone":         "H settles in the hole between LB and flat defender; Y stretches the flat.",
            "kill_look":       "Cover 0 / zero blitz with bracket on the outside — check to RB hot.",
            "vulnerabilities": ["cover_0", "zero_blitz", "inside_bracket"],
            "post_snap_alert": "If single safety rotates high post-snap, Z fade is live on the back shoulder.",
            "why":             "High-percentage concept that attacks underneath leverage and gets the ball out quickly.",
        },
        {
            "name": "Spacing",
            "personnel": "11",
            "formation": "Shotgun Doubles",
            "protection": "5-man scat protection",
            "routes": {
                "X":  "Hitch",
                "H":  "Hook",
                "Y":  "Hook",
                "Z":  "Hitch",
                "RB": "Middle settle / checkdown",
            },
            "vs_man":          "Hitches beat off-coverage; X and Z need clean outside releases.",
            "vs_zone":         "Hooks find voids; RB middle settle is the safety valve.",
            "kill_look":       "Press-man with corner blitz — hitches will be covered tight; hot to RB.",
            "vulnerabilities": ["press_man", "corner_blitz", "cover_0"],
            "post_snap_alert": "If ILB drops to hook-curl zone, RB middle settle is immediate.",
            "why":             "Good versus zone; safe completion around the sticks.",
        },
        {
            "name": "Slant-Flat",
            "personnel": "11",
            "formation": "Shotgun Trips Left",
            "protection": "6-man slide protection",
            "routes": {
                "X":  "Boundary slant",
                "H":  "Flat",
                "Y":  "Seam clear",
                "Z":  "Backside dig sit",
                "RB": "Check-release strong",
            },
            "vs_man":          "X slant beats inside leverage immediately; flat is the quick answer vs. press.",
            "vs_zone":         "H flat pulls CB and opens X slant window; Z dig sits in vacated zone.",
            "kill_look":       "Cloud coverage on the trips side (CB over flat, safety over top) — work backside Z.",
            "vulnerabilities": ["cloud_coverage", "cover_3_buzz", "two_high_bracket"],
            "post_snap_alert": "If MIKE scrapes hard to the flat, Z backside dig sit is wide open.",
            "why":             "Simple read with a clean triangle on the front side.",
        },
    ],

    # ── DROPBACK PASS ─────────────────────────────────────────────────────────
    "dropback_pass": [
        {
            "name": "Dagger",
            "personnel": "11",
            "formation": "Shotgun Trips Right",
            "protection": "6-man half-slide with RB scan",
            "routes": {
                "X":  "Backside hitch",
                "H":  "Clear vertical seam",
                "Y":  "12-15 yard dig",
                "Z":  "Outside go / clear",
                "RB": "Check-release",
            },
            "vs_man":          "H clears the safety; Y dig is the primary read vs. man after the clear.",
            "vs_zone":         "H seam stresses the deep third; Y digs into the vacated MOF window.",
            "kill_look":       "Cover 0 / all-out blitz — get to quick game or screen immediately.",
            "vulnerabilities": ["cover_0", "all_out_blitz", "zero_coverage"],
            "post_snap_alert": "If safety jumps H seam early, Y dig window opens — throw it.",
            "why":             "Strong medium-to-long yardage concept; stresses safeties and opens the dig.",
        },
        {
            "name": "Drive",
            "personnel": "11",
            "formation": "Gun Doubles",
            "protection": "6-man protection",
            "routes": {
                "X":  "Dig",
                "H":  "Shallow cross",
                "Y":  "Sit over ball",
                "Z":  "Clear post",
                "RB": "Swing / outlet",
            },
            "vs_man":          "H shallow cross is hot vs. man; X dig beats trail technique.",
            "vs_zone":         "H clears underneath defenders; Y settles in the void behind them.",
            "kill_look":       "MIKE walks up to the line with no weak-side LB depth — check to draw or screen.",
            "vulnerabilities": ["cover_0", "fire_zone_3", "MIKE_blitz"],
            "post_snap_alert": "If Z clears two safeties, X dig is working single coverage.",
            "why":             "Reliable chain-mover against both man and zone.",
        },
        {
            "name": "Y-Cross",
            "personnel": "11",
            "formation": "Shotgun Trips Open",
            "protection": "7-man protection",
            "routes": {
                "X":  "Backside comeback",
                "H":  "Over / cross",
                "Y":  "Deep cross",
                "Z":  "Clear go",
                "RB": "Strong insert then check-release",
            },
            "vs_man":          "Y deep cross is a winner vs. man; Z clears the safety off the field.",
            "vs_zone":         "H and Y create layered stress across the field; attack the second level.",
            "kill_look":       "Tampa 2 — MIKE will drop to the deep middle and bracket Y; work H underneath.",
            "vulnerabilities": ["tampa_2", "cover_4_bracket", "robber_coverage"],
            "post_snap_alert": "If safety rotates to Z side, X comeback backside is single coverage.",
            "why":             "Creates layered cross-field stress; use when you need more than a quick throw.",
        },
    ],

    # ── SCREEN ────────────────────────────────────────────────────────────────
    "screen": [
        {
            "name": "RB Middle Screen",
            "personnel": "11",
            "formation": "Shotgun Doubles",
            "protection": "Invite the rush; OL delayed release",
            "routes": {
                "X":  "Clear outside",
                "H":  "Mandatory outside release",
                "Y":  "Clear seam",
                "Z":  "Clear vertical",
                "RB": "Middle screen",
            },
            "vs_man":          "Man coverage chases receivers downfield — clear path for the screen.",
            "vs_zone":         "Works if LBs are rushing; zone defenders dropping may read the screen.",
            "kill_look":       "Linebackers sitting in coverage with minimal rush — they will see this develop.",
            "vulnerabilities": ["spy_linebacker", "3_man_rush", "zone_drop"],
            "post_snap_alert": "If LBs drop to zones at the snap, check out at the line if possible.",
            "why":             "Good answer to long-yardage pressure looks.",
        },
        {
            "name": "Trips Bubble",
            "personnel": "11",
            "formation": "Trips Right",
            "protection": "Quick perimeter action",
            "routes": {
                "X":  "Backside glance",
                "H":  "Bubble",
                "Y":  "Block alley / stalk",
                "Z":  "Block corner / stalk",
                "RB": "Inside check",
            },
            "vs_man":          "Numbers game on the perimeter — should have a blocker advantage.",
            "vs_zone":         "Works if the overhang is aggressive; check MOFO safety alignment pre-snap.",
            "kill_look":       "Extra defender walked out over trips — they've matched numbers; check inside.",
            "vulnerabilities": ["pattern_match_cover_4", "extra_overhang", "trips_adjustment"],
            "post_snap_alert": "Count defenders on the perimeter pre-snap — if 3-on-3, look inside first.",
            "why":             "Simple space play if numbers are favorable.",
        },
    ],

    # ── PLAY ACTION ───────────────────────────────────────────────────────────
    "play_action": [
        {
            "name": "Boot Flood",
            "personnel": "12",
            "formation": "Singleback Twins",
            "protection": "Wide zone play-action boot protection",
            "routes": {
                "X":  "Backside post / crosser clear",
                "Y":  "Deep out",
                "H":  "Flat in boot path",
                "Z":  "Intermediate over",
                "RB": "Run fake then edge seal",
            },
            "vs_man":          "H flat in boot path should be open immediately vs. man rotating to run.",
            "vs_zone":         "Y deep out and H flat create a high-low on the perimeter defender.",
            "kill_look":       "Defense in pure pass look — they won't bite on the fake; PA loses its effect.",
            "vulnerabilities": ["cover_4", "quarters_pattern_match", "no_run_fill_defense"],
            "post_snap_alert": "If the corner sits flat, Y deep out is live — take the shot.",
            "why":             "Changes launch point and creates a clean high-low on the perimeter.",
        },
        {
            "name": "Y-Leak",
            "personnel": "12",
            "formation": "Singleback Ace",
            "protection": "Max protect play-action",
            "routes": {
                "X":  "Post clear",
                "Y":  "Delayed leak",
                "H":  "Deep crosser",
                "Z":  "Comeback",
                "RB": "Run fake / insert protect",
            },
            "vs_man":          "Y leak beats any linebacker in man coverage — automatic matchup win.",
            "vs_zone":         "Y leaks into the seam as H clears the intermediate level.",
            "kill_look":       "Two-high with LBs in hook-curl — Y leak will be bracketed; take H crosser.",
            "vulnerabilities": ["two_high_match", "cover_2_bracket", "linebacker_spy"],
            "post_snap_alert": "If strong safety attacks the Y fake, H deep crosser is one-on-one.",
            "why":             "Red-zone shot-play when the defense overreacts to run action.",
            "td_pct": 0.51,
        },
    ],

    # ── RUN GAME ──────────────────────────────────────────────────────────────
    "inside_zone": [
        {
            "name": "Inside Zone Strong",
            "personnel": "11",
            "formation": "Shotgun Trips Right",
            "run_scheme": "Inside zone to the strength",
            "blocking": "Covered/uncovered zone rules; RB presses front-side A/B gap",
            "vs_man":          "Key the double at the point of attack; MIKE movement sets the cut.",
            "vs_zone":         "Same read — RB presses until the front-side crease declares.",
            "kill_look":       "8-man box with LBs stacked on the line — check to a quick pass.",
            "vulnerabilities": ["8_man_box", "A_gap_blitz", "slant_away_from_call"],
            "post_snap_alert": "If MIKE scrapes to the frontside, RB cuts back to the backside A gap.",
            "why":             "Solid baseline run; stable box-count answer.",
        },
    ],

    "outside_zone": [
        {
            "name": "Outside Zone Weak",
            "personnel": "11",
            "formation": "Shotgun Doubles",
            "run_scheme": "Outside zone weak",
            "blocking": "Full stretch zone rules; RB reads EMLOS to inside cut",
            "vs_man":          "Stretch forces backside pursuit — RB can outrun pursuit angles.",
            "vs_zone":         "Same; cutback dependent on how defenders flow.",
            "kill_look":       "Weakside overhang walked up tight — he will wrong-arm the stretch.",
            "vulnerabilities": ["DE_wrong_arm", "overhang_spill", "backside_pursuit"],
            "post_snap_alert": "If EMLOS squeezes hard, RB bends back to the cutback lane immediately.",
            "why":             "Horizontal stress with cutback potential.",
        },
    ],

    "duo": [
        {
            "name": "Duo",
            "personnel": "12",
            "formation": "Singleback Doubles Tight",
            "run_scheme": "Duo downhill run",
            "blocking": "Double teams at point of attack; RB reads MIKE",
            "vs_man":          "Double teams at POA will move the line of scrimmage — downhill attack.",
            "vs_zone":         "MIKE scrape determines the cut: press playside A until he declares.",
            "kill_look":       "MIKE stacked inside with no movement — pure two-gapper; crease may not form.",
            "vulnerabilities": ["stacked_MIKE", "two_gap_nose", "A_gap_double_fill"],
            "post_snap_alert": "RB reads MIKE: if he goes backside, press the playside A gap hard.",
            "why":             "Short-yardage downhill answer without needing true pullers.",
        },
    ],

    "power": [
        {
            "name": "Power O",
            "personnel": "21",
            "formation": "I-Right",
            "run_scheme": "Power right",
            "blocking": "Backside guard pull; fullback leads through the play-side hole",
            "vs_man":          "Pulling guard and FB lead create defined assignment blocks.",
            "vs_zone":         "Forces teams to respect the gap scheme on the backside.",
            "kill_look":       "Backside LB crashing hard — he will meet the pulling guard and spill it.",
            "vulnerabilities": ["backside_LB_crash", "DE_spill_technique", "over_shifted_front"],
            "post_snap_alert": "FB reads the end: if DE squeezes, FB logs him and RB bounces outside.",
            "why":             "Classic gap scheme; defined entry point in tight-yardage situations.",
        },
    ],

    "draw": [
        {
            "name": "Shotgun Draw",
            "personnel": "11",
            "formation": "Shotgun Trips",
            "run_scheme": "Delayed draw",
            "blocking": "Pass-set sell; interior OL climbs late to second level",
            "vs_man":          "Pass rush creates natural lanes as OL climbs off their blocks.",
            "vs_zone":         "Zone defenders may read the delay; works best vs. heavy rushers.",
            "kill_look":       "Spy linebacker or 3-man rush — he will see the delay and fill the gap.",
            "vulnerabilities": ["spy_linebacker", "3_man_rush", "LB_draw_read"],
            "post_snap_alert": "If DEs are wide-rushing upfield, interior A/B gap opens as OL climbs.",
            "why":             "Pressure counter on longer downs.",
        },
    ],

    "fade_iso": [
        {
            "name": "Boundary Fade",
            "personnel": "11",
            "formation": "Shotgun Doubles",
            "protection": "5-man quick protection",
            "routes": {
                "X":  "Fade",
                "H":  "Speed out",
                "Y":  "Stick",
                "Z":  "Slant",
                "RB": "Check-release",
            },
            "vs_man":          "Fade wins on the back shoulder vs. off-coverage CB — trust the matchup.",
            "vs_zone":         "Limited; CB will drive downhill on the fade break.",
            "kill_look":       "CB is pressing — fade is 50/50 at best; consider slant-flat instead.",
            "vulnerabilities": ["press_coverage", "cover_2_corner", "inside_leverage"],
            "post_snap_alert": "If CB gives a hard outside release, throw back-shoulder fade immediately.",
            "why":             "Red-zone option when you trust the matchup outside.",
            "td_pct": 0.31,
        },
    ],

    # ── TWO-POINT CONVERSION SHELF ────────────────────────────────────────────
    "two_point": [
        {
            "name": "Rub / Pick Slant",
            "personnel": "11",
            "formation": "Shotgun Bunch Right",
            "protection": "5-man quick",
            "routes": {
                "X":  "Clear fade",
                "H":  "Inside rub / pick",
                "Y":  "Slant off the rub",
                "Z":  "Flat",
                "RB": "Check-release middle",
            },
            "vs_man":          "Rub creates a natural pick on the inside slant — primary read.",
            "vs_zone":         "Slant finds the void; flat stretches the defense wide.",
            "kill_look":       "Zone coverage — rub won't free anyone; work the flat or RB instead.",
            "vulnerabilities": ["zone_coverage", "bracket_bunch", "illegal_pick_call"],
            "post_snap_alert": "If CB follows H on the rub route, Y slant is wide open.",
            "why":             "Compressed end zone + man coverage = rub is the highest-percentage 2-pt call.",
        },
        {
            "name": "QB Power / Sneak",
            "personnel": "22",
            "formation": "I-Tight",
            "run_scheme": "QB power or sneak option",
            "blocking": "Double team at the center-guard gap; FB leads if QB keeps",
            "vs_man":          "Brute force — assignment blocking in tight space.",
            "vs_zone":         "Same — half a yard is all you need.",
            "kill_look":       "9-man box fully stacked — unlikely to move the pile; consider a pass.",
            "vulnerabilities": ["9_man_box", "no_crease"],
            "post_snap_alert": "QB reads the center gap: if it closes, keep and bounce off the FB shoulder.",
            "why":             "When you need a half-yard — most reliable short-yardage 2-pt option.",
        },
        {
            "name": "Shovel / RPO Bubble",
            "personnel": "11",
            "formation": "Shotgun Trips Left",
            "protection": "Run-pass option — mesh action",
            "routes": {
                "X":  "Backside clearout",
                "H":  "Bubble screen",
                "Y":  "Shovel path / mesh",
                "Z":  "Block / stalk",
                "RB": "Inside zone mesh",
            },
            "vs_man":          "Bubble wins vs. man if the outside is blocked; shovel beats an aggressive DE.",
            "vs_zone":         "Give read — if DE crashes, pull and throw bubble to numbers on the perimeter.",
            "kill_look":       "LB walked out over H pre-snap — perimeter numbers are even; stay with the shovel.",
            "vulnerabilities": ["pattern_match_cover_4", "cloud_coverage", "DE_contain"],
            "post_snap_alert": "Read the DE: if he crashes the mesh, pull and throw the bubble immediately.",
            "why":             "Puts the defense in conflict — can't stop both the run and the perimeter.",
        },
    ],
}


# ──────────────────────────────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────────────────────────────

def ordinal_suffix(n: int) -> str:
    return {1: "st", 2: "nd", 3: "rd"}.get(n, "th")


def fmt_time(seconds: int) -> str:
    m, s = divmod(abs(seconds), 60)
    return f"{m}:{s:02d}"


# ──────────────────────────────────────────────────────────────────────────────
# DRIVE LOGGER
# ──────────────────────────────────────────────────────────────────────────────

class DriveLogger:
    """Tracks play history within a drive for tendency analysis."""

    def __init__(self) -> None:
        self.results: List[PlayResult] = []
        self.family_counts: Dict[str, int] = {}

    def log(self, result: PlayResult) -> None:
        self.results.append(result)
        self.family_counts[result.family] = self.family_counts.get(result.family, 0) + 1

    def overuse_warning(self, family: str, threshold: int = 3) -> Optional[str]:
        count = self.family_counts.get(family, 0)
        if count >= threshold:
            label = family.replace("_", " ").title()
            return f"⚠  {label} called {count}x this drive — defense is keying on it."
        return None

    def run_pass_split(self) -> Tuple[int, int]:
        runs   = sum(1 for r in self.results if r.family in RUN_FAMILIES)
        passes = len(self.results) - runs
        return runs, passes

    def run_count(self) -> int:
        return sum(1 for r in self.results if r.family in RUN_FAMILIES)

    def reset(self) -> None:
        self.results.clear()
        self.family_counts.clear()

    def summary(self) -> str:
        if not self.results:
            return "Drive log: 0 plays."
        runs, passes = self.run_pass_split()
        total = len(self.results)
        lines = [f"Drive log: {total} play{'s' if total != 1 else ''} | {runs} run / {passes} pass"]
        if self.family_counts:
            breakdown = "  |  ".join(
                f"{k.replace('_', ' ')}: {v}"
                for k, v in sorted(self.family_counts.items(), key=lambda x: -x[1])
            )
            lines.append(f"  Concepts: {breakdown}")
        return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────────────
# FOURTH DOWN ADVISOR
# ──────────────────────────────────────────────────────────────────────────────

class FourthDownAdvisor:
    """
    Recommends go-for-it, field goal, or punt based on game context.
    Heuristic model — not a full EPA calculator.
    """

    def advise(self, ctx: GameContext) -> Dict[str, Any]:
        if ctx.down != 4:
            return {}

        in_fg_range  = ctx.territory == "opponents" and ctx.yardline <= FG_RANGE_YARDLINE
        fg_distance  = ctx.yardline + 17 if ctx.territory == "opponents" else None  # yardline + snap depth + end zone

        must_score = ctx.game_mode in ("must_score", "two_minute") or (
            ctx.score_diff < 0 and ctx.quarter == 4 and ctx.seconds_remaining < 300
        )

        # Goal line — always go for the TD
        if ctx.territory == "opponents" and ctx.yardline <= 2:
            return {
                "recommendation": "GO FOR IT",
                "reasoning":      "Goal line — take the touchdown.",
                "fg_distance":    None,
            }

        # Inside FG range, no desperation
        if in_fg_range and not must_score and ctx.distance > 3:
            return {
                "recommendation": "FIELD GOAL",
                "reasoning":      f"~{fg_distance}-yard attempt. Take the points unless a TD is mandatory.",
                "fg_distance":    fg_distance,
            }

        # Short to go — go for it
        if ctx.distance <= 1:
            return {
                "recommendation": "GO FOR IT",
                "reasoning":      "1 yard or less — the conversion rate far exceeds the field position risk.",
                "fg_distance":    fg_distance,
            }

        # Opponent's territory, short to medium, game not yet a blowout
        if ctx.territory == "opponents" and ctx.yardline <= 40 and ctx.distance <= 3:
            return {
                "recommendation": "GO FOR IT",
                "reasoning":      f"{ctx.distance} yards in opposing territory — field position favors the attempt.",
                "fg_distance":    fg_distance if in_fg_range else None,
            }

        # Must score — go for it regardless
        if must_score:
            return {
                "recommendation": "GO FOR IT",
                "reasoning":      "Game script demands the conversion — can't afford to punt.",
                "fg_distance":    fg_distance if in_fg_range else None,
            }

        # Default: punt if outside FG range
        return {
            "recommendation": "PUNT",
            "reasoning":      "Outside FG range — flip field position.",
            "fg_distance":    None,
        }


# ──────────────────────────────────────────────────────────────────────────────
# MAIN PREDICTOR
# ──────────────────────────────────────────────────────────────────────────────

class FootballPlayPredictor:

    def __init__(self) -> None:
        self.baselines: Dict[str, Dict[str, float]] = {
            "short_yardage": {
                "inside_zone": 0.58, "duo": 0.57, "power": 0.55,
                "quick_game": 0.50,  "play_action": 0.46,
            },
            "medium_yardage": {
                "inside_zone": 0.41,   "outside_zone": 0.40,
                "quick_game": 0.52,    "dropback_pass": 0.50,
                "screen": 0.45,        "play_action": 0.48,
            },
            "long_yardage": {
                "draw": 0.26,          "screen": 0.42,
                "quick_game": 0.39,    "dropback_pass": 0.49,
                "play_action": 0.34,
            },
            "red_zone": {
                "inside_zone": 0.43,   "power": 0.44,
                "quick_game": 0.53,    "play_action": 0.51,
                "fade_iso": 0.31,
            },
            "backed_up": {
                "inside_zone": 0.44,   "outside_zone": 0.42,
                "quick_game": 0.50,    "screen": 0.46,
                "dropback_pass": 0.41,
            },
        }
        self.play_library        = PLAY_LIBRARY
        self.fourth_down_advisor = FourthDownAdvisor()

    # ── Parsing ───────────────────────────────────────────────────────────────

    def parse_situation(self, text: str) -> Tuple[int, int, int, str]:
        pattern = re.compile(
            r"(?P<down>\d+)(?:st|nd|rd|th)\s*(?:&|and)\s*(?P<distance>\d+)"
            r"\s*at\s*(?:the\s*)?(?P<territory>own|opponents?)\s*(?P<yardline>\d+)",
            re.IGNORECASE,
        )
        match = pattern.search(text.strip())
        if not match:
            raise ValueError("Use format: '2nd & 7 at the opponents 43'")
        down      = int(match.group("down"))
        distance  = int(match.group("distance"))
        yardline  = int(match.group("yardline"))
        territory = "opponents" if match.group("territory").lower().startswith("opponent") else "own"
        return down, distance, yardline, territory

    def parse_defense(self, text: str, ctx: GameContext) -> None:
        """
        Compact defensive input.
        Examples: 'nickel 6 cover2'  |  'base 8 single blitz'  |  'dime quarters two high'
        """
        t = text.lower().strip()
        if not t or t == "unknown":
            return

        # Personnel
        for p in ("goal_line", "dime", "nickel", "base", "dollar"):
            if p.replace("_", " ") in t or p in t:
                ctx.def_personnel = p
                break

        # Box count — a single digit 4-9 (not part of a coverage number)
        m = re.search(r'\b([4-9])\b(?!\s*(?:yd|yard|man))', t)
        if m:
            ctx.box_count = int(m.group(1))

        # Coverage shell
        cover_map = {
            "cover 0": "cover_0", "cover0": "cover_0", "zero": "cover_0",
            "cover 1": "cover_1", "cover1": "cover_1",
            "man":     "cover_1",
            "cover 2": "cover_2", "cover2": "cover_2", "tampa": "cover_2",
            "cover 3": "cover_3", "cover3": "cover_3",
            "cover 4": "cover_4", "cover4": "cover_4",
            "quarters": "quarters",
        }
        for key, val in cover_map.items():
            if key in t:
                ctx.coverage_shell = val
                break

        # Safety depth
        if "single high" in t or "single" in t or "one high" in t:
            ctx.safeties = "single_high"
        elif "two high" in t or "2 high" in t:
            ctx.safeties = "two_high"

        # Infer safety depth from coverage if not set
        if ctx.safeties == "unknown":
            if ctx.coverage_shell in ("cover_0", "cover_1", "cover_3"):
                ctx.safeties = "single_high"
            elif ctx.coverage_shell in ("cover_2", "cover_4", "quarters"):
                ctx.safeties = "two_high"

        # Blitz
        if "blitz" in t or "pressure" in t or "fire zone" in t:
            ctx.blitz_likely = True

    def parse_game_script(self, text: str, ctx: GameContext) -> None:
        """
        Compact game-script input.
        Example: '-7 Q3 8:30 2/3'  means down 7, Q3, 8:30 left, 2 own TOs / 3 opp TOs
        """
        t = text.strip()
        if not t:
            return

        # Score diff — first signed or unsigned number
        m = re.search(r'([+-]?\d+)', t)
        if m:
            ctx.score_diff = int(m.group(1))

        # Quarter
        m = re.search(r'[Qq](\d)', t)
        if m:
            ctx.quarter = int(m.group(1))

        # Time  mm:ss
        m = re.search(r'(\d{1,2}):(\d{2})', t)
        if m:
            ctx.seconds_remaining = int(m.group(1)) * 60 + int(m.group(2))

        # Timeouts  X/Y
        m = re.search(r'\b([0-3])\s*/\s*([0-3])\b', t)
        if m:
            ctx.own_timeouts = int(m.group(1))
            ctx.opp_timeouts = int(m.group(2))

    # ── Situation bucket ──────────────────────────────────────────────────────

    def get_bucket(self, ctx: GameContext) -> str:
        if ctx.territory == "opponents" and ctx.yardline <= 20:
            return "red_zone"
        if ctx.territory == "own" and ctx.yardline <= 10:
            return "backed_up"
        if ctx.distance <= 2:
            return "short_yardage"
        if 3 <= ctx.distance <= 6:
            return "medium_yardage"
        return "long_yardage"

    # ── Game mode (auto-derived) ───────────────────────────────────────────────

    def derive_game_mode(self, ctx: GameContext) -> str:
        # Never override an explicit override
        if ctx.game_mode not in ("normal", ""):
            return ctx.game_mode

        two_minute = ctx.quarter in (2, 4) and ctx.seconds_remaining <= 120
        if two_minute:
            return "two_minute"

        must_score = (
            (ctx.score_diff <= -14 and ctx.quarter == 4) or
            (ctx.score_diff <= -8  and ctx.quarter == 4 and ctx.seconds_remaining <= 240)
        )
        if must_score:
            return "must_score"

        drain = ctx.score_diff >= 10 and ctx.quarter == 4 and ctx.seconds_remaining > 120
        if drain:
            return "drain_clock"

        return "normal"

    # ── Family scoring (all contextual adjustments) ───────────────────────────

    def score_families(self, ctx: GameContext, bucket: str) -> Dict[str, float]:
        scores = self.baselines[bucket].copy()

        def nudge(family: str, amount: float) -> None:
            if family in scores:
                scores[family] = round(scores[family] + amount, 3)

        # Down
        if ctx.down == 1:
            nudge("inside_zone",   +0.02)
            nudge("play_action",   +0.02)

        if ctx.down == 2 and ctx.distance >= 7:
            nudge("dropback_pass", +0.03)
            nudge("quick_game",    +0.02)

        if ctx.down == 3:
            nudge("dropback_pass", +0.04)
            if ctx.distance <= 4:
                nudge("quick_game",  +0.03)
            if ctx.distance >= 8:
                nudge("screen",      +0.02)

        # Box count
        if ctx.box_count <= 6:
            nudge("inside_zone",   +0.04)
            nudge("outside_zone",  +0.03)
            nudge("duo",           +0.02)
            nudge("dropback_pass", -0.02)
        elif ctx.box_count >= 8:
            nudge("inside_zone",   -0.04)
            nudge("duo",           -0.03)
            nudge("dropback_pass", +0.04)
            nudge("quick_game",    +0.03)

        # Coverage shell
        if ctx.coverage_shell in ("cover_0", "cover_1"):
            # Man coverage — play-action and screens are man-beaters
            nudge("play_action",   +0.05)
            nudge("screen",        +0.04)
            nudge("quick_game",    +0.03)
            nudge("dropback_pass", -0.03)
        elif ctx.coverage_shell == "cover_2":
            nudge("outside_zone",  +0.03)
            nudge("dropback_pass", +0.02)
            nudge("quick_game",    -0.02)
        elif ctx.coverage_shell == "cover_3":
            nudge("dropback_pass", +0.04)   # seam routes
        elif ctx.coverage_shell in ("cover_4", "quarters"):
            nudge("quick_game",    +0.05)   # underneath opens up
            nudge("draw",          +0.03)
            nudge("play_action",   -0.03)

        # Safety depth
        if ctx.safeties == "single_high":
            nudge("play_action",   +0.04)
            nudge("dropback_pass", +0.03)
        elif ctx.safeties == "two_high":
            nudge("quick_game",    +0.03)
            nudge("screen",        +0.02)
            nudge("dropback_pass", -0.02)

        # Blitz
        if ctx.blitz_likely:
            nudge("screen",        +0.05)
            nudge("quick_game",    +0.04)
            nudge("dropback_pass", -0.03)
            nudge("play_action",   -0.02)

        # Weather
        if ctx.weather == "wind" and ctx.wind_mph >= 20:
            nudge("play_action",   -0.05)
            nudge("dropback_pass", -0.04)
            nudge("inside_zone",   +0.04)
            nudge("quick_game",    +0.03)

        if ctx.weather in ("rain", "snow"):
            nudge("dropback_pass", -0.06)
            nudge("play_action",   -0.04)
            nudge("screen",        -0.03)
            nudge("inside_zone",   +0.05)
            nudge("duo",           +0.04)

        # Game mode
        if ctx.game_mode == "drain_clock":
            nudge("inside_zone",   +0.06)
            nudge("duo",           +0.04)
            nudge("power",         +0.03)
            nudge("dropback_pass", -0.05)
            nudge("screen",        -0.04)

        elif ctx.game_mode == "must_score":
            nudge("dropback_pass", +0.05)
            nudge("play_action",   +0.04)
            nudge("inside_zone",   -0.03)

        elif ctx.game_mode == "two_minute":
            nudge("quick_game",    +0.06)
            nudge("dropback_pass", +0.04)
            nudge("inside_zone",   -0.05)
            nudge("play_action",   -0.04)

        # QB limited
        if ctx.qb_limited:
            nudge("dropback_pass", -0.04)
            nudge("play_action",   -0.03)
            nudge("inside_zone",   +0.04)
            nudge("quick_game",    +0.03)

        # Play-action qualifier — degrade if run game hasn't been established
        if "play_action" in scores and ctx.run_plays_this_drive < 3:
            nudge("play_action",   -0.04)

        return scores

    def choose_family(self, ctx: GameContext, bucket: str) -> str:
        scores = self.score_families(ctx, bucket)

        if ctx.down == 4:
            if ctx.distance <= 2:
                preferred = ["duo", "power", "inside_zone", "quick_game"]
                filtered  = {k: v for k, v in scores.items() if k in preferred}
                if filtered:
                    return max(filtered, key=filtered.get)
            else:
                preferred = ["quick_game", "dropback_pass", "screen"]
                filtered  = {k: v for k, v in scores.items() if k in preferred}
                if filtered:
                    return max(filtered, key=filtered.get)

        return max(scores, key=scores.get)

    # ── Play selection (coverage-aware) ───────────────────────────────────────

    def choose_play(self, family: str, ctx: GameContext) -> Dict[str, Any]:
        candidates = self.play_library.get(family, [])
        if not candidates:
            return {"name": f"[No plays defined for {family}]", "why": ""}

        def find(name: str) -> Optional[Dict[str, Any]]:
            return next((p for p in candidates if p["name"] == name), None)

        if family == "quick_game":
            if ctx.distance <= 3:
                play = find("Stick")
                if play:
                    return play
            if ctx.distance >= 6:
                play = find("Slant-Flat")
                if play:
                    return play

        if family == "dropback_pass":
            if ctx.distance >= 8:
                play = find("Dagger")
                if play:
                    return play
            else:
                play = find("Drive")
                if play:
                    return play

        if family == "play_action":
            if ctx.territory == "opponents" and ctx.yardline <= 20:
                play = find("Y-Leak")
                if play:
                    return play

        return random.choice(candidates)

    # ── Coverage note ─────────────────────────────────────────────────────────

    def coverage_note(self, play: Dict[str, Any], ctx: GameContext) -> Optional[str]:
        if ctx.coverage_shell in ("cover_0", "cover_1"):
            return play.get("vs_man")
        if ctx.coverage_shell != "unknown":
            return play.get("vs_zone")
        return None

    # ── Play-action qualifier ─────────────────────────────────────────────────

    def pa_qualifier(self, family: str, ctx: GameContext) -> Optional[str]:
        if family != "play_action":
            return None
        if ctx.run_plays_this_drive < 3:
            return (
                f"⚠  Run not established ({ctx.run_plays_this_drive} run plays this drive) — "
                "play-action may not freeze linebackers. Consider running first."
            )
        return None

    # ── Main recommend ────────────────────────────────────────────────────────

    def recommend(self, ctx: GameContext, drive_log: Optional["DriveLogger"] = None) -> Dict[str, Any]:
        ctx.game_mode = self.derive_game_mode(ctx)

        # Two-point conversion short-circuit
        if ctx.game_mode == "two_point":
            candidates = self.play_library.get("two_point", [])
            play       = random.choice(candidates) if candidates else {}
            return {
                "ctx":             ctx,
                "bucket":          "two_point",
                "play_family":     "two_point",
                "play":            play,
                "fourth_down":     {},
                "pa_warning":      None,
                "coverage_note":   self.coverage_note(play, ctx) if play else None,
                "overuse_warning": drive_log.overuse_warning("two_point") if drive_log else None,
                "scores":          {},
            }

        bucket = self.get_bucket(ctx)
        scores = self.score_families(ctx, bucket)
        family = self.choose_family(ctx, bucket)
        play   = self.choose_play(family, ctx)

        return {
            "ctx":             ctx,
            "bucket":          bucket,
            "play_family":     family,
            "play":            play,
            "fourth_down":     self.fourth_down_advisor.advise(ctx),
            "pa_warning":      self.pa_qualifier(family, ctx),
            "coverage_note":   self.coverage_note(play, ctx),
            "overuse_warning": drive_log.overuse_warning(family) if drive_log else None,
            "scores":          scores,
        }


# ──────────────────────────────────────────────────────────────────────────────
# OUTPUT
# ──────────────────────────────────────────────────────────────────────────────

def pretty_print(result: Dict[str, Any], drive_log: DriveLogger) -> None:
    ctx: GameContext = result["ctx"]
    play   = result["play"]
    family = result["play_family"]
    bucket = result["bucket"]

    W = 62
    print(f"\n{'═' * W}")

    # ── Game mode banner ─────────────────────────────────────────────────────
    mode_banners = {
        "two_minute":  "🚨  TWO-MINUTE DRILL",
        "must_score":  "🚨  MUST SCORE",
        "drain_clock": "⏱   DRAIN THE CLOCK",
        "two_point":   "🎯  TWO-POINT CONVERSION",
    }
    if ctx.game_mode in mode_banners:
        print(f"  {mode_banners[ctx.game_mode]}")
        print(f"{'─' * W}")

    # ── 4th down decision ────────────────────────────────────────────────────
    fd = result.get("fourth_down", {})
    if fd:
        rec  = fd["recommendation"]
        icon = {"GO FOR IT": "✅", "FIELD GOAL": "🏈", "PUNT": "👟"}.get(rec, "•")
        print(f"  {icon}  4TH DOWN: {rec}")
        print(f"     {fd['reasoning']}")
        if fd.get("fg_distance"):
            print(f"     Estimated FG distance: ~{fd['fg_distance']} yards")
        print(f"{'─' * W}")

    # ── Situation summary ────────────────────────────────────────────────────
    suf = ordinal_suffix(ctx.down)
    terr_label = "Opp." if ctx.territory == "opponents" else "Own"
    print(f"  {ctx.down}{suf} & {ctx.distance}  |  {terr_label} {ctx.yardline}  "
          f"|  {bucket.replace('_', ' ').title()}")

    # Defensive read
    def_parts = []
    if ctx.def_personnel != "unknown":
        def_parts.append(ctx.def_personnel.replace("_", " ").title())
    def_parts.append(f"{ctx.box_count} in box")
    if ctx.coverage_shell != "unknown":
        def_parts.append(ctx.coverage_shell.replace("_", " ").upper())
    if ctx.safeties != "unknown":
        def_parts.append(ctx.safeties.replace("_", " ").title())
    if ctx.blitz_likely:
        def_parts.append("BLITZ")
    print(f"  Defense: {' | '.join(def_parts)}")

    # Score / clock
    score_label = f"+{ctx.score_diff}" if ctx.score_diff > 0 else str(ctx.score_diff)
    print(f"  Score: {score_label}  |  Q{ctx.quarter} {fmt_time(ctx.seconds_remaining)}"
          f"  |  TOs {ctx.own_timeouts}–{ctx.opp_timeouts}")

    # Environment
    env_parts = []
    if ctx.weather != "clear":
        mph_note = f" ({ctx.wind_mph} mph)" if ctx.wind_mph and ctx.weather == "wind" else ""
        env_parts.append(ctx.weather.title() + mph_note)
    if ctx.turf == "grass":
        env_parts.append("Grass")
    if ctx.qb_limited:
        env_parts.append("QB limited")
    if env_parts:
        print(f"  Conditions: {'  |  '.join(env_parts)}")

    # Mismatch
    if ctx.mismatch:
        print(f"  🎯 Mismatch flagged: {ctx.mismatch}")

    print(f"{'═' * W}")

    # ── Play ─────────────────────────────────────────────────────────────────
    if not play:
        print("  No play found.")
        return

    print(f"  PLAY: {play.get('name', 'Unknown')}   "
          f"({family.replace('_', ' ').title()})")
    print(f"  Personnel: {play.get('personnel', 'N/A')}  "
          f"|  Formation: {play.get('formation', 'N/A')}")

    if "protection" in play:
        print(f"  Protection: {play['protection']}")
    elif "blocking" in play:
        print(f"  Blocking: {play['blocking']}")

    if "run_scheme" in play:
        print(f"  Run scheme: {play['run_scheme']}")

    if "routes" in play:
        print(f"\n  Routes:")
        for player, route in play["routes"].items():
            print(f"    {player}:  {route}")

    # ── Coaching notes ────────────────────────────────────────────────────────
    print(f"\n{'─' * W}")

    print(f"  📋 Why: {play.get('why', '')}")

    # Coverage-specific note
    cov_note = result.get("coverage_note")
    if cov_note:
        shell_label = ctx.coverage_shell.replace("_", " ").upper()
        print(f"  📡 vs. {shell_label}: {cov_note}")
    else:
        # Show both if coverage is unknown
        if play.get("vs_man"):
            print(f"  📡 vs. MAN:  {play['vs_man']}")
        if play.get("vs_zone"):
            print(f"  📡 vs. ZONE: {play['vs_zone']}")

    # Kill look
    if play.get("kill_look"):
        print(f"  ⛔ Kill look: {play['kill_look']}")

    # Post-snap alert
    if play.get("post_snap_alert"):
        print(f"  👁  Post-snap: {play['post_snap_alert']}")

    # Play-action qualifier
    if result.get("pa_warning"):
        print(f"\n  {result['pa_warning']}")

    # Overuse / tendency warning
    if result.get("overuse_warning"):
        print(f"\n  {result['overuse_warning']}")

    # Weather advisory
    if ctx.weather in ("wind", "rain", "snow") and family in ("dropback_pass", "play_action"):
        advisory = {
            "wind":  f"Wind ({ctx.wind_mph} mph) will affect trajectory — prioritize shorter throws.",
            "rain":  "Wet conditions hurt timing and grip — shorten the route tree.",
            "snow":  "Snow affects footing and the catch radius — consider running instead.",
        }.get(ctx.weather, "")
        if advisory:
            print(f"  🌧  Weather: {advisory}")

    # Mismatch reminder
    if ctx.mismatch and "routes" in play:
        print(f"  🎯 Get the mismatch involved: {ctx.mismatch}")

    # Red zone scoring probability
    if bucket == "red_zone" and "td_pct" in play:
        print(f"  📊 Estimated TD%: {play['td_pct']:.0%}")

    # Tempo
    if ctx.game_mode == "two_minute":
        tos = ctx.own_timeouts
        print(f"  ⏱  Tempo: HURRY-UP — {tos} timeout{'s' if tos != 1 else ''} remaining. "
              "Spike or go OOB to stop the clock.")
    elif ctx.game_mode == "drain_clock":
        print(f"  ⏱  Tempo: MILK IT — long pre-snap cadence, stay in bounds, burn the clock.")

    # Snap count
    if ctx.blitz_likely:
        print(f"  🎙  Snap count: Hard count — see if they jump before the snap.")

    # ── Drive summary ─────────────────────────────────────────────────────────
    print(f"\n{'─' * W}")
    print(f"  {drive_log.summary()}")
    print(f"{'═' * W}")


# ──────────────────────────────────────────────────────────────────────────────
# TEST SUITE
# ──────────────────────────────────────────────────────────────────────────────

TEST_CASES: List[Dict[str, Any]] = [
    {"situation": "1st & 10 at own 25",           "defense": "nickel 7 cover3",         "script": "0 Q2 10:00"},
    {"situation": "2nd & 7 at the opponents 43",  "defense": "nickel 6 cover2",          "script": "-3 Q3 6:30"},
    {"situation": "3rd & 8 at own 35",            "defense": "dime 5 quarters two high", "script": "-7 Q4 4:00 2/3"},
    {"situation": "4th & 1 at the opponents 2",   "defense": "goal_line 9 cover0",       "script": "3 Q4 1:30"},
    {"situation": "4th & 12 at own 48",           "defense": "nickel 6 cover3",          "script": "-14 Q4 3:00"},
    {"situation": "1st & 10 at the opponents 15", "defense": "nickel 7 cover2",          "script": "7 Q2 5:00"},
    {"situation": "3rd & 3 at own 8",             "defense": "base 7 cover3",            "script": "0 Q3 8:00"},
    {"situation": "2nd & 10 at own 40",           "defense": "nickel 7 blitz",           "script": "0 Q4 1:45 1/3", "extras": ""},
]


def run_tests(predictor: FootballPlayPredictor) -> None:
    for tc in TEST_CASES:
        try:
            down, distance, yardline, territory = predictor.parse_situation(tc["situation"])
            ctx = GameContext(down=down, distance=distance, yardline=yardline, territory=territory)
            predictor.parse_defense(tc.get("defense", ""), ctx)
            predictor.parse_game_script(tc.get("script", ""), ctx)
            log = DriveLogger()
            result = predictor.recommend(ctx, log)
            pretty_print(result, log)
        except Exception as e:
            print(f"Error on '{tc['situation']}': {e}")


# ──────────────────────────────────────────────────────────────────────────────
# INTERACTIVE REPL
# ──────────────────────────────────────────────────────────────────────────────

def prompt(label: str, default: str = "") -> str:
    hint = f" [{default}]" if default else ""
    val  = input(f"  {label}{hint}: ").strip()
    return val if val else default


def run_interactive(predictor: FootballPlayPredictor, drive_log: DriveLogger) -> None:
    W = 62
    print(f"\n{'═' * W}")
    print("  FOOTBALL PLAY PREDICTOR — SIDELINE OC")
    print(f"{'─' * W}")
    print("  Situation:  '3rd & 8 at the opponents 35'")
    print("  Defense:    'nickel 6 cover2 blitz'")
    print("  Script:     '-7 Q4 4:20 2/3'  (score / quarter / time / TOs)")
    print("  Extras:     'wind25'  'rain'  'grass'  'qblimited'  '2pt'")
    print("              'mismatch: slot cb is slow'")
    print(f"{'─' * W}")
    print("  Commands:   'new drive'  |  'log'  |  'test'  |  'quit'")
    print(f"{'═' * W}")

    while True:
        print()
        raw = input("  Situation: ").strip()

        if not raw:
            continue
        if raw.lower() in {"quit", "exit", "q"}:
            print("  Exiting.")
            break
        if raw.lower() in {"new drive", "new"}:
            drive_log.reset()
            print("  Drive log reset.\n")
            continue
        if raw.lower() == "log":
            print(f"\n  {drive_log.summary()}")
            continue
        if raw.lower() == "test":
            print("\n  --- Running test cases ---")
            run_tests(predictor)
            continue

        # Parse core situation
        try:
            down, distance, yardline, territory = predictor.parse_situation(raw)
        except ValueError as e:
            print(f"  Error: {e}")
            continue

        ctx = GameContext(
            down=down, distance=distance,
            yardline=yardline, territory=territory,
            plays_this_drive=len(drive_log.results),
            shown_concepts=list(drive_log.family_counts.keys()),
            run_plays_this_drive=drive_log.run_count(),
        )

        # Defensive read
        def_raw = prompt("Defense [personnel/box/coverage/blitz]", "unknown")
        predictor.parse_defense(def_raw, ctx)

        # Game script
        script_raw = prompt("Script [score Q# mm:ss own/opp TOs]", "0 Q2")
        predictor.parse_game_script(script_raw, ctx)

        # Optional extras
        extras_raw = prompt("Extras [wind# / rain / snow / grass / qblimited / 2pt / mismatch:...]", "")
        if extras_raw:
            e = extras_raw.lower()
            if "2pt" in e or "two point" in e or "two-point" in e:
                ctx.game_mode = "two_point"
            if "qblimited" in e or "qb limited" in e or "qb_limited" in e:
                ctx.qb_limited = True
            if "grass" in e:
                ctx.turf = "grass"
            m = re.search(r'wind\s*(\d+)', e)
            if m:
                ctx.weather  = "wind"
                ctx.wind_mph = int(m.group(1))
            elif "wind" in e:
                ctx.weather  = "wind"
                ctx.wind_mph = 15
            if "rain" in e:
                ctx.weather = "rain"
            if "snow" in e:
                ctx.weather = "snow"
            mm = re.search(r'mismatch[:\s]+(.+)', extras_raw, re.IGNORECASE)
            if mm:
                ctx.mismatch = mm.group(1).strip()

        # Recommend
        result = predictor.recommend(ctx, drive_log)
        pretty_print(result, drive_log)

        # Feedback / drive log
        yards_raw = prompt("Result [yards gained, or skip]", "skip").strip().lower()
        if yards_raw not in ("skip", "s", ""):
            m = re.search(r'-?\d+', yards_raw)
            if m:
                yards = int(m.group())
                if yards >= ctx.distance:
                    outcome = "first_down"
                elif yards < -3:
                    outcome = "sack"
                else:
                    outcome = "short"
                drive_log.log(PlayResult(
                    concept_name=result["play"].get("name", ""),
                    family=result["play_family"],
                    yards_gained=yards,
                    outcome=outcome,
                ))
                print(f"  Logged: {yards:+d} yards ({outcome})")


# ──────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    predictor  = FootballPlayPredictor()
    drive_log  = DriveLogger()
    run_interactive(predictor, drive_log)
