"""Match people from outside data (NHL.com, IIHF, EA ratings, league feeds) to player records."""
import difflib
import unicodedata


# letters that do not fall apart into a base letter and an accent (Øby-Olsen, Ærøe, Groß, Łukasz)
SPELLED_OUT = str.maketrans({'ø': 'o', 'Ø': 'O', 'æ': 'ae', 'Æ': 'AE', 'œ': 'oe', 'Œ': 'OE', 'ß': 'ss',
                             'đ': 'd', 'Đ': 'D', 'ð': 'd', 'Ð': 'D', 'þ': 'th', 'Þ': 'Th', 'ł': 'l', 'Ł': 'L',
                             'ı': 'i'})


def norm(s):
    s = unicodedata.normalize('NFKD', s.translate(SPELLED_OUT)).encode('ascii', 'ignore').decode().lower()
    return ''.join(ch for ch in s if ch.isalnum())


def build_index(R):
    P = R.P
    by_last_birth, by_name = {}, {}
    for i in range(P.cur_rec):
        b = (P.get(i, 'dnFq') + 1910, P.get(i, 'pLKJ') + 1, P.get(i, 'iwsK') + 1)
        by_last_birth.setdefault((norm(P.get(i, 'RMbQ')), b), []).append(i)
        by_name.setdefault((norm(P.get(i, 'PedH')), norm(P.get(i, 'RMbQ'))), []).append(i)
    return by_last_birth, by_name


def best_row(R, rows):
    """Several DB rows for the same person: prefer the one with an NHL roster entry, then most entries."""
    def score(r):
        ts = [t for _, t in R.teams_of(r)]
        return (any(t < 32 or 222 <= t <= 233 for t in ts), len(ts))
    return max(rows, key=score)


def _similar(a, b):
    return difflib.SequenceMatcher(None, a, b).ratio()


def same_first_name(a, b):
    """Two normalised first names that can belong to one person (Matt / Matthew, Yegor / Egor).

    Twins share a last name and a birthdate, so a first name has to agree as well."""
    return a == b or (min(len(a), len(b)) >= 3 and (a.startswith(b) or b.startswith(a))) or _similar(a, b) >= 0.7


def match(R, people):
    """Set p['row'] (player record or None) and p['how'] on every dict in `people`.

    Each needs 'first', 'last' and 'birth' (y, m, d). Tried in order: last name + birthdate,
    full name, same birthdate with a near-identical last name, last name + birth year within one
    + first initial. A goalie only matches a goalie's record and a skater a skater's (when 'pos'
    is given): the game's own roster has a forward Daniil Tarasov, born 1991, who is not Detroit's
    goalie."""
    by_lb, by_name = build_index(R)
    by_birth = {}
    for (ln, b), rs in by_lb.items():
        by_birth.setdefault(b, []).extend((ln, r) for r in rs)
    P = R.P
    for p in people:
        if p.get('db_row') is not None:  # looked up for a known record (find_missing)
            p['row'], p['how'] = p['db_row'], 'extra'
            continue
        fn, ln = norm(p['first']), norm(p['last'])
        how = 'birth'
        rows = _same_kind(P, p, by_lb.get((ln, p['birth'])))
        p['row'] = best_row(R, rows) if rows else None
        if rows:
            p['how'] = how
            if len(rows) > 1:   # twins, or one person with two records: the first name decides
                rows = [r for r in rows if same_first_name(norm(P.get(r, 'PedH')), fn)] or rows
                p['row'] = best_row(R, rows)
            continue
        # the full name, with a birth year that can be his: within 2, or ten years late (a record
        # still in EA's year - 1900). The game's own roster has a Moncton junior Will Smith, born
        # 1996, who is not San Jose's, born 2005 (testers, 0.7.0)
        off = lambda r: min(abs(P.get(r, 'dnFq') + 1910 - p['birth'][0]), abs(P.get(r, 'dnFq') + 1900 - p['birth'][0]))
        rows = [r for r in _same_kind(P, p, by_name.get((fn, ln))) or ()
                if abs(P.get(r, 'dnFq') + 1910 - p['birth'][0]) <= 2
                or abs(P.get(r, 'dnFq') + 1900 - p['birth'][0]) <= 1]
        if len(rows) > 1:   # namesakes (the game's two Sebastian Ahos, 1996 and 1997): the closer birth year
            rows = [r for r in rows if off(r) == min(map(off, rows))]
        how = 'name'
        if not rows:  # same birthdate and a near-identical last name (spelling variants)
            how = 'birth+similar'
            rows = _same_kind(P, p, [r for l2, r in by_birth.get(p['birth'], []) if _similar(l2, ln) >= 0.8])
        if not rows:  # same last name, birth year within 1, same first initial
            how = 'last+year'
            rows = _same_kind(P, p, [r for (l2, b), rs in by_lb.items() if l2 == ln and abs(b[0] - p['birth'][0]) <= 1
                                     for r in rs if norm(P.get(r, 'PedH'))[:1] == fn[:1]])
        p['row'] = best_row(R, rows) if rows else None
        p['how'] = how if rows else 'none'
    return people


def _same_kind(P, p, rows):
    """The records among `rows` of the same kind of player as `p`: goalie or skater."""
    if not rows or not p.get('pos'):
        return rows
    goalie = p['pos'] == 'G'
    return [r for r in rows if (P.get(r, 'aljv') == 4) == goalie]


def match_club(R, people):
    """Stricter matching for club rosters: a record only counts when the birthdate agrees.

    Sets p['row'] and p['stale']. Records the community roster never touched still carry EA's
    original birth year, which reads ten years late in this roster's convention; such a record
    matches with p['stale'] = True (its ratings date from 2015 and its birth year needs fixing)."""
    by_lb, by_name = build_index(R)
    by_birth = {}
    for (ln, b), rs in by_lb.items():
        by_birth.setdefault(b, []).extend((ln, r) for r in rs)
    P = R.P
    by_last = {}
    for (f2, l2), rs in by_name.items():
        by_last.setdefault(l2, []).append((f2, rs))
    for p in people:
        fn, ln = norm(p['first']), norm(p['last'])
        y, m, d = p['birth']
        rows, stale = None, False
        if p.get('birth_approx'):
            # the league gives the age only (DEL): the full name and a birth year that fits it
            # (born in year y or y - 1), else a short or long form of his first name (the DEL's
            # Nicolas Krämmer is the game's Nico); a match brings the save's exact birthdate with it
            for shift in (0, 10):
                fits = lambda r: P.get(r, 'dnFq') + 1910 - shift in (y, y - 1)
                rows = [r for r in by_name.get((fn, ln), []) if fits(r)]
                if not rows:
                    rows = [r for f2, rs in by_last.get(ln, []) if same_first_name(f2, fn) for r in rs if fits(r)]
                if rows:
                    stale = shift == 10
                    break
            p['row'] = best_row(R, rows) if rows else None
            p['stale'] = stale
            if rows:
                r = p['row']
                p['birth'] = (P.get(r, 'dnFq') + 1910 - (10 if stale else 0), P.get(r, 'pLKJ') + 1, P.get(r, 'iwsK') + 1)
                p['birth_approx'] = False
            continue
        for shift in (0, 10):
            # same last name and birthdate -- and a first name that fits, because of twins
            rows = [r for r in by_lb.get((ln, (y + shift, m, d)), []) if same_first_name(norm(P.get(r, 'PedH')), fn)]
            if not rows:   # full name with the same day and month, the year within one
                rows = [r for r in by_name.get((fn, ln), [])
                        if (P.get(r, 'pLKJ') + 1, P.get(r, 'iwsK') + 1) == (m, d)
                        and abs(P.get(r, 'dnFq') + 1910 - (y + shift)) <= 1]
            if not rows:   # same birthdate, near-identical last name, same first initial
                rows = [r for l2, r in by_birth.get((y + shift, m, d), [])
                        if _similar(l2, ln) >= 0.8 and norm(P.get(r, 'PedH'))[:1] == fn[:1]]
            if rows:
                stale = shift == 10
                break
        p['row'] = best_row(R, rows) if rows else None
        p['stale'] = stale
    return people
