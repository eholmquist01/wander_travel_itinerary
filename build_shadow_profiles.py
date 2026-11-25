import sys
from queries import qualifying_shadow_user_ids, infer_profile, save_shadow_profiles_bulk

limit = int(sys.argv[1]) if len(sys.argv) > 1 else None

ids = qualifying_shadow_user_ids()
print(len(ids), "qualifying reviewers")
if limit:
    ids = ids[:limit]

batch, saved = [], 0
for n, yelp_user_id in enumerate(ids, 1):
    likes, dislikes, pair_answers = infer_profile(yelp_user_id)
    if likes or dislikes or pair_answers:
        batch.append((yelp_user_id, likes, dislikes, pair_answers))
    if len(batch) >= 200:
        save_shadow_profiles_bulk(batch)
        saved += len(batch)
        batch = []
        print(n, "processed")

if batch:
    save_shadow_profiles_bulk(batch)
    saved += len(batch)
print("saved", saved, "profiles")