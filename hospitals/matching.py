"""Finding the same hospital under a different spelling.

"Seatherney", "Seatherney Hospital" and "Seathurney Hosp." are one hospital:
names are compared after removing generic words (hospital, clinic, pvt ltd, ...)
and with a spelling-similarity score, so search can say "Did you mean ...?",
Add hospital can warn before creating a duplicate, and admins can see likely
duplicates to merge.
"""
from difflib import SequenceMatcher

from .models import Hospital, normalise_name

# Words that do not tell two hospitals apart.
GENERIC_WORDS = {
    "hospital", "hospitals", "hosp", "clinic", "clinics", "nursing", "home", "maternity",
    "multispeciality", "multispecialty", "multi", "speciality", "specialty", "super", "superspeciality",
    "superspecialty", "pvt", "private", "ltd", "limited", "llp", "the", "and", "of", "dr", "centre", "center",
    "medical", "medicare", "healthcare", "health", "care", "trust", "institute", "research", "foundation",
}

SUGGEST_SCORE = 0.78     # "Did you mean ...?" while typing / when adding
DUPLICATE_SCORE = 0.86   # shown on the admin "Possible duplicates" page


def core_name(text):
    """'Seatherney Multispeciality Hospital Pvt. Ltd.' -> 'seatherney'."""
    words = normalise_name(text).split()
    core = [w for w in words if w not in GENERIC_WORDS]
    return " ".join(core or words)


def meaningful_words(query):
    """Search words without the generic ones ('seatherney hospital' -> ['seatherney'])."""
    words = normalise_name(query).split()
    core = [w for w in words if w not in GENERIC_WORDS]
    return core or words


def _names(hospital):
    names = [hospital.name] + [a for a in (hospital.aliases or "").split(",") if a.strip()]
    return {core_name(n) for n in names if core_name(n)}


def score(query_core, hospital):
    """0..1: how likely `hospital` is the hospital the user typed."""
    best = 0.0
    q_words = query_core.split()
    for cand in _names(hospital):
        if cand == query_core:
            return 1.0
        ratio = SequenceMatcher(None, query_core, cand).ratio()
        # "seatherney" vs "seatherney kothrud": every typed word starts a word of the name
        c_words = cand.split()
        if q_words and all(len(qw) >= 3 for qw in q_words) and all(
                any(cw.startswith(qw) or (len(cw) >= 3 and qw.startswith(cw)) for cw in c_words) for qw in q_words):
            ratio = max(ratio, 0.9)
        best = max(best, ratio)
    return best


def find_similar(name, city="", exclude_ids=(), limit=5, threshold=SUGGEST_SCORE):
    """Active hospitals whose name looks like `name` (same city first if given)."""
    query_core = core_name(name)
    if len(query_core) < 3:
        return []
    city_key = normalise_name(city)
    scored = []
    for h in Hospital.objects.active().exclude(pk__in=list(exclude_ids)):
        s = score(query_core, h)
        if s >= threshold:
            same_city = bool(city_key) and normalise_name(h.city) == city_key
            scored.append((s + (0.05 if same_city else 0), h))
    scored.sort(key=lambda x: (-x[0], x[1].name.lower()))
    return [h for _, h in scored[:limit]]


def duplicate_groups():
    """Groups of active hospitals in the same city that look like the same place.

    Exact matches (same name after removing generic words) are always grouped.
    Spelling-similar pairs are checked for hospitals added by the team (doctors /
    admin), which is where duplicates come from, against all hospitals in that city.
    """
    hospitals = list(Hospital.objects.active())
    by_city = {}
    for h in hospitals:
        by_city.setdefault(normalise_name(h.city), []).append(h)

    parent = {h.pk: h.pk for h in hospitals}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    for city_hospitals in by_city.values():
        by_core = {}
        for h in city_hospitals:
            by_core.setdefault(core_name(h.name), []).append(h)
        for same in by_core.values():
            for other in same[1:]:
                union(same[0].pk, other.pk)
        added = [h for h in city_hospitals if h.source in ("doctor", "admin")]
        for a in added:
            a_core = core_name(a.name)
            for b in city_hospitals:
                if b.pk != a.pk and score(a_core, b) >= DUPLICATE_SCORE:
                    union(a.pk, b.pk)

    groups = {}
    for h in hospitals:
        groups.setdefault(find(h.pk), []).append(h)
    result = [sorted(g, key=lambda h: (h.source not in ("directory", "starter"), h.pk)) for g in groups.values() if len(g) > 1]
    result.sort(key=lambda g: g[0].name.lower())
    return result
