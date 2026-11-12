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
        "SELECT Markers.business_id, Markers.name, Markers.address, Markers.city, Markers.stars "
        "FROM Markers "
        "WHERE Markers.city = %s "
        "ORDER BY Markers.stars DESC "
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
def get_boards_by_user(user_id):
    return query(
        "SELECT Boards.board_id, Boards.title, Boards.destination, Boards.time_created "
        "FROM Boards "
        "JOIN Users_Create ON Users_Create.board_id = Boards.board_id "
        "WHERE Users_Create.user_id = %s "
        "ORDER BY Boards.title",
        (user_id,)
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

