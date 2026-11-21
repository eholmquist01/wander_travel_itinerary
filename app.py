import os
import uuid
from urllib.parse import quote
from flask import Flask, send_from_directory, render_template, flash, redirect, request, session
import pymysql
import pymysql.cursors
from queries import (get_db, select_marker_by_location, select_top_markers, get_cities, get_boards_by_user,
                    get_board, create_board, update_board_name, delete_board, set_board_image, 
                    user_on_board, get_marker, get_board_marker_ids, select_places, get_city_categories,
                    add_marker_to_board, get_board_markers, remove_marker_from_board, get_board_members, search_users, add_collaborator,
                    can_view_board, can_edit_board, is_board_owner, select_onboarding_pairs, save_onboarding, select_user_onboarding,
                    save_trip_vibe, select_trip_vibe)
                    # remove_collaborator,
                    #if we're gonna add invites we also need to make sure create_invite, get_pending_invite, get_invite, and delete_invite are created.

# Onboarding Global Variables
# (bucket, label shown on screen, examples shown under it)
BUCKET_LABELS = [
    ("food", "Food & drink", "Restaurants, cafes, sweets"),
    ("nightlife", "Nightlife", "Bars, breweries, live music"),
    ("culture", "Arts & culture", "Museums, galleries, shows"),
    ("outdoors", "Outdoors", "Parks, hiking, golf"),
    ("experiences", "Fun & attractions", "Theme parks, zoos, escape rooms, tours"),
    ("relaxation", "Relax & unwind", "Spas, massage"),
    ("shopping", "Shopping", "Boutiques, vintage, markets"),
    ("stays", "Where to stay", "Hotels"),
]
BUCKETS = [bucket for bucket, label, examples in BUCKET_LABELS]
VALID_ANSWERS = {"A", "B", "both", "neither"} # used in the pair answering
VIBE_OPTIONS = [
    ("famous", "Famous must-sees", "The spots everyone talks about", "star"),
    ("mix", "A bit of both", "Classics plus a few surprises", "shuffle"),
    ("hidden", "Hidden gems", "Places only locals know", "search"),
]
VALID_VIBES = {option[0] for option in VIBE_OPTIONS}
PAIR_ICONS = {
    "food_quick_vs_sitdown": ("burger", "dinner"),
    "bars_upscale_vs_casual": ("cocktail", "beer"),
    "food_comfort_vs_global": ("drumstick", "globe"),
    "day_spa_vs_adventure": ("relaxation", "mountain"),
    "food_brunch_vs_sweets": ("coffee", "icecream"),
    "night_brewery_vs_music": ("beer", "music"),
    "food_healthy_vs_burger": ("salad", "fries"),
    "shop_fashion_vs_vintage": ("hanger", "vase"),
    "fun_show_vs_games": ("mic", "controller"),
    "day_museum_vs_park": ("culture", "outdoors"),
    "vibe_famous_vs_hidden": ("star", "search"),
}
# Optional photos: static/images/onboarding/<pair_key>_a.jpg and _b.jpg (or .png / .webp)
PAIR_IMAGE_DIR = os.path.join("static", "images", "onboarding")
MAX_LIKES = 4   # favorites on the interest section
MAX_FOCUS = 3   # focus buckets per trip


app = Flask(__name__)
app.secret_key = "wander-session-key"

# Image upload settings
UPLOAD_DIR = os.path.join(app.root_path, "static", "uploads")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # 5 MB
os.makedirs(UPLOAD_DIR, exist_ok=True)

def require_board(board_id, level="view"):
    if "user_id" not in session:
        return None, redirect("/login")
    board = get_board(board_id)
    check = {"view": can_view_board, "edit": can_edit_board, "owner": is_board_owner}[level]
    # Same message for "missing" and "not allowed" so board IDs aren't leaked
    if board is None or not check(board_id, session["user_id"]):
        flash("Board not found.")
        return None, redirect("/profile")
    return board, None

# Onboarding helpers
def clean_option(text):
    # Drops a leading emoji (e.g. "🍔 Quick bite" -> "Quick bite"), since the page shows icons instead
    if text and not text[0].isalnum() and " " in text:
        return text.split(" ", 1)[1]
    return text

def onboarding_pairs():
    pairs = select_onboarding_pairs()
    for pair in pairs:
        pair["option_a"] = clean_option(pair["option_a"])
        pair["option_b"] = clean_option(pair["option_b"])
    return pairs

def pair_images(pairs):
    # Returns {pair_key: {"A": url, "B": url}} for any photos that exist
    images = {}
    for pair in pairs:
        for side in ("a", "b"):
            for extension in ("jpg", "jpeg", "png", "webp"):
                filename = f"{pair['pair_key']}_{side}.{extension}"
                if os.path.exists(os.path.join(app.root_path, PAIR_IMAGE_DIR, filename)):
                    images.setdefault(pair["pair_key"], {})[side.upper()] = f"/static/images/onboarding/{filename}"
                    break
    return images

def render_onboarding(pairs, answers, interests, free_text, editing, start_step=""):
    return render_template("onboarding.html", pairs=pairs, buckets=BUCKET_LABELS,
                           answers=answers, interests=interests, free_text=free_text or "",
                           editing=editing, max_likes=MAX_LIKES, start_step=start_step,
                           pair_icons=PAIR_ICONS, pair_images=pair_images(pairs))

# Stage 1 + 2 access points
@app.route("/")
def home():
    return send_from_directory(".", "index.html")

@app.route("/project.html")
def project():
    return send_from_directory(".", "project.html")

@app.route("/devplan.html")
def devplan():
    return send_from_directory(".", "devplan.html")

# Stage 3 Additions
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if "user_id" in session:
        return redirect("/profile")

    if request.method == "POST":
        name = request.form["name"].strip()
        email = request.form["email"].strip()
        password = request.form["password"]

        if not name or not email or not password:
            flash("Please fill in fields.")
            return render_template("signup.html")
        db = get_db()
        cursor = db.cursor()
        try:
            cursor.execute("INSERT INTO Users (name, email, password) VALUES (%s, %s, %s)", (name, email, password))
            db.commit()
            session["user_id"] = cursor.lastrowid
            session["name"] = name
            return redirect("/profile")
        except pymysql.IntegrityError:
            flash("An account already exists.")
        finally:
            cursor.close()
            db.close()

    return render_template("signup.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect("/profile")

    if request.method == "POST":
        email = request.form["email"].strip()
        password = request.form["password"]
        db = get_db()
        cursor = db.cursor()
        cursor.execute("select user_id, name from Users where email = %s and password = %s", (email, password))
        user = cursor.fetchone()
        cursor.close()
        db.close()
        
        if user:
            session["user_id"] = user["user_id"]
            session["name"] = user["name"]
            return redirect("/profile")
        flash("Email or password is wrong")

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# Accessed after Login
@app.route("/profile")
def profile():
    if "user_id" not in session:
        return redirect("/login")
    view = request.args.get("view", "all")
    if view not in ("all", "mine", "shared"):
        view = "all"
    my_boards = get_boards_by_user(session["user_id"], view)  
    return render_template("board_profile.html", name=session["name"], boards=my_boards, view=view) 

# Create a new board form
@app.route("/boards/new", methods=["GET", "POST"])
def new_board():
    if "user_id" not in session:
        return redirect("/login")
    if request.method=="POST":
        title = request.form["title"].strip()
        destination = request.form["destination"].strip()

        if not title or not destination:
            flash("Please give your board a title and destination")
            return render_template("board_form.html", cities=get_cities())
        
        board_id = create_board(session["user_id"], title, destination)
        flash(f"Created {title}. Add some places to it.")
        return redirect(f"/boards/{board_id}/places")
    return render_template("board_form.html", cities=get_cities())

# View Board Details: the places saved on this board
@app.route("/boards/<int:board_id>")
def board_details(board_id):
    if "user_id" not in session:
        return redirect("/login")

    board = get_board(board_id)
    if board is None or not user_on_board(board_id, session["user_id"]):
        flash("Board not found.")
        return redirect("/profile")
    markers = get_board_markers(board_id)
    is_owner = (board["creator_id"] == session["user_id"])
    q = request.args.get("q", "").strip()
    user_results = search_users(q, board_id) if (is_owner and q) else []
    return render_template("board_details.html", board=board, markers=markers, members=get_board_members(board_id), is_owner=is_owner, q=q, user_results=user_results)

# Add Member to Board
@app.route("/boards/<int:board_id>/members/add", methods=["POST"])
def add_member(board_id):
    if "user_id" not in session:
        return redirect("/login")
    
    board = get_board(board_id)
    if board is None or board["creator_id"] != session["user_id"]:
        flash("Only the owner can add people.")
        return redirect("/profile")
    
    if add_collaborator(board_id, int(request.form["user_id"])):
        flash("Collaborator added.")
    else:
        flash("Person already added, or doesn't exit")
    return redirect(f"/boards/{board_id}")

# Edit Board: change the name and/or image in one save
@app.route("/boards/<int:board_id>/edit", methods=["POST"])
def edit_board(board_id):
    if "user_id" not in session:
        return redirect("/login")

    board = get_board(board_id)
    if board is None:
        flash("Board not found.")
        return redirect("/profile")

    # Name
    new_title = request.form.get("title", "").strip()
    if new_title and new_title != board["title"]:
        if update_board_name(new_title, board_id, session["user_id"]):
            flash(f"Board renamed to {new_title}.")
        else:
            flash("Couldn't rename that board.")

    # Image (optional)
    image = request.files.get("image")
    if image is not None and image.filename != "":
        extension = image.filename.rsplit(".", 1)[-1].lower() if "." in image.filename else ""
        header = image.stream.read(12)
        image.stream.seek(0)
        looks_like_image = (header.startswith(b"\x89PNG")
                            or header.startswith(b"\xff\xd8\xff")
                            or header.startswith(b"GIF8")
                            or (header[:4] == b"RIFF" and header[8:12] == b"WEBP"))
        if extension not in ALLOWED_EXTENSIONS or not looks_like_image:
            flash("Use a PNG, JPG, GIF or WebP image.")
        else:
            filename = uuid.uuid4().hex + "." + extension
            image.save(os.path.join(UPLOAD_DIR, filename))
            if set_board_image(board_id, filename, session["user_id"]):
                flash("Board image updated.")
            else:
                os.remove(os.path.join(UPLOAD_DIR, filename))
                flash("Only the person who created a board can change its image.")

    return redirect("/profile")

# Shown when an image is over 5 MB
@app.errorhandler(413)
def image_too_large(error):
    flash("That image is over 5 MB. Choose a smaller one.")
    return redirect("/profile")

# Delete Board from Page
@app.route("/boards/<int:board_id>/delete", methods=["POST"])
def remove_board(board_id):
    if "user_id" not in session:
        return redirect("/login")
    if delete_board(board_id, session["user_id"]):
        flash("Board deleted.")
    else:
        flash("Couldn't delete board")
    return redirect("/profile")

# Browse places in the board's city so they can be added to the board
@app.route("/boards/<int:board_id>/places")
def browse_places(board_id):
    if "user_id" not in session:
        return redirect("/login")

    board = get_board(board_id)
    if board is None or not user_on_board(board_id, session["user_id"]):
        flash("Board not found.")
        return redirect("/profile")

    category = request.args.get("category", "").strip()
    markers = select_places(board["destination"], category, 50)
    categories = get_city_categories(board["destination"])
    saved_ids = get_board_marker_ids(board_id)
    return render_template("places.html", board=board, markers=markers,
                           saved_ids=saved_ids, category=category, categories=categories)

# Add a place to a board
@app.route("/boards/<int:board_id>/add/<business_id>", methods=["POST"])
def add_place(board_id, business_id):
    if "user_id" not in session:
        return redirect("/login")

    board = get_board(board_id)
    if board is None or not user_on_board(board_id, session["user_id"]):
        flash("Board not found.")
        return redirect("/profile")

    category = request.form.get("category", "").strip()
    back = f"/boards/{board_id}/places"
    if category:
        back += "?category=" + quote(category)

    marker = get_marker(business_id)
    if marker is None:
        flash("That place doesn't exist.")
        return redirect(back)

    if add_marker_to_board(board_id, business_id):
        flash(f"Added {marker['name']} to {board['title']}.")
    else:
        flash(f"{marker['name']} is already on {board['title']}.")
    return redirect(back + f"#place-{business_id}")

# Remove a place from a board
@app.route("/boards/<int:board_id>/remove/<business_id>", methods=["POST"])
def remove_place(board_id, business_id):
    if "user_id" not in session:
        return redirect("/login")

    board = get_board(board_id)
    if board is None or not user_on_board(board_id, session["user_id"]):
        flash("Board not found.")
        return redirect("/profile")

    marker = get_marker(business_id)
    if marker is not None and remove_marker_from_board(board_id, business_id):
        flash(f"Removed {marker['name']} from {board['title']}.")
    else:
        flash("That place isn't on this board.")
    return redirect(f"/boards/{board_id}")


# Onboarding: taste questions, shown once after signup and from "Preferences" later
@app.route("/onboarding", methods=["GET", "POST"])
def onboarding():
    if "user_id" not in session:
        return redirect("/login")
    user_id = session["user_id"]
    pairs = onboarding_pairs()

    if request.method == "POST":
        # This-or-that: one radio group per pair, named pair_<pair_key>. Blank means skipped.
        answers = {}
        for pair in pairs:
            answer = request.form.get("pair_" + pair["pair_key"], "")
            if answer in VALID_ANSWERS:
                answers[pair["pair_key"]] = answer

        # Interests: one radio group per bucket, named interest_<bucket>
        interests = {}
        for bucket in BUCKETS:
            feeling = request.form.get("interest_" + bucket, "")
            if feeling in ("like", "dislike"):
                interests[bucket] = feeling
        likes = [b for b in BUCKETS if interests.get(b) == "like"]
        dislikes = [b for b in BUCKETS if interests.get(b) == "dislike"]

        free_text = request.form.get("free_text", "").strip()
        editing = request.form.get("editing") == "1"

        if len(likes) > MAX_LIKES:
            flash(f"Pick up to {MAX_LIKES} favorites.")
            return render_onboarding(pairs, answers, interests, free_text, editing, "step-interests")

        save_onboarding(user_id, free_text or None, answers, likes, dislikes)
        flash("Your travel preferences are saved.")
        return redirect("/profile")

    answers, interests, free_text = select_user_onboarding(user_id)
    editing = bool(answers or interests or free_text)
    return render_onboarding(pairs, answers, interests, free_text, editing)

# Trip vibe: set after a board is created, or changed later from the board page
@app.route("/boards/<int:board_id>/vibe", methods=["GET", "POST"])
def trip_vibe(board_id):
    board, error = require_board(board_id, "edit")
    if error:
        return error

    # After creating a board, continue to adding places; otherwise back to the board
    next_page = request.values.get("next", "")
    done_url = f"/boards/{board_id}/places" if next_page == "places" else f"/boards/{board_id}"

    if request.method == "POST":
        focus = [b for b in request.form.getlist("focus") if b in BUCKETS]
        vibe = request.form.get("vibe", "mix")
        if vibe not in VALID_VIBES:
            vibe = "mix"

        if len(focus) > MAX_FOCUS:
            flash(f"Pick up to {MAX_FOCUS} things this trip is about.")
            return render_template("trip_vibe.html", board=board, buckets=BUCKET_LABELS,
                                   vibe_options=VIBE_OPTIONS, focus=focus, vibe=vibe,
                                   next_page=next_page, done_url=done_url, max_focus=MAX_FOCUS)

        # The city is the board's destination
        save_trip_vibe(board_id, board["destination"], focus, vibe)
        flash("Trip vibe saved.")
        return redirect(done_url)

    saved = select_trip_vibe(board_id)
    if saved:
        focus, vibe = saved["focus"], saved["vibe"]
    else:
        # First time: start with the user's favorite buckets from onboarding
        answers, interests, free_text = select_user_onboarding(session["user_id"])
        focus = [b for b in BUCKETS if interests.get(b) == "like"][:MAX_FOCUS]
        vibe = "mix"

    return render_template("trip_vibe.html", board=board, buckets=BUCKET_LABELS,
                           vibe_options=VIBE_OPTIONS, focus=focus, vibe=vibe,
                           next_page=next_page, done_url=done_url, max_focus=MAX_FOCUS)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5027, debug=True)
