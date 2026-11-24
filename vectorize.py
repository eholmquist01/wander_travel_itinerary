import numpy as np
from sentence_transformers import SentenceTransformer
from queries import qualifying_shadow_user_ids, infer_profile

BUCKET_ORDER = [
    "food", "nightlife", "culture", "outdoors",
    "experiences", "relaxation", "shopping", "stays",
]

def profile_sentence(likes, dislikes):
    likes = [bucket for bucket in BUCKET_ORDER if bucket in likes]
    dislikes = [bucket for bucket in BUCKET_ORDER if bucket in dislikes]
    like_text = ", ".join(likes) if likes else "none"
    dislike_text = ", ".join(dislikes) if dislikes else "none"
    return f"Likes: {like_text}. Dislikes: {dislike_text}."

ids = qualifying_shadow_user_ids()[:5]
sentences = []
kept_ids = []
for user_id in ids:
    likes, dislikes, answers = infer_profile(user_id)
    sentences.append(profile_sentence(likes, dislikes))
    kept_ids.append(user_id)

for user_id, sentence in zip(kept_ids, sentences):
    print(user_id, sentence)

model = SentenceTransformer("all-MiniLM-L6-v2")
vectors = model.encode(sentences, normalize_embeddings=True)
print(vectors.shape)

for user_id in qualifying_shadow_user_ids()[:5]:
    likes, dislikes, answers = infer_profile(user_id)
    print(user_id, likes, dislikes)
    print(profile_sentence(likes, dislikes))
    print()