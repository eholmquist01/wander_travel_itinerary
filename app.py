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
                    can_view_board, can_edit_board, is_board_owner, remove_collaborator)
                    #if we're gonna add invites we also need to make sure create_invite, get_pending_invite, get_invite, and delete_invite are created.

app = Flask(__name__)
app.secret_key = "wander-session-key"

# Image upload settings
UPLOAD_DIR = os.path.join(app.root_path, "static", "uploads")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # 5 MB
os.makedirs(UPLOAD_DIR, exist_ok=True)

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

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5027, debug=True)
