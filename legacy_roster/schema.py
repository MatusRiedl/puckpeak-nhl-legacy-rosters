"""What the fields of a roster save mean, beyond their names (see schema_names.py for those).

Everything here follows the game's own schema (db/nhlng-meta.xml); nothing is guessed.
"""
from .schema_names import FIELDS

# stored attribute value = rating - RATING_BASE (6 bits: ratings 36..99)
RATING_BASE = 36

# the ratings list's attribute label -> exhibitionskaterai field
LIST_SKATER = {
    'Deking': 'iCvN', 'Hand-Eye': 'ujcW', 'Passing': 'oRUd', 'Puck Control': 'YqXz',
    'Slap Shot Accuracy': 'KQBB', 'Slap Shot Power': 'DCvJ', 'Wrist Shot Accuracy': 'ObeE', 'Wrist Shot Power': 'Hvje',
    'Acceleration': 'ckxF', 'Agility': 'pyYq', 'Balance': 'YqOX', 'Endurance': 'kIjD', 'Speed': 'bEdA',
    'Discipline': 'ShqX', 'Offensive Awareness': 'VlLd', 'Poise': 'fRaZ',
    'Defensive Awareness': 'OTvp', 'Faceoffs': 'KrwV', 'Shot Blocking': 'zRrS', 'Stick Checking': 'TUty',
    'Aggression': 'oskO', 'Aggressiveness': 'oskO', 'Body Checking': 'oisw', 'Durability': 'seUB',
    'Fighting Skill': 'gUBy', 'Strength': 'POYr',
}
# the ratings list's attribute label -> exhibitiongoalieai field
LIST_GOALIE = {
    'Glove Side High': 'DTrq', 'Glove Side Low': 'ejux', 'Stick Side High': 'vcIl', 'Stick Side Low': 'mshm',
    'Five Hole': 'nMNR', 'Poke Check': 'UqhP', 'Rebound Control': 'SiKH', 'Shot Recover': 'oLxj',
    'Vision': 'miXH', 'Breakaway': 'Nhuq', 'Angles': 'fdgB', 'Puck Playing Frequency': 'LMNx',
    'Aggression': 'oskO', 'Aggressiveness': 'oskO', 'Agility': 'pyYq', 'Speed': 'bEdA', 'Endurance': 'kIjD',
    'Durability': 'seUB', 'Passing': 'oRUd', 'Poise': 'fRaZ',
}

# The full ratings' database (data pack part `ratings_full`, docs/notes/full-ratings.md) has these fields under the
# names NHL Legacy's skater / goalie tables use. RATED: 0-99 ratings, stored as value - RATING_BASE (clamped 0-63; the
# overall is c_overall, `FUWe`). AS IS: small numbers with the same meaning in both games, copied unchanged (the player
# type `playerstyle` only within the record's class: ratings.STYLE_CHOICES). Not copied: c_potential, growth*, trait*.
FULL_RATED = {
    'skater': ('c_acceleration', 'c_aggression', 'c_agility', 'c_balance', 'c_bodychecking', 'c_defawareness',
               'c_deking', 'c_discipline', 'c_durability', 'c_endurance', 'c_faceoffs', 'c_fightingskill', 'c_handeye',
               'c_offawareness', 'c_overall', 'c_passing', 'c_poise', 'c_puckcontrol', 'c_shotblocking',
               'c_slapaccuracy', 'c_slapshotpower', 'c_speed', 'c_stickchecking', 'c_strength', 'c_wristaccuracy',
               'c_wristshotpower'),
    'goalie': ('c_5hole', 'c_aggression', 'c_agility', 'c_breakaway', 'c_durability', 'c_endurance', 'c_gsh', 'c_gsl',
               'c_overall', 'c_passing', 'c_poise', 'c_pokecheck', 'c_positioning', 'c_puckplayfrequency',
               'c_reboundcontrol', 'c_shotrecover', 'c_speed', 'c_ssh', 'c_ssl', 'c_vision'),
}
FULL_ASIS = {
    'skater': ('c_fighting', 'shoot_passbias', 'off_defbias', 'pass_carrybias', 'playerstyle'),
    'goalie': ('c_consistency', 'c_fighting', 'c_paddledown', 'playerstyle'),
}
# the values the game's own players hold in the fields the full ratings writes (verify.rating_problems); the player type
# has its own check (verify.style_problems)
RATING_RANGE = (0, 63)
ASIS_RANGE = {'c_fighting': (0, 3), 'c_consistency': (0, 2), 'c_paddledown': (0, 1),
              'shoot_passbias': (0, 15), 'off_defbias': (0, 15), 'pass_carrybias': (0, 15)}
FULL_TABLE = {'skater': 'yvSd', 'goalie': 'yuHm'}
FULL_TAG = {kind: {real: tag for tag, real in FIELDS[table].items()} for kind, table in FULL_TABLE.items()}

# exhibitionrostertable: the 71 one-bit line slots, by real name -> tag
_ROSTER = {real: tag for tag, real in FIELDS['ulGe'].items()}
EVEN_STRENGTH = [f"l{n}{p}" for n in (1, 2, 3) for p in ('lw', 'c', 'rw', 'ld', 'rd')] + ['l4lw', 'l4c', 'l4rw']
POWER_PLAY = [f"pp{n}{p}" for n in (1, 2) for p in ('lw', 'c', 'rw', 'ld', 'rd')]
POWER_PLAY_4 = [f"pp4_{n}{p}" for n in (1, 2) for p in ('lw', 'c', 'ld', 'rd')]
PENALTY_KILL_4 = [f"pk4_{n}{p}" for n in (1, 2) for p in ('lw', 'c', 'ld', 'rd')]
PENALTY_KILL_3 = [f"pk3_{n}{p}" for n in (1, 2) for p in ('c', 'ld', 'rd')]
OVERTIME = [f"ot_{n}{p}" for n in (1, 2, 3) for p in ('lw', 'c', 'ld', 'rd')]
SHOOTOUT = [f"s{n}" for n in (1, 2, 3, 4, 5)]
EXTRA_ATTACKER = ['x1', 'x2']
GOALIE_SLOTS = ['g1', 'g2']
LINE_SLOTS = (EVEN_STRENGTH + POWER_PLAY + POWER_PLAY_4 + PENALTY_KILL_4 + PENALTY_KILL_3 + OVERTIME
              + SHOOTOUT + EXTRA_ATTACKER + GOALIE_SLOTS)
SLOT_TAG = {name: _ROSTER[name] for name in LINE_SLOTS}   # 'l1c' -> 'ctKP'
assert len(SLOT_TAG) == 71
