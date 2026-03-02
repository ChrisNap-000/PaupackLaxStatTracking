# =============================================================================
# Women's Lacrosse Analytics - Streamlit App
# =============================================================================
# This app loads three Excel files (FactTable, DimSchedule, DimPlayers),
# merges them together, and displays stats across four pages:
#   1. Team Stats   - Overall team performance metrics and charts
#   2. Player Stats - Individual player deep-dive
#   3. Specialist   - Goalie save stats and draw control stats
#   4. Box Stats    - Full filterable stat table (like a box score)
#
# No data is stored between sessions. The user uploads files each time,
# which keeps player data private.
# =============================================================================

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

# -----------------------------------------------------------------------------
# APP CONFIGURATION
# Must be the very first Streamlit call in the script
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Women's Lacrosse Stats",
    page_icon="🥍",
    layout="wide",           # Use full browser width instead of centered column
    initial_sidebar_state="collapsed",
)

# Inject a single global CSS rule to center all page titles (h1) and
# section subheaders (h2) across every tab from one place.
st.markdown(
    "<style>h1, h2 { text-align: center; }</style>",
    unsafe_allow_html=True
)

# -----------------------------------------------------------------------------
# COLOR CONSTANTS
# Define our purple/black theme colors in one place so they're easy to update
# -----------------------------------------------------------------------------
PURPLE   = "#8B2FC9"    # Main purple
PURPLE_L = "#B060E8"    # Lighter purple (for secondary charts/lines)
PURPLE_D = "#5A1A8A"    # Darker purple (for backgrounds, borders)
BLACK    = "#0D0D0D"    # Near-black background
DARK     = "#1A1A2E"    # Slightly lighter dark (card backgrounds)
TEXT     = "#F0F0F0"    # Off-white text
MUTED    = "#A0A0C0"    # Dimmed text for labels
ACCENT   = "#E040FB"    # Bright pink-purple for highlighted values

# -----------------------------------------------------------------------------
# SHARED PLOTLY LAYOUT SETTINGS
# We apply this dictionary to every chart so they all look consistent.
# "paper_bgcolor" is the area outside the chart, "plot_bgcolor" is inside.
# -----------------------------------------------------------------------------
BASE_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",   # Transparent so the page background shows
    plot_bgcolor="rgba(0,0,0,0)",    # Transparent chart interior
    font=dict(family="sans-serif", color=TEXT),

    legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color=TEXT)),
    xaxis=dict(gridcolor="#2a2a4a", linecolor="#2a2a4a", tickfont=dict(color=MUTED)),
    yaxis=dict(gridcolor="#2a2a4a", linecolor="#2a2a4a", tickfont=dict(color=MUTED)),
)

def apply_layout(fig, **kwargs):
    """
    Apply our standard dark theme layout to any Plotly figure.
    **kwargs lets us pass in extra overrides (like height or axis titles)
    without rewriting the whole layout every time.

    We merge BASE_LAYOUT and kwargs into a single dict before calling
    update_layout. kwargs is merged second so its values take priority
    over BASE_LAYOUT when the same key appears in both — this prevents
    the 'multiple values for keyword argument' error that occurs when
    both dicts contain the same key (e.g. legend, margin).
    """
    merged = {**BASE_LAYOUT, **kwargs}
    fig.update_layout(**merged)
    return fig


# -----------------------------------------------------------------------------
# SESSION STATE INITIALIZATION
# Streamlit re-runs the entire script on every interaction, so we use
# st.session_state (a dictionary that persists across reruns) to remember
# which page the user is on and whether data has been loaded.
# -----------------------------------------------------------------------------
if "page" not in st.session_state:
    st.session_state.page = "Team Stats"

if "data_loaded" not in st.session_state:
    st.session_state.data_loaded = False


# -----------------------------------------------------------------------------
# DATA LOADING
# We use @st.cache_data so that if the same files are uploaded again,
# Streamlit skips re-reading them and returns the cached result instead.
# This makes the app faster.
# -----------------------------------------------------------------------------
@st.cache_data
def load_data(fact_bytes, schedule_bytes, players_bytes):
    """
    Read the three uploaded Excel files into pandas DataFrames.
    We convert the Date columns to proper datetime objects so we can
    filter and sort by date correctly.
    """
    fact     = pd.read_excel(fact_bytes)
    schedule = pd.read_excel(schedule_bytes)
    players  = pd.read_excel(players_bytes)

    # Convert date strings like "2025-03-08" into actual datetime objects
    fact["Date"]     = pd.to_datetime(fact["Date"])
    schedule["Date"] = pd.to_datetime(schedule["Date"])

    # --- NULL REPLACEMENT ---
    # select_dtypes(include="number") returns only columns with numeric data
    # types (int, float). We fill nulls with 0 on all three tables so that
    # .sum() and other aggregations never return NaN due to missing entries.
    # Text columns like PlayerName and PenType are left untouched — replacing
    # their nulls with 0 would corrupt the data and break filters.
    fact[fact.select_dtypes(include="number").columns]         = fact.select_dtypes(include="number").fillna(0)
    schedule[schedule.select_dtypes(include="number").columns] = schedule.select_dtypes(include="number").fillna(0)
    players[players.select_dtypes(include="number").columns]   = players.select_dtypes(include="number").fillna(0)

    return fact, schedule, players


# -----------------------------------------------------------------------------
# MERGE HELPER
# Most pages need player names, positions, and opponent names attached to
# each row of the fact table. This function does those joins once.
# -----------------------------------------------------------------------------
def get_merged(fact, players, schedule):
    """
    Join the FactTable with DimPlayers (to get name/position/jersey) and
    with DimSchedule (to get opponent name and win/loss).
    We use a left join so every row in the fact table is kept even if
    there's no matching row in the other tables.
    """
    df = fact.merge(players, on="PlayerID", how="left")
    df = df.merge(
        schedule[["Date", "OpponentName", "Won?"]],
        on="Date",
        how="left"
    )
    return df


# -----------------------------------------------------------------------------
# NAVIGATION BAR
# Displays four buttons across the top. When clicked, we update session_state
# and call st.rerun() to reload the page with the new selection active.
# -----------------------------------------------------------------------------
# Add logo
logo_url = "LaxLogo.jpg"

# Center logo using columns: empty column on left and right, logo in the middle
col1, col2, col3 = st.columns([3.5, 1, 3.5])
with col2:
    st.image(logo_url, width=200)

PAGES = ["Team Stats", "Player Stats", "Specialist", "Box Stats"]

def nav_bar():
    """Render the top navigation buttons."""
    cols = st.columns(len(PAGES))
    for i, page_name in enumerate(PAGES):
        # Highlight the currently active page with a different button type
        btn_type = "primary" if st.session_state.page == page_name else "secondary"
        if cols[i].button(page_name, key=f"nav_{page_name}",
                          use_container_width=True, type=btn_type):
            st.session_state.page = page_name
            st.rerun()


# -----------------------------------------------------------------------------
# KPI METRIC HELPER
# Wraps st.metric so we don't repeat the same styling call everywhere.
# -----------------------------------------------------------------------------
def show_kpi(label, value):
    """
    Display a single KPI metric inside a bordered, centered container.
    st.columns(1) creates a single-column layout that correctly inherits
    the parent column context and reliably renders the border — a plain
    st.container(border=True) can lose the border when called from inside
    another column via a function. Using [0] grabs the single column out
    of the list that st.columns() always returns.

    The markdown block injects a small scoped CSS rule that centers the
    metric label and value text inside this specific container. We target
    the data-testid attributes Streamlit uses internally on metric elements.
    """
    with st.columns(1)[0]:
        with st.container(border=True):
            st.markdown(
                """
                <style>
                [data-testid="stMetric"] { text-align: center; }
                [data-testid="stMetricLabel"] {
                    justify-content: center;
                    display: block;
                    text-align: center;
                    width: 100%;
                }
                [data-testid="stMetricLabel"] > div {
                    text-align: center;
                    width: 100%;
                }
                [data-testid="stMetricValue"] { justify-content: center; }
                </style>
                """,
                unsafe_allow_html=True
            )
            st.metric(label=label, value=value)


# -----------------------------------------------------------------------------
# DATE HIERARCHY FILTER
# Renders three chained dropdowns: Year → Month → Day.
# Each level narrows the available options in the next level down.
# Returns a filtered copy of the schedule based on whatever levels were selected.
#
# The key_prefix argument makes each set of dropdowns unique on the page.
# Streamlit requires every widget to have a unique key — without a prefix,
# two pages using this function would try to create widgets with the same key
# and throw an error.
# -----------------------------------------------------------------------------
def date_hierarchy_filter(schedule, key_prefix):
    """
    Render Year / Month / Day dropdowns and return a filtered schedule DataFrame.
    Any level left at 'All' means that level is not applied as a filter.
    """
    # Extract available years from the schedule for the first dropdown
    years = ["All"] + sorted(schedule["Date"].dt.year.unique().tolist(), reverse=True)
    col1, col2, col3 = st.columns(3)

    # --- YEAR DROPDOWN ---
    sel_year = col1.selectbox("Year", years, key=f"{key_prefix}_year")

    # Narrow the schedule to the selected year before building month options.
    # This ensures Month only shows months that actually exist in that year.
    sched_y = schedule.copy()
    if sel_year != "All":
        sched_y = sched_y[sched_y["Date"].dt.year == sel_year]

    # --- MONTH DROPDOWN ---
    # Use month number for filtering but display the full month name for readability.
    # We build a dict {month_number: "Month Name"} from the filtered schedule.
    month_nums   = sorted(sched_y["Date"].dt.month.unique().tolist())
    month_labels = {m: pd.Timestamp(2000, m, 1).strftime("%B") for m in month_nums}
    month_options = ["All"] + [month_labels[m] for m in month_nums]

    sel_month_label = col2.selectbox("Month", month_options, key=f"{key_prefix}_month")

    # Convert the selected month name back to its number for filtering
    # by reversing the month_labels dict
    label_to_num  = {v: k for k, v in month_labels.items()}
    sel_month_num = label_to_num.get(sel_month_label)  # None if "All" was selected

    # Narrow further to the selected month before building day options
    sched_ym = sched_y.copy()
    if sel_month_label != "All":
        sched_ym = sched_ym[sched_ym["Date"].dt.month == sel_month_num]

    # --- DAY DROPDOWN ---
    # Only show days that exist in the already-filtered schedule
    days    = ["All"] + sorted(sched_ym["Date"].dt.day.unique().tolist())
    sel_day = col3.selectbox("Day", days, key=f"{key_prefix}_day")

    # --- APPLY ALL THREE LEVELS AND RETURN ---
    sched_f = sched_ym.copy()
    if sel_day != "All":
        sched_f = sched_f[sched_f["Date"].dt.day == sel_day]

    return sched_f


# =============================================================================
# UPLOAD SCREEN
# Shown when the app first loads and no data has been uploaded yet.
# =============================================================================
def upload_screen():
    """
    Show a file upload UI for all three required Excel files.
    Once all three are uploaded and the button is clicked, we load the data
    into session_state and set data_loaded = True, which triggers a rerun
    that takes the user to the main app.
    """
    st.title("🥍 Women's Lacrosse Analytics")
    st.write("Upload your three data files to get started. No data is stored — everything stays in your browser session.")
    st.divider()

    col1, col2, col3 = st.columns(3)

    with col1:
        st.subheader("FactTable")
        st.caption("One row per player per game")
        fact_file = st.file_uploader("FactTable", type=["xlsx", "csv"],
                                     label_visibility="collapsed", key="up_fact")
    with col2:
        st.subheader("DimSchedule")
        st.caption("One row per game (team-level data)")
        sched_file = st.file_uploader("DimSchedule", type=["xlsx", "csv"],
                                      label_visibility="collapsed", key="up_sched")
    with col3:
        st.subheader("DimPlayers")
        st.caption("Roster — one row per player")
        player_file = st.file_uploader("DimPlayers", type=["xlsx", "csv"],
                                       label_visibility="collapsed", key="up_players")

    # Only show the Load button once all three files have been selected
    if fact_file and sched_file and player_file:
        if st.button("Load Report", use_container_width=True, type="primary"):
            # Read files and store DataFrames directly in session_state
            fact, schedule, players = load_data(fact_file, sched_file, player_file)
            st.session_state.fact     = fact
            st.session_state.schedule = schedule
            st.session_state.players  = players
            st.session_state.data_loaded = True
            st.rerun()  # Reload the script — now data_loaded is True
    else:
        st.info("Upload all three files above, then click Load Report.")


# =============================================================================
# PAGE 1 — TEAM STATS
# Shows overall team performance: KPIs, woman-up gauge, goals over time,
# scatter of goals vs assists per player, wins/losses, and top scorers.
# =============================================================================
def page_team_stats(fact, schedule, players):
    st.title("Team Stats")

    # Build the merged DataFrame (fact + player info + opponent info)
    df = get_merged(fact, players, schedule)

    # --- FILTERS ---
    st.subheader("Filters")

    # Opponent dropdown sits above the date hierarchy
    opponents = ["All"] + sorted(schedule["OpponentName"].unique().tolist())
    sel_opp   = st.selectbox("Opponent", opponents, key="ts_opp")

    # Date hierarchy: Year -> Month -> Day, each narrowing the next.
    # date_hierarchy_filter returns an already-filtered schedule DataFrame.
    st.caption("Date Filter")
    sched_f = date_hierarchy_filter(schedule, key_prefix="ts")

    # Apply the opponent filter on top of whatever the date hierarchy returned
    if sel_opp != "All":
        sched_f = sched_f[sched_f["OpponentName"] == sel_opp]

    # Filter the merged fact table to only rows whose date is in sched_f
    df_f = df[df["Date"].isin(sched_f["Date"])]

    games_played = len(sched_f)

    # --- KPI CALCULATIONS ---
    # Guard against division by zero with "if games_played else 0"
    total_goals   = df_f["Goals"].sum()
    total_assists = df_f["Assists"].sum()
    goals_pg      = round(total_goals   / games_played, 1) if games_played else 0
    assists_pg    = round(total_assists / games_played, 1) if games_played else 0

    # Clearing %: how often we successfully clear the ball
    clear_atts  = sched_f["ClearAtts"].sum()
    clear_succ  = sched_f["ClearSuccesses"].sum()
    clearing_pct = f"{round(clear_succ / clear_atts * 100, 1)}%" if clear_atts else "N/A"

    # Riding %: how often we forced the opponent to fail their clear
    # Formula: (OppClearAtts - OppClearSuccesses) / OppClearAtts
    opp_clear_atts  = sched_f["OppClearAtts"].sum()
    opp_clear_succ  = sched_f["OppClearSuccesses"].sum()
    forced_fails    = opp_clear_atts - opp_clear_succ
    riding_pct = f"{round(forced_fails / opp_clear_atts * 100, 1)}%" if opp_clear_atts else "N/A"

    # Opponent goals per game
    opp_goals    = sched_f["OppGoals"].sum()
    opp_goals_pg = round(opp_goals / games_played, 1) if games_played else 0

    # --- KPI DISPLAY ---
    st.divider()
    k1, k2, k3, k4, k5 = st.columns(5)
    with k1: show_kpi("Goals PG",       goals_pg)
    with k2: show_kpi("Assists PG",     assists_pg)
    with k3: show_kpi("Clearing %",     clearing_pct)
    with k4: show_kpi("Riding %",       riding_pct)
    with k5: show_kpi("Opp Goals PG",   opp_goals_pg)

    st.divider()

    # --- ROW 2: W/L Donut + Team Goals Line Chart ---
    # W/L donut moved here (was in row 3), gauge moved to row 3
    left_col, right_col = st.columns([1, 2])

    with left_col:
        st.subheader("W / L")

        wins   = (sched_f["Won?"] == "Y").sum()
        losses = (sched_f["Won?"] == "N").sum()

        # Donut chart (pie with a hole in the middle)
        fig_wl = go.Figure(go.Pie(
            labels=["Wins", "Losses"],
            values=[wins, losses],
            hole=0.6,
            marker=dict(colors=[PURPLE, "#222244"]),
            textinfo="label+percent",
            textfont=dict(color=TEXT),
        ))
        apply_layout(fig_wl, height=500, showlegend=False,
                     margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig_wl, use_container_width=True, config={"displayModeBar": False})

    with right_col:
        st.subheader("Team Goals vs Opponent Goals by Game")

        # Aggregate total goals scored per game date from the fact table
        game_goals = df_f.groupby("Date")["Goals"].sum().reset_index()

        # Merge in opponent name, their goal total, OT flag, and result from schedule.
        # We need OT? and Won? to color the "Our Goals" markers conditionally.
        game_goals = game_goals.merge(
            sched_f[["Date", "OpponentName", "OppGoals", "OT?", "Won?"]],
            on="Date", how="left"
        )

        # Build a readable x-axis label: "Riverside HS<br>3/8"
        # Plotly renders <br> as a line break on axis tick labels,
        # whereas \n is ignored — so we use <br> to stack the date under the name.
        game_goals["Label"] = (
            game_goals["OpponentName"] + "<br>" +
            game_goals["Date"].dt.strftime("%-m/%-d")
        )

        # Determine marker color for each "Our Goals" point:
        #   Green  — OT game we won  (came back or held on in OT)
        #   Red    — OT game we lost
        #   ACCENT — regular (non-OT) game, no special color needed
        def our_goals_marker_color(row):
            if row["OT?"] == "Y" and row["Won?"] == "Y":
                return "#2ecc71"   # Green — OT win
            elif row["OT?"] == "Y" and row["Won?"] == "N":
                return "#e74c3c"   # Red — OT loss
            else:
                return ACCENT      # Default — non-OT game

        game_goals["MarkerColor"] = game_goals.apply(our_goals_marker_color, axis=1)

        fig_line = go.Figure()

        # Our team's goals — line stays ACCENT, markers change color per game
        fig_line.add_trace(go.Scatter(
            x=game_goals["Label"], y=game_goals["Goals"],
            mode="lines+markers", name="Our Goals",
            line=dict(color=ACCENT, width=2.5),
            marker=dict(color=game_goals["MarkerColor"], size=10,
                        line=dict(color=ACCENT, width=1))
        ))

        # Opponent's goals — neutral color so ours stands out
        fig_line.add_trace(go.Scatter(
            x=game_goals["Label"], y=game_goals["OppGoals"],
            mode="lines+markers", name="Opp Goals",
            line=dict(color="#888888", width=2.5),
            marker=dict(color=TEXT, size=7)
        ))

        # --- LEGEND ENTRIES FOR OT MARKER COLORS ---
        # We add a small caption below the chart using st.caption instead of
        # relying on Plotly dummy traces, which are unreliable across versions.
        # The caption clearly explains the green/red marker meaning to the user.
        apply_layout(fig_line, height=500,
            legend=dict(orientation="h", y=1.1, bgcolor="rgba(0,0,0,0)"),
            yaxis=dict(
                gridcolor="#2a2a4a", linecolor="#2a2a4a", tickfont=dict(color=MUTED),
                rangemode="tozero",
                dtick=1,
            ))
        st.plotly_chart(fig_line, use_container_width=True, config={"displayModeBar": False})

        # Caption explains the OT marker colors since Plotly legend entries
        # for mixed-color markers are unreliable across versions.
        # The colored squares are rendered using Unicode block characters.
        st.caption("🟢 Our Goals marker = OT Win   🔴 Our Goals marker = OT Loss")

    st.divider()

    # --- ROW 3: Woman-Up/Down Gauge + Scatter Plot + Top 5 Bar Chart ---
    # Gauge moved here from row 2. Toggle button switches between
    # Woman-Up % and Woman-Down % on the same gauge visual.
    col_a, col_b, col_c = st.columns([1, 2, 2])

    with col_a:
        # Toggle button: clicking it flips between Woman-Up and Woman-Down mode.
        # We store the current mode in session_state so it persists across reruns.
        if "gauge_mode" not in st.session_state:
            st.session_state.gauge_mode = "Woman-Up %"

        # The button label always shows the opposite mode (what you'll switch TO)
        btn_label = "Switch to Woman-Down %" if st.session_state.gauge_mode == "Woman-Up %" else "Switch to Woman-Up %"
        if st.button(btn_label, key="ts_gauge_toggle", use_container_width=True):
            # Flip the mode when clicked
            st.session_state.gauge_mode = (
                "Woman-Down %" if st.session_state.gauge_mode == "Woman-Up %" else "Woman-Up %"
            )
            st.rerun()

        st.subheader(st.session_state.gauge_mode)

        if st.session_state.gauge_mode == "Woman-Up %":
            # Woman-Up %: how often we score when we have the extra player
            # Formula: WomanUpGoals / WomanUpAtts
            wu_atts  = sched_f["WomanUpAtts"].sum()
            wu_goals = df_f["WomanUpGoals"].sum()
            gauge_val = round(wu_goals / wu_atts * 100, 1) if wu_atts else 0
        else:
            # Woman-Down %: how often we prevent the opponent from scoring
            # when they have the extra player (their woman-up situation)
            # Formula: (OppWomanUpAtts - OppWomanUpGoals) / OppWomanUpAtts
            opp_wu_atts  = sched_f["OppWomanUpAtts"].sum()
            opp_wu_goals = sched_f["OppWomanUpGoals"].sum()
            gauge_val = round((opp_wu_atts - opp_wu_goals) / opp_wu_atts * 100, 1) if opp_wu_atts else 0

        # Gauge chart — same visual for both modes, only the value changes
        fig_gauge = go.Figure(go.Indicator(
            mode="gauge+number",
            value=gauge_val,
            number={"suffix": "%", "font": {"size": 36, "color": ACCENT}},
            gauge={
                "axis":        {"range": [0, 100], "tickcolor": MUTED},
                "bar":         {"color": PURPLE},
                "bgcolor":     DARK,
                "bordercolor": PURPLE_D,
                "steps":       [{"range": [0, 100], "color": "#1a1a3e"}],
            }
        ))
        apply_layout(fig_gauge, height=500, margin=dict(l=20, r=20, t=10, b=10))
        st.plotly_chart(fig_gauge, use_container_width=True, config={"displayModeBar": False})

    with col_b:
        st.subheader("Goals vs Assists by Player")

        # Sum each player's total goals and assists across all filtered games
        scatter_df = df_f.groupby("PlayerName")[["Goals", "Assists"]].sum().reset_index()

        # --- REFERENCE LINE: y = x (equal goals and assists) ---
        # Players above the line score more than they assist (goal-heavy).
        # Players below the line assist more than they score (playmaker).
        # We extend the line slightly beyond the data range so it always
        # crosses the full chart area regardless of the data values.
        max_val = int(max(scatter_df["Assists"].max(), scatter_df["Goals"].max(), 1)) + 3
        line_x  = list(range(0, max_val + 1))
        line_y  = line_x  # y = 1x + 0, so y equals x at every point

        fig_sc = go.Figure()

        # --- SHADING: above the line (more goals than assists) ---
        # We draw a filled area from the line up to max_val.
        # The line color must be set (even if thin) because Plotly uses it
        # for the legend swatch — width=0 makes the border invisible on the
        # chart but the color still appears as the legend icon.
        fig_sc.add_trace(go.Scatter(
            x=line_x + line_x[::-1],   # Forward along top, then back along line
            y=[max_val] * len(line_x) + line_y[::-1],
            fill="toself",
            fillcolor="rgba(139, 47, 201, 0.25)",   # Purple — goal-heavy zone
            line=dict(color="rgba(139, 47, 201, 0.8)", width=0.5),
            showlegend=True,
            name="More Goals",
            hoverinfo="skip",           # Don't show tooltip on the shading
        ))

        # --- SHADING: below the line (more assists than goals) ---
        # Different color (teal/green) so the two zones are clearly distinct
        fig_sc.add_trace(go.Scatter(
            x=line_x + line_x[::-1],
            y=line_y + [0] * len(line_x),
            fill="toself",
            fillcolor="rgba(0, 200, 150, 0.15)",    # Teal — assist-heavy zone
            line=dict(color="rgba(0, 200, 150, 0.8)", width=0.5),
            showlegend=True,
            name="More Assists",
            hoverinfo="skip",
        ))

        # --- REFERENCE LINE: y = x drawn as a dashed line ---
        fig_sc.add_trace(go.Scatter(
            x=line_x, y=line_y,
            mode="lines",
            line=dict(color=MUTED, width=1.5, dash="dash"),
            showlegend=False,
            hoverinfo="skip",
        ))

        # --- PLAYER DATA POINTS on top of the shading ---
        # mode="markers" only — no text labels rendered on the chart.
        # customdata bundles extra columns onto each point so we can reference
        # them in hovertemplate. The order here (PlayerName, Goals, Assists)
        # maps to customdata[0], customdata[1], customdata[2] in the template.
        # <extra></extra> suppresses the default grey trace-name box in the tooltip.
        fig_sc.add_trace(go.Scatter(
            x=scatter_df["Assists"],
            y=scatter_df["Goals"],
            mode="markers",
            customdata=scatter_df[["PlayerName", "Goals", "Assists"]].values,
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                "Goals: %{customdata[1]}<br>"
                "Assists: %{customdata[2]}"
                "<extra></extra>"
            ),
            marker=dict(color=ACCENT, size=10, line=dict(color=PURPLE, width=1)),
            showlegend=False,
            name="Player",
        ))

        apply_layout(fig_sc, height=500,
            xaxis=dict(title="Total Assists", gridcolor="#2a2a4a",
                       tickfont=dict(color=MUTED), range=[0, max_val]),
            yaxis=dict(title="Total Goals",   gridcolor="#2a2a4a",
                       tickfont=dict(color=MUTED), range=[0, max_val]),
            legend=dict(orientation="h", y=1.08, bgcolor="rgba(0,0,0,0)",
                        font=dict(color=TEXT)))
        st.plotly_chart(fig_sc, use_container_width=True, config={"displayModeBar": False})

    with col_c:
        st.subheader("Top 5 Players by Points")

        # Calculate total points (goals + assists) per player, then take top 5
        pts = df_f.groupby("PlayerName").apply(
            lambda x: x["Goals"].sum() + x["Assists"].sum()
        ).reset_index()
        pts.columns = ["PlayerName", "Points"]
        top5 = pts.nlargest(5, "Points")

        fig_bar = go.Figure(go.Bar(
            x=top5["PlayerName"],
            y=top5["Points"],
            marker=dict(color=PURPLE, line=dict(color=ACCENT, width=1)),
            text=top5["Points"],
            textposition="outside",
            textfont=dict(color=TEXT),
        ))
        apply_layout(fig_bar, height=500,
                     xaxis=dict(tickfont=dict(size=11, color=TEXT)))
        st.plotly_chart(fig_bar, use_container_width=True, config={"displayModeBar": False})


# =============================================================================
# PAGE 2 — PLAYER STATS
# Deep-dive on a single player: KPIs, shooting %, goals over time, penalties.
# =============================================================================
def page_player_stats(fact, schedule, players):
    st.title("Player Stats")

    df = get_merged(fact, players, schedule)

    # --- FILTERS ---
    st.subheader("Filters")
    fcol1, fcol2 = st.columns(2)

    player_list = sorted(players["PlayerName"].unique().tolist())
    opponents   = ["All"] + sorted(schedule["OpponentName"].unique().tolist())

    sel_player = fcol1.selectbox("Player",   player_list, key="ps_player")
    sel_opp    = fcol2.selectbox("Opponent", opponents,   key="ps_opp")

    # Date hierarchy: Year -> Month -> Day, each narrowing the next.
    # date_hierarchy_filter returns an already-filtered schedule DataFrame.
    st.caption("Date Filter")
    

    # Filter schedule, then filter fact table to matching dates
    sched_f = schedule.copy()
    sched_f = date_hierarchy_filter(fact, key_prefix="ts")
    if sel_opp != "All":
        sched_f = sched_f[sched_f["OpponentName"] == sel_opp]

    df_f = df[
        (df["PlayerName"] == sel_player) &
        (df["Date"].isin(sched_f["Date"]))
    ]

    if df_f.empty:
        st.warning("No data found for the selected filters.")
        return

    # --- PLAYER INFO LOOKUP ---
    # .iloc[0] gets the first (and should be only) row for this player
    player_info = players[players["PlayerName"] == sel_player].iloc[0]
    jersey = player_info["JerseyNum"]
    pos    = player_info["Position"]

    # --- KPI CALCULATIONS ---
    gp      = len(df_f)                         # Games played = number of rows for this player
    goals   = int(df_f["Goals"].sum())
    assists = int(df_f["Assists"].sum())
    points  = goals + assists
    ppg     = round(points / gp, 1) if gp else 0
    gbs     = int(df_f["GBs"].sum())

    # --- PLAYER CARD + KPIs ---
    st.divider()

    # Player card (jersey + position) sits in its own column alongside the KPIs
    pc, k1, k2, k3, k4, k5 = st.columns([1, 1.2, 1.2, 1.2, 1.2, 1.2])

    with pc:
        # st.container(border=True) draws a simple outlined box — no HTML needed
        with st.container(border=True):
            st.metric(label="Jersey", value=f"#{jersey}")
            st.caption(f"**Position:** {pos}")

    with k1: show_kpi("PPG",          ppg)
    with k2: show_kpi("Points",       points)
    with k3: show_kpi("Goals",        goals)
    with k4: show_kpi("Assists",      assists)
    with k5: show_kpi("Ground Balls", gbs)

    st.divider()

    # --- ROW 2: Charts side by side ---
    left_col, right_col = st.columns(2)

    with left_col:
        # SHOOTING % DONUT — legend removed, labels on slices are sufficient
        st.subheader("Shooting %")
        shots  = int(df_f["Shots"].sum())
        missed = max(shots - goals, 0)   # max() prevents a negative value if data is off

        # "Shots<br>Missed" forces a line break in the slice label so both
        # labels fit vertically within their slices at the same orientation.
        fig_shoot = go.Figure(go.Pie(
            labels=["Goals", "Shots<br>Missed"],
            values=[goals, missed],
            hole=0.55,
            marker=dict(colors=[PURPLE, "#1a1a3e"]),
            textinfo="label+percent",
            textfont=dict(color=TEXT),
        ))
        apply_layout(fig_shoot, height=500, showlegend=False)
        st.plotly_chart(fig_shoot, use_container_width=True, config={"displayModeBar": False})

        # % OF POINTS FROM GOALS / ASSISTS GAUGE
        # Toggle button swaps between the two modes.
        # Goals %  = goals / points * 100
        # Assists % = 1 - Goals % (the remainder of points not from goals)
        if "ptg_mode" not in st.session_state:
            st.session_state.ptg_mode = "Goals"

        gc, ac = st.columns(2)
        if gc.button("Goals",   key="ptg_goals",
                     type="primary" if st.session_state.ptg_mode == "Goals" else "secondary",
                     use_container_width=True):
            st.session_state.ptg_mode = "Goals";   st.rerun()
        if ac.button("Assists", key="ptg_assists",
                     type="primary" if st.session_state.ptg_mode == "Assists" else "secondary",
                     use_container_width=True):
            st.session_state.ptg_mode = "Assists"; st.rerun()

        st.subheader(f"% of Points from {st.session_state.ptg_mode}")

        pct_from_goals   = round(goals   / points * 100, 1) if points else 0
        pct_from_assists = round(100 - pct_from_goals, 1)   # Remainder of points not from goals

        gauge_val = pct_from_goals if st.session_state.ptg_mode == "Goals" else pct_from_assists

        fig_ptg = go.Figure(go.Indicator(
            mode="gauge+number",
            value=gauge_val,
            number={"suffix": "%", "font": {"size": 34, "color": ACCENT}},
            gauge={
                "axis":        {"range": [0, 100], "tickcolor": MUTED},
                "bar":         {"color": PURPLE},
                "bgcolor":     DARK,
                "bordercolor": PURPLE_D,
                "steps":       [{"range": [0, 100], "color": "#1a1a3e"}],
            }
        ))
        apply_layout(fig_ptg, height=500, margin=dict(l=20, r=20, t=10, b=10))
        st.plotly_chart(fig_ptg, use_container_width=True, config={"displayModeBar": False})

    with right_col:
        # STAT OVER TIME LINE CHART
        # Three buttons let the user switch between Goals, Assists, and Points.
        # We store the current selection in session_state so it persists on rerun.
        st.subheader("Stats Over Time")

        if "ps_line_mode" not in st.session_state:
            st.session_state.ps_line_mode = "Goals"

        # Render three side-by-side buttons — highlight the active one as primary
        btn1, btn2, btn3 = st.columns(3)
        if btn1.button("Goals",   key="ps_line_goals",   type="primary" if st.session_state.ps_line_mode == "Goals"   else "secondary", use_container_width=True):
            st.session_state.ps_line_mode = "Goals";   st.rerun()
        if btn2.button("Assists", key="ps_line_assists", type="primary" if st.session_state.ps_line_mode == "Assists" else "secondary", use_container_width=True):
            st.session_state.ps_line_mode = "Assists"; st.rerun()
        if btn3.button("Points",  key="ps_line_points",  type="primary" if st.session_state.ps_line_mode == "Points"  else "secondary", use_container_width=True):
            st.session_state.ps_line_mode = "Points";  st.rerun()

        # Attach opponent names to each game row for x-axis labels
        time_df = df_f.merge(
            sched_f[["Date", "OpponentName"]], on="Date", how="left"
        )
        time_df["Label"] = (
            time_df["OpponentName"] + "<br>" +
            time_df["Date"].dt.strftime("%m-%d-%Y")
        )

        # Calculate Points column (not stored in fact table, derived here)
        time_df["Points"] = time_df["Goals"] + time_df["Assists"]

        # All three modes use the same ACCENT color — the button label makes
        # it clear which stat is showing, so different colors aren't needed.
        line_col = st.session_state.ps_line_mode

        fig_time = go.Figure()
        fig_time.add_trace(go.Scatter(
            x=time_df["Label"], y=time_df[line_col],
            mode="lines+markers", name=line_col,
            line=dict(color=ACCENT, width=2.5),
            marker=dict(size=7, color=ACCENT)
        ))

        apply_layout(fig_time, height=500,
            legend=dict(orientation="h", y=1.08, bgcolor="rgba(0,0,0,0)"),
            yaxis=dict(
                gridcolor="#2a2a4a", linecolor="#2a2a4a", tickfont=dict(color=MUTED),
                rangemode="tozero",  # y axis always starts at 0
                dtick=1,             # Force integer increments of 1
            ))
        st.plotly_chart(fig_time, use_container_width=True, config={"displayModeBar": False})

        # PENALTIES OVER TIME
        st.subheader("Penalty Minutes Over Time")

        # Only include rows where a penalty was recorded (non-null PenType)
        pen_df = df_f[df_f["PenType"].notna()].copy()

        fig_pen = go.Figure()

        if not pen_df.empty:
            # Merge OpponentName onto pen_df — df_f does not carry OpponentName
            # directly, it must be joined from sched_f using Date as the key.
            pen_df = pen_df.merge(
                sched_f[["Date", "OpponentName"]], on="Date", how="left"
            )
            pen_df["Label"] = (
                pen_df["OpponentName"] + "<br>" +
                pen_df["Date"].dt.strftime("%m-%d-%Y")
            )
            # Area chart: fill="tozeroy" shades the area under the line down to the x-axis
            fig_pen.add_trace(go.Scatter(
                x=pen_df["Label"], y=pen_df["MinsServed"],
                mode="lines+markers", fill="tozeroy",
                line=dict(color=PURPLE, width=2),
                fillcolor="rgba(139, 47, 201, 0.27)",  # PURPLE at 27% opacity
                marker=dict(size=7, color=ACCENT)
            ))
        else:
            # If no penalties, add a text annotation inside the empty chart
            fig_pen.add_annotation(
                text="No penalties recorded",
                x=0.5, y=0.5, xref="paper", yref="paper",
                showarrow=False, font=dict(color=MUTED, size=14)
            )

        apply_layout(fig_pen, height=500,
            yaxis=dict(
                title="Mins Served", gridcolor="#2a2a4a", tickfont=dict(color=MUTED),
                rangemode="tozero",  # y axis always starts at 0
                dtick=1,             # Force integer increments of 1
            ))
        st.plotly_chart(fig_pen, use_container_width=True, config={"displayModeBar": False})

    st.divider()

    # --- ADDITIONAL STATS ROW ---
    st.subheader("Additional Stats")

    # Count penalties by card type — value_counts() tallies each unique PenType.
    # .get(type, 0) safely returns 0 if that card type never appears for this player.
    pen_counts = df_f["PenType"].value_counts()

    # List of (label, value) tuples — easy to add or remove stats here
    extra_stats = [
        ("Caused TOs",       int(df_f["CTOs"].sum())),
        ("Turnovers",        int(df_f["TOs"].sum())),
        ("Shots PG",         round(df_f["Shots"].sum() / gp, 1) if gp else 0),
        ("Woman-Up Goals",   int(df_f["WomanUpGoals"].sum())),
        ("Woman-Down Goals", int(df_f["WomanDownGoals"].sum())),
        ("Games Played",     gp),
        ("12m Penalties",    int(pen_counts.get("12m",    0))),
        ("Green Cards",      int(pen_counts.get("Green",  0))),
        ("Yellow Cards",     int(pen_counts.get("Yellow", 0))),
        ("Red Cards",        int(pen_counts.get("Red",    0))),
    ]

    # Display in two rows of 5 so the layout stays readable
    row1 = extra_stats[:5]
    row2 = extra_stats[5:]

    cols1 = st.columns(len(row1))
    for i, (label, value) in enumerate(row1):
        with cols1[i]:
            show_kpi(label, value)

    st.write("")  # Small vertical gap between rows

    cols2 = st.columns(len(row2))
    for i, (label, value) in enumerate(row2):
        with cols2[i]:
            show_kpi(label, value)


# =============================================================================
# PAGE 3 — SPECIALIST
# Focuses on goalie save stats and draw control stats.
# Player filter is limited to Goalies and Midfielders only.
# =============================================================================
def page_specialist(fact, schedule, players):
    st.title("Specialist")

    df = get_merged(fact, players, schedule)

    # Only show Goalie and Midfielder options in the player dropdown
    spec_positions = ["Midfield", "Goalie"]
    spec_players   = players[players["Position"].isin(spec_positions)]["PlayerName"].tolist()
    opponents      = ["All"] + sorted(schedule["OpponentName"].unique().tolist())

    # --- FILTERS ---
    st.subheader("Filters")
    fcol1, fcol2 = st.columns(2)
    sel_player = fcol1.selectbox("Player (Goalie/Mid only)",
                                  ["All"] + sorted(spec_players), key="sp_player")
    sel_opp    = fcol2.selectbox("Opponent", opponents, key="sp_opp")

    # Date hierarchy: Year -> Month -> Day, each narrowing the next.
    # date_hierarchy_filter returns an already-filtered schedule DataFrame.
    st.caption("Date Filter")

    # Apply filters — always restrict to specialist positions
    sched_f = schedule.copy()

    #Apply the date filter
    sched_f = date_hierarchy_filter(schedule, key_prefix="ts")

    if sel_opp != "All":
        sched_f = sched_f[sched_f["OpponentName"] == sel_opp]

    df_f = df[
        df["Date"].isin(sched_f["Date"]) &
        df["Position"].isin(spec_positions)
    ]
    if sel_player != "All":
        df_f = df_f[df_f["PlayerName"] == sel_player]

    games_played = len(sched_f)

    # --- KPI CALCULATIONS ---
    saves_tot   = int(df_f["Saves"].sum())
    shots_faced = int(df_f["ShotsFaced"].sum())
    save_pct    = f"{round(saves_tot / shots_faced * 100, 1)}%" if shots_faced else "N/A"

    opp_goals   = sched_f["OppGoals"].sum()
    opp_gpg     = round(opp_goals / games_played, 1) if games_played else 0

    draw_atts   = int(df_f["DrawAtts"].sum())
    draw_ctrl   = int(df_f["DrawControls"].sum())
    draw_pct    = f"{round(draw_ctrl / draw_atts * 100, 1)}%" if draw_atts else "N/A"

    pen_time    = int(df_f["MinsServed"].sum())

    # --- TOP KPI ROW: 3 summary metrics (Penalty Mins removed) ---
    st.divider()
    k1, k2, k3 = st.columns(3)
    with k1: show_kpi("Save %",         save_pct)
    with k2: show_kpi("Opp Goals PG",   opp_gpg)
    with k3: show_kpi("Draw Control %", draw_pct)

    st.divider()

    # ==========================================================================
    # GOALIE SECTION
    # Layout: [KPIs (Shots Faced + Saves)] | [Save % Line Chart] | [Save % Donut]
    # ==========================================================================
    st.subheader("Goalie")

    g_kpi_col, g_line_col, g_donut_col = st.columns([1, 2, 1])

    with g_kpi_col:
        with st.container(height = 500):
            show_kpi("Shots Faced", shots_faced)
            show_kpi("Total Saves", saves_tot)

    with g_line_col:
        # SAVE % BY GAME — Area line chart, goalie rows only
        st.subheader("Save % by Game")
        goalie_df = df_f[df_f["Position"] == "Goalie"]

        if not goalie_df.empty:
            # Sum saves and shots faced per game date
            sg = goalie_df.groupby("Date")[["Saves", "ShotsFaced"]].sum().reset_index()
            sg = sg.merge(sched_f[["Date", "OpponentName"]], on="Date", how="left")
            sg["SavePct"] = sg.apply(
                lambda r: round(r["Saves"] / r["ShotsFaced"] * 100, 1)
                          if r["ShotsFaced"] else 0, axis=1
            )
            sg["Label"] = (
                sg["OpponentName"] + "<br>" +
                sg["Date"].dt.strftime("%m-%d-%Y")
            )
            # Color each data point: red if below 50%, green if at or above 50%
            sg["MarkerColor"] = sg["SavePct"].apply(
                lambda v: "#e74c3c" if v < 50 else "#2ecc71"
            )
            fig_sv = go.Figure()
            # Dashed reference line at 50% to show the "break-even" point
            fig_sv.add_hline(y=50, line_dash="dot", line_color=MUTED, opacity=0.5)
            fig_sv.add_trace(go.Scatter(
                x=sg["Label"], y=sg["SavePct"],
                mode="lines+markers", fill="tozeroy",
                line=dict(color=PURPLE_L, width=2.5),
                fillcolor="rgba(139, 47, 201, 0.20)",
                marker=dict(size=9, color=sg["MarkerColor"])
            ))
            apply_layout(fig_sv, height=500,
                yaxis=dict(title="Save %", range=[0, 105],
                           ticksuffix="%", gridcolor="#2a2a4a",
                           tickfont=dict(color=MUTED)))
            st.plotly_chart(fig_sv, use_container_width=True, config={"displayModeBar": False})
        else:
            st.info("No goalie data for this selection.")

    with g_donut_col:
        # SAVES DONUT — Saves vs Goals Allowed
        st.subheader("Save %")
        goals_allowed = max(shots_faced - saves_tot, 0)
        fig_sv_d = go.Figure(go.Pie(
            labels=["Saves", "Goals<br>Allowed"],
            values=[saves_tot, goals_allowed],
            hole=0.55,
            marker=dict(colors=[PURPLE, DARK]),
            textinfo="label+percent",
            textfont=dict(color=TEXT),
        ))
        apply_layout(fig_sv_d, height=500, showlegend=False,
                     margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig_sv_d, use_container_width=True, config={"displayModeBar": False})

    st.divider()

    # ==========================================================================
    # DRAW CONTROL SECTION
    # Layout: [KPIs (Draw Atts + Draw Controls)] | [Draw % Line Chart] | [Draw % Donut]
    # ==========================================================================
    st.subheader("Draw Control")

    d_kpi_col, d_line_col, d_donut_col = st.columns([1, 2, 1])

    with d_kpi_col:
        show_kpi("Draw Atts",     draw_atts)
        show_kpi("Draw Controls", draw_ctrl)

    with d_line_col:
        # DRAW CONTROL % BY GAME — Area line chart, midfielder rows only
        st.subheader("Draw Control % by Game")
        mid_df = df_f[df_f["Position"] == "Midfield"]

        if not mid_df.empty:
            dg = mid_df.groupby("Date")[["DrawAtts", "DrawControls"]].sum().reset_index()
            dg = dg.merge(sched_f[["Date", "OpponentName"]], on="Date", how="left")
            dg["DrawPct"] = dg.apply(
                lambda r: round(r["DrawControls"] / r["DrawAtts"] * 100, 1)
                          if r["DrawAtts"] else 0, axis=1
            )
            dg["Label"] = (
                dg["OpponentName"] + "<br>" +
                dg["Date"].dt.strftime("%m-%d-%Y")
            )
            # Same red/green coloring logic as the save % chart
            dg["MarkerColor"] = dg["DrawPct"].apply(
                lambda v: "#e74c3c" if v < 50 else "#2ecc71"
            )
            fig_dc = go.Figure()
            fig_dc.add_hline(y=50, line_dash="dot", line_color=MUTED, opacity=0.5)
            fig_dc.add_trace(go.Scatter(
                x=dg["Label"], y=dg["DrawPct"],
                mode="lines+markers", fill="tozeroy",
                line=dict(color=PURPLE, width=2.5),
                fillcolor="rgba(139, 47, 201, 0.20)",
                marker=dict(size=9, color=dg["MarkerColor"])
            ))
            apply_layout(fig_dc, height=500,
                yaxis=dict(title="Draw %", range=[0, 105],
                           ticksuffix="%", gridcolor="#2a2a4a",
                           tickfont=dict(color=MUTED)))
            st.plotly_chart(fig_dc, use_container_width=True, config={"displayModeBar": False})
        else:
            st.info("No draw data for this selection.")

    with d_donut_col:
        # DRAW CONTROLS DONUT — Won vs Lost
        st.subheader("Draw Controls")
        draws_lost = max(draw_atts - draw_ctrl, 0)
        fig_dc_d = go.Figure(go.Pie(
            labels=["Controls<br>Won", "Controls<br>Lost"],
            values=[draw_ctrl, draws_lost],
            hole=0.55,
            marker=dict(colors=[PURPLE_L, DARK]),
            textinfo="label+percent",
            textfont=dict(color=TEXT),
        ))
        apply_layout(fig_dc_d, height=500, showlegend=False,
                     margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig_dc_d, use_container_width=True, config={"displayModeBar": False})


# =============================================================================
# PAGE 4 — BOX STATS
# A full aggregated stat table — one row per player for the filtered games.
# Includes a totals row at the bottom, similar to a traditional box score.
# =============================================================================
def page_box_stats(fact, schedule, players):
    st.title("Box Stats")

    df = get_merged(fact, players, schedule)

    # --- FILTERS ---
    st.subheader("Filters")

    # Top row: opponent, position, and name search
    fcol1, fcol2, fcol3 = st.columns(3)
    opponents = ["All"] + sorted(schedule["OpponentName"].unique().tolist())
    positions = ["All"] + sorted(players["Position"].unique().tolist())

    sel_opp  = fcol1.selectbox("Opponent", opponents, key="bs_opp")
    sel_pos  = fcol2.selectbox("Position", positions, key="bs_pos")
    sel_name = fcol3.text_input("Player Name Search", key="bs_name")

    # Date hierarchy: Year -> Month -> Day, each narrowing the next.
    # date_hierarchy_filter returns an already-filtered schedule DataFrame.
    st.caption("Date Filter")
    sched_f = date_hierarchy_filter(schedule, key_prefix="bs")

    # Apply opponent filter on top of the date hierarchy result
    if sel_opp != "All":
        sched_f = sched_f[sched_f["OpponentName"] == sel_opp]

    df_f = df[df["Date"].isin(sched_f["Date"])]
    if sel_pos  != "All":
        df_f = df_f[df_f["Position"] == sel_pos]
    if sel_name:
        # str.contains() does a partial, case-insensitive match
        df_f = df_f[df_f["PlayerName"].str.contains(sel_name, case=False, na=False)]

    st.divider()

    # --- AGGREGATION ---
    # Group by player and sum all numeric stats across all filtered games.
    # "nunique" on Date gives us games played (counts distinct game dates).
    agg = df_f.groupby(["PlayerName", "Position"]).agg(
        GP             = ("Date",           "nunique"),
        Goals          = ("Goals",          "sum"),
        Assists        = ("Assists",         "sum"),
        GBs            = ("GBs",            "sum"),
        TOs            = ("TOs",            "sum"),
        CTOs           = ("CTOs",           "sum"),
        DrawAtts       = ("DrawAtts",       "sum"),
        DrawControls   = ("DrawControls",   "sum"),
        Shots          = ("Shots",          "sum"),
        WomanUpGoals   = ("WomanUpGoals",   "sum"),
        WomanDownGoals = ("WomanDownGoals", "sum"),
        ShotsFaced     = ("ShotsFaced",     "sum"),
        Saves          = ("Saves",          "sum"),
    ).reset_index()

    # Calculated columns — derived from the aggregated totals above
    agg["Points"] = agg["Goals"] + agg["Assists"]
    agg["PPG"]    = (agg["Points"] / agg["GP"]).round(1)

    # Format percentages as strings with "%" so they display cleanly in the table
    agg["Shot%"] = agg.apply(
        lambda r: f"{round(r['Goals'] / r['Shots'] * 100, 1)}%" if r["Shots"] else "—", axis=1
    )
    agg["Save%"] = agg.apply(
        lambda r: f"{round(r['Saves'] / r['ShotsFaced'] * 100, 1)}%" if r["ShotsFaced"] else "—", axis=1
    )
    agg["Draw%"] = agg.apply(
        lambda r: f"{round(r['DrawControls'] / r['DrawAtts'] * 100, 1)}%" if r["DrawAtts"] else "—", axis=1
    )

    # Define column order for display
    display_cols = [
        "PlayerName", "Position", "GP", "Goals", "Assists", "Points", "PPG",
        "GBs", "TOs", "CTOs", "Shots", "Shot%",
        "WomanUpGoals", "WomanDownGoals",
        "DrawAtts", "DrawControls", "Draw%",
        "ShotsFaced", "Saves", "Save%"
    ]

    # Rename to shorter display-friendly column headers
    rename_map = {
        "PlayerName":     "Player",
        "WomanUpGoals":   "W-Up G",
        "WomanDownGoals": "W-Dn G",
        "DrawAtts":       "Draw Atts",
        "DrawControls":   "Draw Ctrl",
        "ShotsFaced":     "Shots Faced",
    }
    table = agg[display_cols].rename(columns=rename_map).sort_values("Points", ascending=False)

    # --- TOTALS ROW ---
    # Build a single-row dict with summed values for all numeric columns
    numeric_cols = ["GP", "Goals", "Assists", "Points", "GBs", "TOs", "CTOs",
                    "Shots", "W-Up G", "W-Dn G", "Draw Atts", "Draw Ctrl",
                    "Shots Faced", "Saves"]

    totals = {col: "" for col in table.columns}   # Start with empty strings
    for col in numeric_cols:
        if col in table.columns:
            totals[col] = table[col].sum()         # Fill in numeric sums

    totals["Player"]   = "TOTAL"
    totals["Position"] = ""
    totals["PPG"]      = round(totals["Points"] / totals["GP"], 1) if totals["GP"] else 0

    # Convert the totals dict to a single-row DataFrame and append to the table
    totals_df = pd.DataFrame([totals])
    final_df  = pd.concat([table, totals_df], ignore_index=True)
    final_df = final_df.dropna(axis = 0)

    # Display as an interactive Streamlit dataframe (sortable columns, scrollable)
    st.dataframe(
        final_df,
        use_container_width=True,
        height=520,
        hide_index=True,
    )


# =============================================================================
# MAIN — Entry point
# Decides whether to show the upload screen or the main report,
# then routes to the correct page based on session_state.
# =============================================================================
def main():
    # If no data has been loaded yet, show the file upload screen and stop here
    if not st.session_state.data_loaded:
        upload_screen()
        return

    # Retrieve the DataFrames stored in session_state after upload
    fact     = st.session_state.fact
    schedule = st.session_state.schedule
    players  = st.session_state.players

    # Render the navigation bar at the top of every page
    nav_bar()
    st.divider()

    # Route to the correct page function based on what the user selected
    page = st.session_state.page
    if page == "Team Stats":
        page_team_stats(fact, schedule, players)
    elif page == "Player Stats":
        page_player_stats(fact, schedule, players)
    elif page == "Specialist":
        page_specialist(fact, schedule, players)
    elif page == "Box Stats":
        page_box_stats(fact, schedule, players)


# Standard Python entry point — runs main() only when this file is executed directly
if __name__ == "__main__":
    main()