"""What the fields of a roster save mean, beyond their names (see schema_names.py for those).

Everything here follows the game's own schema (db/nhlng-meta.xml); nothing is guessed.
"""
from .schema_names import FIELDS

# stored attribute value = rating - RATING_BASE (6 bits: ratings 36..99)
RATING_BASE = 36

# EA attribute label (as published for NHL 27) -> exhibitionskaterai field
EA_SKATER = {
    'Deking': 'iCvN', 'Hand-Eye': 'ujcW', 'Passing': 'oRUd', 'Puck Control': 'YqXz',
    'Slap Shot Accuracy': 'KQBB', 'Slap Shot Power': 'DCvJ', 'Wrist Shot Accuracy': 'ObeE', 'Wrist Shot Power': 'Hvje',
    'Acceleration': 'ckxF', 'Agility': 'pyYq', 'Balance': 'YqOX', 'Endurance': 'kIjD', 'Speed': 'bEdA',
    'Discipline': 'ShqX', 'Offensive Awareness': 'VlLd', 'Poise': 'fRaZ',
    'Defensive Awareness': 'OTvp', 'Faceoffs': 'KrwV', 'Shot Blocking': 'zRrS', 'Stick Checking': 'TUty',
    'Aggression': 'oskO', 'Aggressiveness': 'oskO', 'Body Checking': 'oisw', 'Durability': 'seUB',
    'Fighting Skill': 'gUBy', 'Strength': 'POYr',
}
# EA attribute label -> exhibitiongoalieai field
EA_GOALIE = {
    'Glove Side High': 'DTrq', 'Glove Side Low': 'ejux', 'Stick Side High': 'vcIl', 'Stick Side Low': 'mshm',
    'Five Hole': 'nMNR', 'Poke Check': 'UqhP', 'Rebound Control': 'SiKH', 'Shot Recover': 'oLxj',
    'Vision': 'miXH', 'Breakaway': 'Nhuq', 'Angles': 'fdgB', 'Puck Playing Frequency': 'LMNx',
    'Aggression': 'oskO', 'Aggressiveness': 'oskO', 'Agility': 'pyYq', 'Speed': 'bEdA', 'Endurance': 'kIjD',
    'Durability': 'seUB', 'Passing': 'oRUd', 'Poise': 'fRaZ',
}

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
