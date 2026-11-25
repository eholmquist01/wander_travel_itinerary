import math
import time

import queries

BUCKETS = ["food", "nightlife", "culture", "outdoors",
           "experiences", "relaxation", "shopping", "stays"]

FEELING_VALUE = {"like": 1, "dislike": -1}
ANSWER_VALUE = {"A": 1, "B": -1}   # both / neither / skipped count as 0

CACHE_SECONDS = 600
_cache = {"shadow": None, "shadow_time": 0, "cities": {}}


def build_vector(feelings, answers, pair_keys):
    """feelings: {bucket: 'like'/'dislike'}, answers: {pair_key: 'A'/'B'/'both'/'neither'}"""
    vector = [FEELING_VALUE.get(feelings.get(bucket), 0) for bucket in BUCKETS]
    vector += [ANSWER_VALUE.get(answers.get(key), 0) for key in pair_keys]
    return vector


def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _shadow_vectors(pair_keys):
    """{yelp_user_id: vector} for every saved shadow user. Kept in memory for a few minutes."""
    now = time.time()
    if _cache["shadow"] is None or now - _cache["shadow_time"] > CACHE_SECONDS:
        feelings, answers = {}, {}
        for row in queries.select_all_shadow_interests():
            feelings.setdefault(row["user_id"], {})[row["bucket"]] = row["feeling"]
        for row in queries.select_all_shadow_pair_answers():
            answers.setdefault(row["user_id"], {})[row["pair_key"]] = row["answer"]
        _cache["shadow"] = {
            uid: build_vector(feelings.get(uid, {}), answers.get(uid, {}), pair_keys)
            for uid in set(feelings) | set(answers)
        }
        _cache["shadow_time"] = now
        _cache["cities"] = {}
    return _cache["shadow"]


def _city_candidates(city):
    if city not in _cache["cities"]:
        _cache["cities"][city] = set(queries.get_city_candidates(city))
    return _cache["cities"][city]


def get_neighbors(user_id, city, k=25):
    """The k shadow users most like this user who have reviewed places in city.
    Returns [(yelp_user_id, similarity), ...], best first. Empty if the user
    has not done onboarding yet."""
    pair_keys = [row["pair_key"] for row in queries.select_onboarding_pairs()]
    answers, feelings, _free_text = queries.select_user_onboarding(user_id)
    mine = build_vector(feelings, answers, pair_keys)
    if not any(mine):
        return []

    shadow = _shadow_vectors(pair_keys)
    scored = []
    for other in _city_candidates(city):
        vector = shadow.get(other)
        if vector is None:
            continue
        similarity = cosine(mine, vector)
        if similarity > 0:
            scored.append((other, round(similarity, 4)))
    scored.sort(key=lambda pair: (-pair[1], pair[0]))
    return scored[:k]