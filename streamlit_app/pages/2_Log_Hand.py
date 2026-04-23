"""
2_Log_Hand.py — Log a poker hand
----------------------------------
This page uses a step-based flow to guide hand entry street by street.
The key concept is st.session_state — a dictionary that persists across
Streamlit's reruns. Without it, every widget interaction would reset the
entire page and lose any in-progress hand data.

Flow:
    Step 0 → Hand setup   (players, hero cards, stacks, pot type)
    Step 1 → Preflop      (add actions one at a time)
    Step 2 → Flop         (enter board cards, add actions)
    Step 3 → Turn         (enter turn card, add actions)
    Step 4 → River        (enter river card, add actions)
    Step 5 → Result       (end pot, hero result, notes → save to DB)
"""

import streamlit as st
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from utils.db import execute, fetch_all

st.set_page_config(page_title="Log Hand", page_icon="🃏", layout="centered")

# ── Constants ─────────────────────────────────────────────────────────────────

# Valid positions keyed by number of players at the table.
# SB and BB are always present; other positions are added working
# backwards from BTN as the table fills up.
POSITIONS_BY_COUNT = {
    9: ["UTG", "UTG+1", "MP", "LJ", "HJ", "CO", "BTN", "SB", "BB"],
    8: ["UTG", "UTG+1", "LJ", "HJ", "CO", "BTN", "SB", "BB"],
    7: ["UTG", "LJ", "HJ", "CO", "BTN", "SB", "BB"],
    6: ["UTG", "HJ", "CO", "BTN", "SB", "BB"],
    5: ["UTG", "CO", "BTN", "SB", "BB"],
    4: ["UTG", "BTN", "SB", "BB"],
    3: ["BTN", "SB", "BB"],
    2: ["SB", "BB"],
}

VALID_RANKS = list("23456789TJQKA")
VALID_SUITS = ["s", "h", "d", "c"]
SUIT_SYMBOLS = {"s": "♠", "h": "♥", "d": "♦", "c": "♣"}

ACTION_TYPES = ["fold", "check", "call", "bet", "raise"]
POT_TYPES    = ["limp", "SRP", "3bet", "4bet+"]
TAGS         = ["", "interesting", "mistake", "good-fold", "good-call", "bad-call", "bad-fold"]
STREETS      = ["preflop", "flop", "turn", "river"]


# ── Helpers ───────────────────────────────────────────────────────────────────

def validate_card(card: str) -> bool:
    """Check card is in standard 2-char notation e.g. 'As', 'Td', '2h'."""
    if not card or len(card) != 2:
        return False
    return card[0].upper() in VALID_RANKS and card[1].lower() in VALID_SUITS


def format_card(card: str) -> str:
    """Return a readable card string e.g. 'As' → 'A♠'."""
    if not card or len(card) != 2:
        return card
    return card[0].upper() + SUIT_SYMBOLS.get(card[1].lower(), card[1])


def normalise_card(card: str) -> str:
    """Uppercase rank, lowercase suit. 'as' → 'As'."""
    return card[0].upper() + card[1].lower()


def init_state():
    """
    Initialise all session_state keys used by this page.
    Called at the top of every rerun — only sets a key if it doesn't
    already exist, so existing state is never overwritten.
    """
    defaults = {
        "hand_step":      0,       # which step of the flow we're on
        "hand_setup":     {},      # data from step 0
        "hand_players":   [],      # list of {position, stack, is_hero, is_involved}
        "actions":        [],      # accumulated list of action dicts
        "action_order":   1,       # global counter across all streets
        "board":          {},      # card values keyed by 'flop_1','flop_2','flop_3','turn','river'
        "current_street": "preflop",
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


def reset_hand():
    """Clear all in-progress hand state and return to step 0."""
    keys = ["hand_step", "hand_setup", "hand_players", "actions",
            "action_order", "board", "current_street"]
    for k in keys:
        if k in st.session_state:
            del st.session_state[k]
    init_state()


def get_involved_positions() -> list:
    """Return position labels for players who entered the pot (is_involved=True)."""
    return [p["position"] for p in st.session_state.hand_players if p["is_involved"]]


def add_action(street, actor, action_type, amount, is_allin, pot_before):
    """Append one action to the accumulated actions list."""
    st.session_state.actions.append({
        "street":       street,
        "action_order": st.session_state.action_order,
        "action_type":  action_type,
        "player":       actor,
        "amount":       amount,
        "is_allin":     is_allin,
        "pot_before":   pot_before,
    })
    st.session_state.action_order += 1


def render_action_log(street_filter: str = None):
    """Display the accumulated action list as a compact table."""
    actions = st.session_state.actions
    if street_filter:
        actions = [a for a in actions if a["street"] == street_filter]
    if not actions:
        st.caption("No actions recorded yet.")
        return
    for a in actions:
        amount_str = f"  ${a['amount']:.2f}" if a["amount"] else ""
        allin_str  = " 🔴 ALL-IN" if a["is_allin"] else ""
        st.caption(
            f"`{a['player']:5s}` {a['action_type']}{amount_str}{allin_str}"
        )


def save_hand_to_db(result: dict):
    """
    Write the completed hand to DuckDB in three steps:
        1. Insert into hands
        2. Insert into hand_players (one row per seat)
        3. Insert into hand_actions (one row per action)
    All three use the same hand_id to link everything together.
    """
    setup   = st.session_state.hand_setup
    board   = st.session_state.board
    players = st.session_state.hand_players
    actions = st.session_state.actions

    # Derive final_street from board and actions
    if board.get("river"):
        final_street = "river"
    elif board.get("turn"):
        final_street = "turn"
    elif board.get("flop_1"):
        final_street = "flop"
    else:
        final_street = "preflop"

    # ── 1. Insert hand ────────────────────────────────────────────────────────
    execute(
        """
        INSERT INTO hands (
            session_id, hero_card_1, hero_card_2,
            hero_position, hero_stack, pot_type, num_players,
            flop_card_1, flop_card_2, flop_card_3,
            turn_card, river_card, final_street,
            end_pot, hero_result,
            went_to_showdown, villain_cards,
            tag, notes
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?,
            ?, ?, ?,
            ?, ?,
            ?, ?,
            ?, ?
        )
        """,
        [
            setup["session_id"],
            setup["hero_card_1"], setup["hero_card_2"],
            setup["hero_position"], setup["hero_stack"],
            setup["pot_type"], setup["num_players"],
            board.get("flop_1"),  board.get("flop_2"),  board.get("flop_3"),
            board.get("turn"),    board.get("river"),
            final_street,
            result["end_pot"],    result["hero_result"],
            result["went_to_showdown"],
            result.get("villain_cards") or None,
            result.get("tag") or None,
            result.get("notes") or None,
        ],
    )

    # Retrieve the hand_id that was just created
    hand_row = fetch_all(
        "SELECT hand_id FROM hands ORDER BY created_at DESC LIMIT 1"
    )
    hand_id = hand_row["hand_id"].iloc[0]

    # ── 2. Insert hand_players ────────────────────────────────────────────────
    for player in players:
        execute(
            """
            INSERT INTO hand_players
                (hand_id, position, stack_start, is_hero, is_involved)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                hand_id,
                player["position"],
                player["stack"],
                player["is_hero"],
                player["is_involved"],
            ],
        )

    # ── 3. Insert hand_actions ────────────────────────────────────────────────
    for action in actions:
        execute(
            """
            INSERT INTO hand_actions
                (hand_id, street, action_order, action_type,
                 player, amount, is_allin, pot_before)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                hand_id,
                action["street"],    action["action_order"],
                action["action_type"], action["player"],
                action.get("amount"), action["is_allin"],
                action["pot_before"],
            ],
        )

    return hand_id


# ── Page init ─────────────────────────────────────────────────────────────────

init_state()

st.title("Log Hand")

# Progress indicator — shows which step the user is on.
# st.progress takes a value 0.0–1.0.
step_labels = ["Setup", "Preflop", "Flop", "Turn", "River", "Result"]
current     = st.session_state.hand_step
st.progress(current / (len(step_labels) - 1), text=f"Step {current + 1} of {len(step_labels)}: **{step_labels[current]}**")

# Reset button — always visible so the user can abandon a hand in progress
if st.button("↩ Reset hand", use_container_width=False):
    reset_hand()
    st.rerun()

st.divider()


# =============================================================================
# STEP 0 — HAND SETUP
# =============================================================================
if st.session_state.hand_step == 0:

    st.subheader("Hand Setup")
    st.caption("Set the players, positions, and stacks for this hand.")

    # ── Session picker ────────────────────────────────────────────────────────
    # If a session was just created on the New Session page, it will already
    # be in st.session_state["active_session"]. Otherwise show a selectbox.

    sessions_df = fetch_all(
        """
        SELECT session_id,
               date || '  ' ||
               CASE WHEN straddle IS NOT NULL
                    THEN '$' || CAST(small_blind AS VARCHAR) || '/$' || CAST(big_blind AS VARCHAR)
                         || '/$' || CAST(straddle AS VARCHAR)
                    ELSE '$' || CAST(small_blind AS VARCHAR) || '/$' || CAST(big_blind AS VARCHAR)
               END ||
               COALESCE('  @ ' || location, '') AS label,
               default_stack,
               small_blind,
               big_blind,
               straddle
        FROM sessions
        ORDER BY created_at DESC
        LIMIT 20
        """
    )

    if sessions_df.empty:
        st.warning("No sessions found. Please create a session first.")
        st.stop()

    session_labels = sessions_df["label"].tolist()
    active = st.session_state.get("active_session")

    # Default to the most recent session if one was just created
    default_idx = 0
    if active:
        match = sessions_df[sessions_df["session_id"] == active.get("session_id")]
        if not match.empty:
            default_idx = int(match.index[0])

    selected_label = st.selectbox("Session", session_labels, index=default_idx)
    selected_row   = sessions_df[sessions_df["label"] == selected_label].iloc[0]

    default_stack = float(selected_row["default_stack"])
    effective_bb  = float(selected_row["straddle"] or selected_row["big_blind"])

    st.divider()

    # ── Table size and hero cards ─────────────────────────────────────────────
    col1, col2, col3 = st.columns([1, 1, 1])

    with col1:
        num_players = st.number_input(
            "Players at table",
            min_value=2, max_value=9, value=9, step=1,
        )

    positions = POSITIONS_BY_COUNT.get(num_players, POSITIONS_BY_COUNT[9])

    with col2:
        hero_pos = st.selectbox("Hero position", positions)

    with col3:
        pot_type = st.selectbox("Pot type", POT_TYPES, index=1,
                                help="limp=no raise preflop, SRP=single raised, 3bet/4bet+=re-raised")

    col4, col5 = st.columns(2)
    with col4:
        hero_card_1 = st.text_input(
            "Hero card 1", placeholder="e.g. As",
            help="Rank (A K Q J T 2-9) + Suit (s h d c)"
        ).strip()
    with col5:
        hero_card_2 = st.text_input(
            "Hero card 2", placeholder="e.g. Kh"
        ).strip()

    hero_stack = st.number_input(
        "Hero stack ($)", min_value=1.0, value=default_stack, step=10.0, format="%.2f"
    )

    st.divider()

    # ── Villain stacks ────────────────────────────────────────────────────────
    # For every position that isn't the hero, show a stack input and an
    # "involved in hand" checkbox. Default stack comes from session default.

    st.subheader("Villain stacks")
    st.caption(
        "Check **Involved** for players who entered the pot. "
        "All others are assumed to have folded preflop."
    )

    villain_positions = [p for p in positions if p != hero_pos]
    villain_data = {}

    for vpos in villain_positions:
        vcol1, vcol2, vcol3 = st.columns([1, 2, 1])
        with vcol1:
            st.markdown(f"**{vpos}**")
        with vcol2:
            stack = st.number_input(
                f"Stack {vpos}", min_value=0.0,
                value=default_stack, step=10.0, format="%.2f",
                label_visibility="collapsed",
            )
        with vcol3:
            involved = st.checkbox("Involved", key=f"inv_{vpos}")
        villain_data[vpos] = {"stack": stack, "involved": involved}

    st.divider()

    if st.button("▶ Start Hand", use_container_width=True, type="primary"):
        # Validate hero cards
        errors = []
        if not validate_card(hero_card_1):
            errors.append(f"'{hero_card_1}' is not a valid card. Use format Rank+Suit e.g. As, Td, 2h.")
        if not validate_card(hero_card_2):
            errors.append(f"'{hero_card_2}' is not a valid card.")
        if hero_card_1 and hero_card_2 and normalise_card(hero_card_1) == normalise_card(hero_card_2):
            errors.append("Hero's two cards cannot be the same card.")

        if errors:
            for e in errors:
                st.error(e)
        else:
            # Store hand setup in session_state
            st.session_state.hand_setup = {
                "session_id":    selected_row["session_id"],
                "num_players":   num_players,
                "hero_position": hero_pos,
                "hero_card_1":   normalise_card(hero_card_1),
                "hero_card_2":   normalise_card(hero_card_2),
                "hero_stack":    hero_stack,
                "pot_type":      pot_type,
                "effective_bb":  effective_bb,
            }

            # Build hand_players list — hero first, then villains
            players_list = [{
                "position":   hero_pos,
                "stack":      hero_stack,
                "is_hero":    True,
                "is_involved": True,   # hero is always involved
            }]
            for vpos, vdata in villain_data.items():
                players_list.append({
                    "position":    vpos,
                    "stack":       vdata["stack"],
                    "is_hero":     False,
                    "is_involved": vdata["involved"],
                })
            st.session_state.hand_players  = players_list
            st.session_state.current_street = "preflop"
            st.session_state.hand_step      = 1
            st.rerun()


# =============================================================================
# STEPS 1–4 — STREET-BY-STREET ACTIONS
# =============================================================================
elif st.session_state.hand_step in [1, 2, 3, 4]:

    step    = st.session_state.hand_step
    street  = STREETS[step - 1]   # step 1=preflop, 2=flop, 3=turn, 4=river
    setup   = st.session_state.hand_setup
    board   = st.session_state.board

    st.subheader(f"{street.title()} Actions")

    # ── Board card inputs (flop / turn / river) ───────────────────────────────
    if street == "flop":
        st.caption("Enter the three flop cards.")
        bcol1, bcol2, bcol3 = st.columns(3)
        with bcol1:
            f1 = st.text_input("Flop card 1", value=board.get("flop_1", ""), placeholder="e.g. Ah").strip()
        with bcol2:
            f2 = st.text_input("Flop card 2", value=board.get("flop_2", ""), placeholder="e.g. 7d").strip()
        with bcol3:
            f3 = st.text_input("Flop card 3", value=board.get("flop_3", ""), placeholder="e.g. 2c").strip()
        if f1 and f2 and f3:
            st.session_state.board["flop_1"] = normalise_card(f1)
            st.session_state.board["flop_2"] = normalise_card(f2)
            st.session_state.board["flop_3"] = normalise_card(f3)
        st.divider()

    elif street == "turn":
        st.caption("Enter the turn card.")
        flop_display = "  ".join([
            format_card(board.get("flop_1", "")),
            format_card(board.get("flop_2", "")),
            format_card(board.get("flop_3", "")),
        ])
        st.markdown(f"**Board:** {flop_display}")
        turn = st.text_input("Turn card", value=board.get("turn", ""), placeholder="e.g. Ks").strip()
        if turn:
            st.session_state.board["turn"] = normalise_card(turn)
        st.divider()

    elif street == "river":
        flop_display = "  ".join([
            format_card(board.get("flop_1", "")),
            format_card(board.get("flop_2", "")),
            format_card(board.get("flop_3", "")),
        ])
        turn_display  = format_card(board.get("turn", ""))
        st.markdown(f"**Board:** {flop_display}  {turn_display}")
        river = st.text_input("River card", value=board.get("river", ""), placeholder="e.g. 3h").strip()
        if river:
            st.session_state.board["river"] = normalise_card(river)
        st.divider()

    # ── Context summary ───────────────────────────────────────────────────────
    hero_cards = (
        f"{format_card(setup['hero_card_1'])} {format_card(setup['hero_card_2'])}"
    )
    involved   = get_involved_positions()
    eff_stack  = min(
        p["stack"] for p in st.session_state.hand_players if p["is_involved"]
    )

    icol1, icol2, icol3 = st.columns(3)
    icol1.metric("Hero", f"{setup['hero_position']}  {hero_cards}")
    icol2.metric("Involved", "  ".join(involved))
    icol3.metric("Eff. stack", f"${eff_stack:,.2f}")

    st.divider()

    # ── Action entry form ─────────────────────────────────────────────────────
    # st.form here means adding one action doesn't rerun and lose the
    # partially-typed next action — the page only reruns on "Add Action".

    st.markdown("**Add action**")

    with st.form(f"action_form_{street}", clear_on_submit=True):
        acol1, acol2 = st.columns(2)
        with acol1:
            actor = st.selectbox("Player", involved)
        with acol2:
            action_type = st.selectbox("Action", ACTION_TYPES)

        acol3, acol4 = st.columns(2)
        with acol3:
            amount = st.number_input(
                "Amount ($)", min_value=0.0, value=0.0, step=1.0, format="%.2f",
                help="Leave as 0 for fold or check"
            )
        with acol4:
            pot_before = st.number_input(
                "Pot before ($)", min_value=0.0, value=0.0, step=1.0, format="%.2f"
            )

        is_allin = st.checkbox("All-in")
        add_btn  = st.form_submit_button("➕ Add Action", use_container_width=True)

    if add_btn:
        amount_val = amount if action_type in ("bet", "raise", "call") else None
        add_action(street, actor, action_type, amount_val, is_allin, pot_before)
        st.rerun()

    # ── Action log for current street ─────────────────────────────────────────
    st.markdown(f"**{street.title()} actions so far:**")
    render_action_log(street_filter=street)

    st.divider()

    # ── Street navigation buttons ─────────────────────────────────────────────
    # Two columns: advance to next street, or end the hand here.

    nav1, nav2 = st.columns(2)

    next_street_labels = {
        1: "Deal Flop ▶",
        2: "Deal Turn ▶",
        3: "Deal River ▶",
        4: "Go to Result ▶",
    }

    with nav1:
        if st.button(next_street_labels[step], use_container_width=True, type="primary"):
            st.session_state.hand_step += 1
            st.rerun()

    with nav2:
        if st.button(f"End hand on {street.title()} ▶", use_container_width=True):
            # Skip remaining streets and go straight to result
            st.session_state.hand_step = 5
            st.rerun()


# =============================================================================
# STEP 5 — RESULT
# =============================================================================
elif st.session_state.hand_step == 5:

    setup  = st.session_state.hand_setup
    board  = st.session_state.board

    st.subheader("Result")

    # Show a read-only hand summary before asking for the result
    hero_cards = (
        f"{format_card(setup['hero_card_1'])} {format_card(setup['hero_card_2'])}"
    )
    board_cards = "  ".join(filter(None, [
        format_card(board.get("flop_1",  "")),
        format_card(board.get("flop_2",  "")),
        format_card(board.get("flop_3",  "")),
        format_card(board.get("turn",    "")),
        format_card(board.get("river",   "")),
    ]))

    rcol1, rcol2, rcol3 = st.columns(3)
    rcol1.metric("Hero hand",    f"{setup['hero_position']}  {hero_cards}")
    rcol2.metric("Pot type",     setup["pot_type"])
    rcol3.metric("Board",        board_cards or "Preflop only")

    st.caption(f"Total actions logged: {len(st.session_state.actions)}")
    st.divider()

    with st.form("result_form"):
        res1, res2 = st.columns(2)
        with res1:
            end_pot = st.number_input(
                "End pot ($)", min_value=0.0, value=0.0, step=1.0, format="%.2f"
            )
        with res2:
            hero_result = st.number_input(
                "Hero result ($)",
                value=0.0, step=1.0, format="%.2f",
                help="Positive = won, negative = lost. Net of what you put in."
            )

        went_to_sd = st.checkbox("Went to showdown")
        villain_cards = st.text_input(
            "Villain cards (optional)",
            placeholder="e.g. QdJc",
            help="Enter if villain showed cards at showdown"
        )

        res3, res4 = st.columns(2)
        with res3:
            tag = st.selectbox("Tag", TAGS)
        with res4:
            pass

        notes = st.text_area("Notes", placeholder="Anything worth remembering about this hand.", height=80)

        save_btn = st.form_submit_button("💾 Save Hand", use_container_width=True, type="primary")

    if save_btn:
        result_data = {
            "end_pot":           end_pot,
            "hero_result":       hero_result,
            "went_to_showdown":  went_to_sd,
            "villain_cards":     villain_cards.strip() or None,
            "tag":               tag or None,
            "notes":             notes.strip() or None,
        }

        try:
            hand_id = save_hand_to_db(result_data)
            eff_bb  = setup.get("effective_bb", 1)
            result_bb = hero_result / eff_bb if eff_bb else 0

            st.success(
                f"✅ Hand saved!  "
                f"Result: **${hero_result:+.2f}** ({result_bb:+.1f} BB)"
            )
            st.balloons()
            reset_hand()

        except Exception as e:
            st.error(f"Failed to save hand: {e}")