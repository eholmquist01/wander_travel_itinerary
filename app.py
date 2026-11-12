from flask import Flask, send_from_directory, render_template, flash, redirect, request, session
import pymysql
import pymysql.cursors
from wander_travel_itinerary.queries import (get_db, select_marker_by_location, select_top_markers, get_cities, get_boards_by_user,
                    get_board, create_board, update_board_name, delete_board)

app = Flask(__name__)
app.secret_key = "wander-session-key"

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
    my_boards = get_boards_by_user(session["user_id"])  
    return render_template("board_profile.html", name=session["name"], boards=my_boards) 

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
        return redirect(f"/boards/{board_id}")
    return render_template("board_form.html", cities=get_cities())

# View Board Details
@app.route("/boards/<int:board_id>")
def board_details(board_id):
    if "user_id" not in session:
        return redirect("/login")
    
    board = get_board(board_id)
    if board is None:
        flash("board doesn't exist.")
        return redirect("/profile")
    markers = select_marker_by_location(board["destination"], 50)
    return render_template("board_details.html", board=board, markers=markers)

# Rename Board
@app.route("/boards/<int:board_id>/rename", methods=["POST"])
def rename_board(board_id):
    if "user_id" not in session:
        return redirect("/login")
    
    renamed_title = request.form["title"].strip()
    if renamed_title and update_board_name(renamed_title, board_id, session["user_id"]):
        flash("Board renamed")
    else:
        flash("Couldn't rename that board")
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

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5027, debug=True)
