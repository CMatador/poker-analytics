-- =============================================================================
-- poker-analytics | schema.sql
-- Database: DuckDB
-- Description: Raw layer schema for poker hand tracking application.
--              All analytical derivations (hand_class, board_type,
--              hero_result_bb, effective_stack, pot_type_derived)
--              are handled downstream in dbt models.
-- =============================================================================


-- =============================================================================
-- SESSIONS
-- One row per playing session. Stakes structure supports optional straddle.
-- default_stack is used to pre-populate hand_players stack inputs in the UI.
-- =============================================================================

CREATE TABLE IF NOT EXISTS sessions(
    session_id      VARCHAR PRIMARY KEY DEFAULT gen_random_uuid(),
    game_type       VARCHAR NOT NULL,
    small_blind     DECIMAL(10, 2) NOT NULL,
    big_blind       DECIMAL(10, 2) NOT NULL,
    straddle        DECIMAL(10, 2),
    date            DATE NOT NULL,
    location        VARCHAR,
    default_stack   DECIMAL(10, 2),
    notes           TEXT,
    created_at      TIMESTAMP DEFAULT current_timestamp
);


-- =============================================================================
-- HANDS
-- One row per hand played. Board cards stored as individual card columns.
-- hero_card_1/2 stored in rank+suit notation (e.g. 'As', 'Td', 'Kh').
-- pot_type is user-selected; pot_type_derived is computed in dbt as a check.
-- hand_number is auto-assigned in dbt via ROW_NUMBER() over session.
-- =============================================================================

CREATE TABLE IF NOT EXISTS hands(
    hand_id             VARCHAR PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id          VARCHAR NOT NULL REFERENCES sessions(session_id),
    hand_number         INTEGER,
    hero_card_1         VARCHAR(2) NOT NULL,
    hero_card_2         VARCHAR(2) NOT NULL,
    hero_position       VARCHAR(5) NOT NULL,
    hero_stack          DECIMAL(10, 2) NOT NULL,
    pot_type            VARCHAR NOT NULL,
    num_players         INTEGER NOT NULL,
    flop_card_1         VARCHAR(2),
    flop_card_2         VARCHAR(2),
    flop_card_3         VARCHAR(2),
    turn_card           VARCHAR(2),
    river_card          VARCHAR(2),
    final_street        VARCHAR(8),
    end_pot             DECIMAL(10, 2),
    hero_result         DECIMAL(10, 2),
    went_to_showdown    BOOLEAN DEFAULT FALSE,
    villain_cards       VARCHAR
    tag                 VARCHAR,
    notes               VARCHAR,
    created_at          TIMESTAMP DEFAULT current_timestamp,

    -- Data entry validations
    CONSTRAINT chk_hero_card_1 CHECK(LENGTH(hero_card_1) = 2),
    CONSTRAINT chk_hero_card_2 CHECK(LENGTH(hero_card_2) = 2)

    CONSTRAINT chk_final_street CHECK(
        final_street IN ('preflop', 'flop', 'turn', 'river')
    ),

    CONSTRAINT chk_pot_type CHECK(
        pot_type IN ('limp', 'SRP', '3bet', '4bet+')
    ),

    CONSTRAINT chk_num_players CHECK(
        num_players BETWEEN 2 AND 9
    )

    -- Board validation: turn requires flop, river requires turn
    CONSTRAINT chk_turn_requires_flop CHECK(
        turn_card IS NULL OR (flop_card_1 IS NOT NULL AND flop_card_2 IS NOT NULL AND flop_card_3 IS NOT NULL)
    ),
    CONSTRAINT chk_river_requires_turn CHECK(
        river_card IS NULL OR turn_card IS NOT NULL
    )
);

-- =============================================================================
-- HAND_PLAYERS
-- One row per seat per hand. Captures all players present, not just those
-- who entered the pot. is_involved = FALSE means the player folded preflop
-- without voluntarily putting money in.
-- effective_stack = MIN(stack_start) WHERE is_involved = TRUE, derived in dbt.
-- =============================================================================

CREATE TABLE IF NOT EXISTS hand_players (
    hand_player_id  VARCHAR PRIMARY KEY DEFAULT gen_random_uuid(),
    hand_id         VARCHAR NOT NULL REFERENCES hands(hand_id),
    position        VARCHAR(5) NOT NULL,
    stack_start     DECIMAL(10, 2) NOT NULL,
    is_hero         BOOLEAN DEFAULT FALSE,
    is_involved     BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMP DEFAULT current_timestamp,

    -- No duplicate positions in same hand
    CONSTRAINT uq_hand_position UNIQUE (hand_id, position),

    -- One hero per hand
    CONSTRAINT chk_position CHECK(
        position IN ('UTG', 'UTG+1', 'MP', 'LJ', 'HJ', 'CO', 'BTN', 'SB', 'BB')
    )
);


-- =============================================================================
-- HAND_ACTIONS
-- One row per player action per street. action_order is a global sequence
-- across the entire hand (not reset per street) to support full reconstruction.
-- Preflop actions not recorded are assumed folded.
-- pot_before captures the pot size at the moment of action for odds calculation.
-- =============================================================================

CREATE TABLE IF NOT EXISTS hand_actions (
    action_id       VARCHAR PRIMARY KEY DEFAULT gen_random_uuid(),
    hand_id         VARCHAR NOT NULL REFERENCES hands(hand_id),
    street          VARCHAR(8) NOT NULL,
    action_order    INTEGER NOT NULL,
    action_type     VARCHAR NOT NULL,
    player          VARCHAR(5) NOT NULL,
    amount          DECIMAL(10, 2),
    is_allin        BOOLEAN DEFAULT FALSE,
    pot_before      DECIMAL(10, 2) NOT NULL,
    created_at      TIMESTAMP DEFAULT current_timestamp,

    -- Validate data entry
    CONSTRAINT chk_action_street CHECK(
        street IN ('preflop', 'flop', 'turn', 'river')
    ),

    CONSTRAINT chk_action_type CHECK(
        action_type IN ('fold', 'check', 'call', 'bet', 'raise')
    ),

    CONSTRAINT uq_hand_action_order UNIQUE (hand_id, action_order),

    CONSTRAINT chk_amount_on_action CHECK(
        (action_type IN ('bet', 'raise', 'call') AND amount IS NOT NULL)
        OR
        (action_type IN ('fold', 'check') AND amount IS NULL)
    )
);


-- =============================================================================
-- INDEXES
-- Support common query patterns: filter by session, reconstruct hand order,
-- and retrieve all actions for a given hand in sequence.
-- =============================================================================

CREATE INDEX IF NOT EXISTS idx_hands_session_id
    ON hands(session_id);

CREATE INDEX IF NOT EXISTS idx_hand_players_hand_id
    ON hand_players(hand_id);

CREATE INDEX IF NOT EXISTS idx_hand_actions_hand_id_order
    ON hand_actions (hand_id, action_order);