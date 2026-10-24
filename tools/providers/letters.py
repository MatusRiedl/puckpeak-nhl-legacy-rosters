"""Captains from the last games (owner, 2026-10-24: real captains for every team): a team's C and A worked out from the
letters its players wore in its last games (NHL.com's game roster reports, HockeyTech's game summaries, the Extraliga's
match line-ups)."""
from collections import Counter


def count_letters(games):
    """{player: 'C' | 'A'} of one team from `games`, oldest first, each {player: 'C' | 'A'} (who wore a letter in that
    game). The captain wore the C most often; the alternates are the others who wore a letter most often (an alternate
    wears the C while the captain is out): two with a captain, three without. Ties: the latest game with a letter, then
    the player. Empty when no game had letters."""
    worn, as_c, latest = Counter(), Counter(), {}
    for k, game in enumerate(games):
        for who, letter in game.items():
            worn[who] += 1
            latest[who] = k
            if letter == 'C':
                as_c[who] += 1
    def rank(counter):
        return sorted((w for w in counter if counter[w] > 0), key=lambda w: (-counter[w], -latest[w], str(w)))
    captain = rank(as_c)[:1]
    out = {w: 'C' for w in captain}
    for w in [w for w in rank(worn) if w not in out][:3 - len(out)]:
        out[w] = 'A'
    return out
