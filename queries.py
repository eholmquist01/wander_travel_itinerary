import pymysql
import pymysql.cursors

# Configure database
def get_db():
    return pymysql.connect(
        host='localhost',
        user='mbegley2',
        password='not_private_password',
        database='mbegley2',
        cursorclass=pymysql.cursors.DictCursor
    )

# Helper: run a SELECT and return one row (one=True) or a list of rows
def query(sql, params=(), one=False):
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute(sql, params)
        return cursor.fetchone() if one else cursor.fetchall()
    finally:
        cursor.close()
        db.close()


# Select top markers for a location, top limit included
def select_marker_by_location(city, limit):
    return query(
        "SELECT Markers.business_id, Markers.name, Markers.address, Markers.city, "
        "Markers.stars, Markers.review_count, "
        "GROUP_CONCAT(Categories.name ORDER BY Categories.name SEPARATOR ', ') AS categories "
        "FROM Markers "
        "LEFT JOIN MarkerCategories ON MarkerCategories.business_id = Markers.business_id "
        "LEFT JOIN Categories ON Categories.category_id = MarkerCategories.category_id "
        "WHERE Markers.city = %s "
        "GROUP BY Markers.business_id, Markers.name, Markers.address, Markers.city, "
        "Markers.stars, Markers.review_count "
        "ORDER BY Markers.stars DESC, Markers.review_count DESC "
        "LIMIT %s",
        (city, limit)
    )


# Select top X amount of markers
def select_top_markers(x):
    x = max(1, min(int(x), 100))  # keep X between 1 and 100
    return query(
        "SELECT Markers.business_id, Markers.name, Markers.city, Markers.stars, Markers.review_count "
        "FROM Markers "
        "ORDER BY Markers.stars DESC, Markers.review_count DESC "
        "LIMIT %s",
        (x,)
    )

# Cities we have data for
def get_cities():
    rows = query("SELECT DISTINCT city FROM Markers ORDER BY city")
    return [row["city"] for row in rows]

# Get boards by user
def get_boards_by_user(user_id, view="all"):
    selected = (
        "SELECT Boards.board_id, Boards.image_filename, Boards.title, Boards.destination, Boards.time_created, "
        "Boards.creator_id, Users.name AS owner_name "
        "FROM Boards "
        "JOIN Users ON Users.user_id = Boards.creator_id "
    )
    if view == "mine":
        return query(
            selected +
            "WHERE Boards.creator_id = %s "
            "ORDER BY Boards.title",
            (user_id,)
        )
    elif view == "shared":
        return query(
            selected + 
            "WHERE Boards.creator_id <> %s "
            "AND Boards.board_id IN (SELECT board_id FROM Users_Create WHERE user_id = %s) "
            "ORDER BY Boards.title",
            (user_id, user_id)
        )

    else:
        return query(
            selected +
            "WHERE Boards.creator_id = %s "
            "OR Boards.board_id IN (SELECT board_id FROM Users_Create WHERE user_id = %s) "
            "ORDER BY Boards.title",
            (user_id, user_id)
        )


# Get one board for the details page
def get_board(board_id):
    return query (
        "SELECT board_id, title, destination, time_created, creator_id "
        "FROM Boards WHERE board_id = %s",
        (board_id,),
        one=True
    )

    #Helper for insert, update, delete: returns number of entries affected
def execute(sql, params=()):
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute(sql, params)
        db.commit()
        return cursor.rowcount
    finally:
        cursor.close()
        db.close()

def insert(sql, params=()):
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute(sql, params)
        db.commit()
        return cursor.lastrowid
    finally:
        cursor.close()
        db.close()

# Create board
def create_board(user_id, title, destination):
    board_id = insert("INSERT INTO Boards (title, destination, time_created, creator_id) "
    " VALUES (%s, %s, NOW(), %s)",
    (title, destination, user_id)
    )
    execute("INSERT INTO Users_Create (board_id, user_id, role) VALUES (%s, %s, 'owner')",
    (board_id, user_id))
    return board_id

#Delete board
def delete_board(board_id, user_id):
    board = query("SELECT board_id FROM Boards WHERE board_id = %s AND creator_id = %s",
    (board_id, user_id), one=True)

    if board is None:
        return 0
    
    execute("DELETE FROM Boards_Have WHERE board_id = %s", (board_id,))
    execute("DELETE FROM Users_Create WHERE board_id = %s", (board_id,))
    return execute("DELETE FROM Boards WHERE board_id = %s", (board_id,))

#Delete user
def delete_user(user_id):
    return execute("DELETE FROM Users WHERE user_id = %s",
            (user_id,)
    )

#Change board name by id
def update_board_name(new_name, board_id, user_id):
    return execute("UPDATE Boards SET title = %s WHERE board_id = %s AND creator_id = %s",
    (new_name, board_id, user_id)
    )

# Save an image for a board. Only the creator can change it.
# Returns the number of rows updated (0 means it was not allowed).
def set_board_image(board_id, filename, user_id):
    return execute(
        "UPDATE Boards SET image_filename = %s "
        "WHERE board_id = %s AND creator_id = %s",
        (filename, board_id, user_id)
    )

# Search users by name or email, leaving out anyone on board already
def search_users(term, board_id):
    similar = "%" + term + "%"

    return query(
        "SELECT user_id, name, email FROM Users "
        "WHERE (name LIKE %s or email LIKE %s) "
        "AND user_id NOT IN (SELECT user_id FROM Users_Create WHERE board_id = %s) "
        "AND user_id <> (SELECT creator_id FROM Boards WHERE board_id = %s) "
        "ORDER BY name "
        "LIMIT 10",
        (similar, similar, board_id, board_id)
    )

# Everyone on the board
def get_board_members(board_id):
    return query(
        "SELECT Users.user_id, Users.name, Users.email, 'owner' AS role "
        "FROM Boards "
        "JOIN Users ON Users.user_id = Boards.creator_id "
        "WHERE Boards.board_id = %s "
        "UNION "
        "SELECT Users.user_id, Users.name, Users.email, Users_Create.role "
        "FROM Users_Create "
        "JOIN Users ON Users.user_id = Users_Create.user_id "
        "JOIN Boards On Boards.board_id = Users_Create.board_id "
        "WHERE Users_Create.board_id = %s "
        "AND Users_Create.user_id <> Boards.creator_id "
        "ORDER BY role DESC, name",
        (board_id, board_id)
    )

# Add collaborator; if this user is already a collaborator, return false to avoid duplicate key
def add_collaborator(board_id, other_user_id):
    # Check whether the user exists
    user = query("""
        SELECT user_id
        FROM Users
        WHERE user_id = %s
    """, (other_user_id,))

    if not user:
        return False  # User doesn't exist
    #make sure other user isnt already a collaborator
    existing = query("""
        SELECT *
        FROM Users_Create
        WHERE board_id = %s AND user_id = %s
    """, (board_id, other_user_id))

    if existing:
        return False
        
    return execute("""
        INSERT INTO Users_Create (board_id, user_id, role)
        VALUES (%s, %s, 'collaborator')
    """, (board_id, other_user_id))

def user_on_board(board_id, user_id):
    row = query(
        "SELECT 1 AS ok FROM Users_Create WHERE board_id = %s AND user_id = %s",
        (board_id, user_id), one=True)
    return row is not None

#indicates rs btwn board and user 
def get_member_role(board_id, user_id): 
    row = query(
        "SELECT CASE WHEN Boards.creator_id = %s THEN 'owner' "
        "ELSE (SELECT role FROM Users_Create WHERE board_id = %s AND user_id = %s) END AS role "
        "FROM Boards WHERE Boards.board_id = %s",
        (user_id, board_id, user_id, board_id), one=True)
    return row["role"] if row else None

def can_view_board(board_id, user_id):
    return get_member_role(board_id, user_id) is not None

def can_edit_board(board_id, user_id):
    return get_member_role(board_id, user_id) in ("owner", "collaborator")

def is_board_owner(board_id, user_id):
    return get_member_role(board_id, user_id) == "owner"

def get_marker(business_id):
    return query(
        "SELECT business_id, name FROM Markers WHERE business_id = %s",
        (business_id,), one=True)


def get_board_marker_ids(board_id):
    rows = query("SELECT business_id FROM Boards_Have WHERE board_id = %s", (board_id,))
    return {r["business_id"] for r in rows}


# Places in a city, optionally only those in one category
def select_places(city, category, limit):
    sql = (
        "SELECT Markers.business_id, Markers.name, Markers.address, Markers.city, "
        "Markers.stars, Markers.review_count, "
        "GROUP_CONCAT(Categories.name ORDER BY Categories.name SEPARATOR ', ') AS categories "
        "FROM Markers "
        "LEFT JOIN MarkerCategories ON MarkerCategories.business_id = Markers.business_id "
        "LEFT JOIN Categories ON Categories.category_id = MarkerCategories.category_id "
        "WHERE Markers.city = %s "
    )
    params = [city]
    if category:
        sql += (
            "AND Markers.business_id IN ("
            "SELECT MarkerCategories.business_id FROM MarkerCategories "
            "JOIN Categories ON Categories.category_id = MarkerCategories.category_id "
            "WHERE Categories.name = %s) "
        )
        params.append(category)
    sql += (
        "GROUP BY Markers.business_id, Markers.name, Markers.address, Markers.city, "
        "Markers.stars, Markers.review_count "
        "ORDER BY Markers.stars DESC, Markers.review_count DESC "
        "LIMIT %s"
    )
    params.append(limit)
    return query(sql, tuple(params))


# Most common categories in a city, for the filter dropdown
def get_city_categories(city):
    return query(
        "SELECT Categories.name, COUNT(*) AS total "
        "FROM Markers "
        "JOIN MarkerCategories ON MarkerCategories.business_id = Markers.business_id "
        "JOIN Categories ON Categories.category_id = MarkerCategories.category_id "
        "WHERE Markers.city = %s "
        "GROUP BY Categories.category_id, Categories.name "
        "ORDER BY total DESC "
        "LIMIT 40",
        (city,))

# Returns 1 if added, 0 if it was already on the board
def add_marker_to_board(board_id, business_id):
    return execute(
        "INSERT INTO Boards_Have (board_id, business_id) "
        "SELECT %s, %s FROM DUAL "
        "WHERE NOT EXISTS (SELECT 1 FROM Boards_Have WHERE board_id = %s AND business_id = %s)",
        (board_id, business_id, board_id, business_id))

def get_board_markers(board_id):
    return query(
        "SELECT Markers.business_id, Markers.name, Markers.address, Markers.city, "
        "Markers.stars, Markers.review_count, "
        "GROUP_CONCAT(Categories.name ORDER BY Categories.name SEPARATOR ', ') AS categories "
        "FROM Boards_Have "
        "JOIN Markers ON Markers.business_id = Boards_Have.business_id "
        "LEFT JOIN MarkerCategories ON MarkerCategories.business_id = Markers.business_id "
        "LEFT JOIN Categories ON Categories.category_id = MarkerCategories.category_id "
        "WHERE Boards_Have.board_id = %s "
        "GROUP BY Markers.business_id, Markers.name, Markers.address, Markers.city, "
        "Markers.stars, Markers.review_count "
        "ORDER BY Markers.name",
        (board_id,))

def remove_marker_from_board(board_id, business_id):
    return execute(
        "DELETE FROM Boards_Have WHERE board_id = %s AND business_id = %s",
        (board_id, business_id))


# Onboarding: this-or-that questions, in display order
def select_onboarding_pairs():
    return query(
        "SELECT pair_key, question, option_a, option_b "
        "FROM OnboardingPairs "
        "ORDER BY sort_order"
    )

# Onboarding: save a user's taste answers, replacing any earlier answers
def save_onboarding(user_id, free_text, pair_answers, likes, dislikes):
    execute("DELETE FROM UserPairAnswers WHERE user_id = %s", (user_id,))
    execute("DELETE FROM UserInterests WHERE user_id = %s", (user_id,))

    execute(
        "INSERT INTO UserOnboarding (user_id, free_text) VALUES (%s, %s) "
        "ON DUPLICATE KEY UPDATE free_text = VALUES(free_text)",
        (user_id, free_text),
    )

    for pair_key, answer in pair_answers.items():
        execute(
            "INSERT INTO UserPairAnswers (user_id, pair_key, answer) VALUES (%s, %s, %s)",
            (user_id, pair_key, answer),
        )

    for bucket in likes:
        execute(
            "INSERT INTO UserInterests (user_id, bucket, feeling) VALUES (%s, %s, 'like')",
            (user_id, bucket),
        )

    for bucket in dislikes:
        execute(
            "INSERT INTO UserInterests (user_id, bucket, feeling) VALUES (%s, %s, 'dislike')",
            (user_id, bucket),
        )

# Onboarding: a user's saved answers, to pre-fill the form
# Returns ({pair_key: answer}, {bucket: 'like'/'dislike'}, free_text or None)
def select_user_onboarding(user_id):
    pairs = query("SELECT pair_key, answer FROM UserPairAnswers WHERE user_id = %s", (user_id,))
    interests = query("SELECT bucket, feeling FROM UserInterests WHERE user_id = %s", (user_id,))
    onboarding = query("SELECT free_text FROM UserOnboarding WHERE user_id = %s", (user_id,), one=True)

    answers = {row["pair_key"]: row["answer"] for row in pairs}
    feelings = {row["bucket"]: row["feeling"] for row in interests}
    free_text = onboarding["free_text"] if onboarding else None
    return answers, feelings, free_text

# Boards: save or update a board's trip vibe (focus is a list of buckets)
def save_trip_vibe(board_id, city, focus, vibe):
    execute(
        "INSERT INTO BoardTripVibe (board_id, city, focus, vibe) VALUES (%s, %s, %s, %s) "
        "ON DUPLICATE KEY UPDATE city = VALUES(city), focus = VALUES(focus), vibe = VALUES(vibe)",
        (board_id, city, ";".join(focus), vibe),
    )

# Boards: a board's trip vibe, with focus as a list. None if not set yet.
def select_trip_vibe(board_id):
    row = query("SELECT city, focus, vibe FROM BoardTripVibe WHERE board_id = %s", (board_id,), one=True)
    if row is None:
        return None
    row["focus"] = [b for b in (row["focus"] or "").split(";") if b]
    return row

# Shadow profiles: the same UserInterests and UserPairAnswers shape as onboarding,
TRAVEL_BUCKETS = (
    "food", "nightlife", "culture", "outdoors",
    "experiences", "relaxation", "shopping", "stays",
)

def qualifying_shadow_user_ids():
    """Reviewers with at least 10 reviews of a specifically categorized place."""
    placeholders = ", ".join(["%s"] * len(TRAVEL_BUCKETS))
    rows = query(
        f"""
        SELECT R.user_id
        FROM Reviews R
        WHERE R.user_id IS NOT NULL
          AND EXISTS (
              SELECT 1
              FROM MarkerCategories MC
              JOIN Categories C ON MC.category_id = C.category_id
              JOIN CategoryMap CM ON C.name = CM.category
              WHERE MC.business_id = R.business_id
                AND CM.type = 'specific'
                AND CM.bucket IN ({placeholders})
          )
        GROUP BY R.user_id
        HAVING COUNT(DISTINCT R.review_id) >= 10
        """,
        TRAVEL_BUCKETS,
    )
    return [row["user_id"] for row in rows]



def infer_profile(user_id):
    """Return (likes, dislikes, pair_answers) for one reviewer.

    likes and dislikes are bucket lists. pair_answers maps pair_key to
    'A', 'B', or 'both'. Neutral buckets and unanswered pairs are absent.
    """
    placeholders = ", ".join(["%s"] * len(TRAVEL_BUCKETS))
    bucket_rows = query(
        f"""
        SELECT bucket, COUNT(*) AS n, AVG(stars) AS avg_stars
        FROM (
            SELECT DISTINCT R.review_id, R.stars, CM.bucket
            FROM Reviews R
            JOIN MarkerCategories MC ON MC.business_id = R.business_id
            JOIN Categories C ON C.category_id = MC.category_id
            JOIN CategoryMap CM ON C.name = CM.category
            WHERE R.user_id = %s
              AND CM.type = 'specific'
              AND CM.bucket IN ({placeholders})
        ) AS review_buckets
        GROUP BY bucket
        """,
        (user_id, *TRAVEL_BUCKETS),
    )

    like_candidates = []
    dislikes = []
    for row in bucket_rows:
        review_count = row["n"]
        avg_stars = float(row["avg_stars"])
        if review_count < 3:
            continue
        if avg_stars >= 4:
            like_candidates.append((avg_stars, review_count, row["bucket"]))
        elif avg_stars <= 2:
            dislikes.append(row["bucket"])
    like_candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    likes = [bucket for avg_stars, review_count, bucket in like_candidates[:4]]

    pair_rows = query(
        f"""
        SELECT DISTINCT PS.pair_key, PS.side, R.review_id, R.stars
        FROM Reviews R
        JOIN MarkerCategories MC ON MC.business_id = R.business_id
        JOIN Categories C ON C.category_id = MC.category_id
        JOIN CategoryMap CM ON C.name = CM.category
        JOIN PairSides PS ON PS.subgroup = CM.subgroup
        WHERE R.user_id = %s
          AND CM.type = 'specific'
          AND CM.bucket IN ({placeholders})
        """,
        (user_id, *TRAVEL_BUCKETS),
    )

    grouped = {}
    for row in pair_rows:
        side = (row["side"] or "").strip().upper()
        if side not in ("A", "B"):
            continue
        pair = grouped.setdefault(row["pair_key"], {"A": {}, "B": {}})
        pair[side][row["review_id"]] = float(row["stars"])

    pair_answers = {}
    for pair_key, sides in grouped.items():
        side_a = sides["A"]
        side_b = sides["B"]
        classified = set(side_a) | set(side_b)
        if not classified:
            continue
        share_a = len(side_a) / len(classified)
        share_b = len(side_b) / len(classified)
        if side_a and side_b:
            avg_a = sum(side_a.values()) / len(side_a)
            avg_b = sum(side_b.values()) / len(side_b)
            star_gap = (avg_a - avg_b) / 4
        else:
            star_gap = 0
        preference = 0.6 * (share_a - share_b) + 0.4 * star_gap
        if preference > 0.1:
            pair_answers[pair_key] = "A"
        elif preference < -0.1:
            pair_answers[pair_key] = "B"
        else:
            pair_answers[pair_key] = "both"

    return likes, dislikes, pair_answers


def save_shadow_profile(user_id, likes, dislikes, pair_answers):
    """Replace this reviewer's inferred rows. Leave real onboarding rows alone."""
    existing = query(
        "SELECT user_id FROM UserOnboarding WHERE user_id = %s",
        (user_id,),
        one=True,
    )
    if existing:
        return False

    execute("DELETE FROM UserPairAnswers WHERE user_id = %s", (user_id,))
    execute("DELETE FROM UserInterests WHERE user_id = %s", (user_id,))

    for pair_key, answer in pair_answers.items():
        execute(
            "INSERT INTO UserPairAnswers (user_id, pair_key, answer) VALUES (%s, %s, %s)",
            (user_id, pair_key, answer),
        )
    for bucket in likes:
        execute(
            "INSERT INTO UserInterests (user_id, bucket, feeling) VALUES (%s, %s, 'like')",
            (user_id, bucket),
        )
    for bucket in dislikes:
        execute(
            "INSERT INTO UserInterests (user_id, bucket, feeling) VALUES (%s, %s, 'dislike')",
            (user_id, bucket),
        )
    return True

# Save many shadow profiles at once (one connection, one commit)
# profiles: list of (yelp_user_id, likes, dislikes, pair_answers)
def save_shadow_profiles_bulk(profiles):
    db = get_db()
    cursor = db.cursor()
    try:
        ids = [(p[0],) for p in profiles]
        interest_rows, pair_rows = [], []
        for yelp_user_id, likes, dislikes, pair_answers in profiles:
            interest_rows += [(yelp_user_id, b, "like") for b in likes]
            interest_rows += [(yelp_user_id, b, "dislike") for b in dislikes]
            pair_rows += [(yelp_user_id, k, a) for k, a in pair_answers.items()]

        cursor.executemany("DELETE FROM ShadowInterests WHERE yelp_user_id = %s", ids)
        cursor.executemany("DELETE FROM ShadowPairAnswers WHERE yelp_user_id = %s", ids)
        if interest_rows:
            cursor.executemany(
                "INSERT INTO ShadowInterests (yelp_user_id, bucket, feeling) VALUES (%s, %s, %s)",
                interest_rows)
        if pair_rows:
            cursor.executemany(
                "INSERT INTO ShadowPairAnswers (yelp_user_id, pair_key, answer) VALUES (%s, %s, %s)",
                pair_rows)
        db.commit()
    finally:
        cursor.close()
        db.close()

# Matching: saved shadow profiles (Yelp reviewers)
def select_all_shadow_interests():
    return query("SELECT yelp_user_id AS user_id, bucket, feeling FROM ShadowInterests")


def select_all_shadow_pair_answers():
    return query("SELECT yelp_user_id AS user_id, pair_key, answer FROM ShadowPairAnswers")


# Shadow users who have reviewed at least min_places places in a city
def get_city_candidates(city, min_places=3):
    rows = query(
        "SELECT Reviews.user_id "
        "FROM Reviews "
        "JOIN Markers ON Markers.business_id = Reviews.business_id "
        "WHERE Markers.city = %s "
        "AND Reviews.user_id IN (SELECT yelp_user_id FROM ShadowInterests "
        "UNION SELECT yelp_user_id FROM ShadowPairAnswers) "
        "GROUP BY Reviews.user_id "
        "HAVING COUNT(DISTINCT Reviews.business_id) >= %s",
        (city, min_places))
    return [row["user_id"] for row in rows]
