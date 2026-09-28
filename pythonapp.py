from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash
)

import mysql.connector
from mysql.connector import Error
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

import os
import re
import qrcode
import hashlib
import json

from blockchain import Blockchain


app = Flask(__name__)


# =========================================================
# CONFIGURATION
# =========================================================

app.config["SECRET_KEY"] = os.getenv(
    "SECRET_KEY",
    "change_this_secret_key"
)


# MySQL SERVER configuration
# Notice: NO database is specified here.
# This connection is used only to create the database.
MYSQL_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", "")
}


# Application database
DB_NAME = os.getenv("DB_NAME", "blockpay")


# =========================================================
# CUSTOM SHA-256 BLOCKCHAIN
# =========================================================

blockchain = Blockchain(difficulty=3)


# =========================================================
# CREATE DATABASE IF NOT EXISTS
# =========================================================

def create_database():
    """
    Connect to MySQL server without selecting a database,
    then create blockpay database if it does not exist.
    """

    connection = None
    cursor = None

    try:

        connection = mysql.connector.connect(
            host=MYSQL_CONFIG["host"],
            user=MYSQL_CONFIG["user"],
            password=MYSQL_CONFIG["password"]
        )

        if connection.is_connected():

            cursor = connection.cursor()

            cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}`"
            )

            connection.commit()

            print(
                f"Database '{DB_NAME}' created successfully "
                f"or already exists."
            )

    except Error as e:

        print("Database creation error:", e)

        raise

    finally:

        if cursor:
            cursor.close()

        if connection and connection.is_connected():
            connection.close()


# =========================================================
# DATABASE CONFIGURATION
# =========================================================

DB_CONFIG = {
    "host": MYSQL_CONFIG["host"],
    "user": MYSQL_CONFIG["user"],
    "password": MYSQL_CONFIG["password"],
    "database": DB_NAME
}


# =========================================================
# DATABASE CONNECTION
# =========================================================

def get_db_connection():

    return mysql.connector.connect(
        **DB_CONFIG
    )


# =========================================================
# INITIALIZE DATABASE TABLES
# =========================================================

def init_db():

    conn = None
    cursor = None

    try:

        conn = get_db_connection()

        cursor = conn.cursor()

        # =================================================
        # USERS TABLE
        # =================================================

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS users(

            id INT AUTO_INCREMENT PRIMARY KEY,

            fullname VARCHAR(100) NOT NULL,

            username VARCHAR(50) UNIQUE NOT NULL,

            mobile VARCHAR(15) UNIQUE NOT NULL,

            password VARCHAR(255) NOT NULL,

            upi_pin VARCHAR(255),

            balance DECIMAL(10,2) DEFAULT 1000.00,

            qr_code VARCHAR(255)

        )
        """)


        # =================================================
        # TRANSACTIONS TABLE
        # =================================================

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions(

            id INT AUTO_INCREMENT PRIMARY KEY,

            sender_id INT NOT NULL,

            receiver_id INT NOT NULL,

            amount DECIMAL(10,2) NOT NULL,

            transaction_time DATETIME DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY(sender_id)
                REFERENCES users(id)
                ON DELETE CASCADE,

            FOREIGN KEY(receiver_id)
                REFERENCES users(id)
                ON DELETE CASCADE

        )
        """)


        # =================================================
        # BLOCKCHAIN TABLE
        # =================================================

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS blockchain_blocks(

            id INT AUTO_INCREMENT PRIMARY KEY,

            block_index INT NOT NULL UNIQUE,

            transaction_id INT NULL,

            block_timestamp DATETIME NOT NULL,

            block_data JSON NOT NULL,

            previous_hash VARCHAR(64) NOT NULL,

            nonce BIGINT NOT NULL,

            block_hash VARCHAR(64) NOT NULL UNIQUE

        )
        """)


        # =================================================
        # GENESIS BLOCK
        # =================================================

        cursor.execute("""
            SELECT id
            FROM blockchain_blocks
            WHERE block_index = 0
        """)

        genesis_exists = cursor.fetchone()


        if genesis_exists is None:

            genesis_data = {
                "message": "Food Bridge Genesis Block"
            }

            genesis_data_json = json.dumps(
                genesis_data,
                sort_keys=True
            )

            genesis_time = datetime.now()

            genesis_hash_data = (
                "0"
                + genesis_time.isoformat()
                + genesis_data_json
                + "0"
                + "0"
            )

            genesis_hash = hashlib.sha256(
                genesis_hash_data.encode()
            ).hexdigest()


            cursor.execute("""
                INSERT INTO blockchain_blocks
                (
                    block_index,
                    transaction_id,
                    block_timestamp,
                    block_data,
                    previous_hash,
                    nonce,
                    block_hash
                )
                VALUES
                (
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s
                )
            """, (
                0,
                None,
                genesis_time,
                genesis_data_json,
                "0",
                0,
                genesis_hash
            ))


        conn.commit()

        print("Database tables initialized successfully.")

    except Error as e:

        if conn:
            conn.rollback()

        print("Database initialization error:", e)

        raise

    finally:

        if cursor:
            cursor.close()

        if conn:
            conn.close()


# =========================================================
# CREATE DATABASE FIRST
# THEN CREATE TABLES
# =========================================================

create_database()

init_db()


# =========================================================
# HOME
# =========================================================

@app.route("/")
def home():

    return render_template(
        "base1.html"
    )


@app.route("/go_to_index")
def index():

    return render_template(
        "index.html"
    )


# =========================================================
# LOGIN
# =========================================================

@app.route(
    "/login",
    methods=["POST"]
)
def login():

    username = request.form.get(
        "username",
        ""
    ).strip().lower()

    password = request.form.get(
        "password",
        ""
    )


    conn = None
    cursor = None

    try:

        conn = get_db_connection()

        cursor = conn.cursor(
            dictionary=True
        )


        cursor.execute(
            """
            SELECT *
            FROM users
            WHERE username=%s
            """,
            (username,)
        )


        user = cursor.fetchone()


        if not user:

            flash("User not found.")

            return redirect(
                url_for("index")
            )


        if not check_password_hash(
            user["password"],
            password
        ):

            flash("Incorrect password.")

            return redirect(
                url_for("index")
            )


        session["user_id"] = user["id"]

        session["fullname"] = user["fullname"]


        return redirect(
            url_for("dashboard")
        )


    finally:

        if cursor:
            cursor.close()

        if conn:
            conn.close()


# =========================================================
# DASHBOARD
# =========================================================

@app.route("/dashboard")
def dashboard():

    if "user_id" not in session:

        return redirect(
            url_for("index")
        )


    conn = get_db_connection()

    cursor = conn.cursor(
        dictionary=True
    )


    # Get logged-in user

    cursor.execute(
        """
        SELECT *
        FROM users
        WHERE id=%s
        """,
        (session["user_id"],)
    )


    user = cursor.fetchone()


    # Get recent transactions

    cursor.execute("""
        SELECT

            t.amount,

            t.transaction_time,

            s.username AS sender,

            r.username AS receiver

        FROM transactions t

        JOIN users s
            ON t.sender_id = s.id

        JOIN users r
            ON t.receiver_id = r.id

        WHERE
            t.sender_id=%s
            OR
            t.receiver_id=%s

        ORDER BY
            t.transaction_time DESC

    """, (
        session["user_id"],
        session["user_id"]
    ))


    transactions = cursor.fetchall()


    cursor.close()

    conn.close()


    return render_template(

        "dashboard.html",

        fullname=user["fullname"],

        username=user["username"],

        mobile=user["mobile"],

        balance=user["balance"],

        qr=user["qr_code"],

        transactions=transactions,

        user=user

    )


# =========================================================
# LOGOUT
# =========================================================

@app.route("/logout")
def logout():

    session.clear()

    flash(
        "Logged out successfully."
    )

    return redirect(
        url_for("home")
    )


# =========================================================
# REGISTER USER
# =========================================================

@app.route(
    "/register",
    methods=["POST"]
)
def register():

    fullname = request.form[
        "fullname"
    ].strip()

    username = request.form[
        "username"
    ].strip().lower()

    mobile = request.form[
        "mobile"
    ].strip()

    password = request.form[
        "password"
    ]

    confirm_password = request.form[
        "confirm_password"
    ]

    upi_pin = request.form[
        "upi_pin"
    ].strip()

    confirm_upi_pin = request.form[
        "confirm_upi_pin"
    ].strip()


    # =====================================================
    # VALIDATION
    # =====================================================

    if password != confirm_password:

        flash(
            "Passwords do not match."
        )

        return redirect(
            url_for("index")
        )


    if len(password) < 6:

        flash(
            "Password must contain at least 6 characters."
        )

        return redirect(
            url_for("index")
        )


    if not re.fullmatch(
        r"\d{4,6}",
        upi_pin
    ):

        flash(
            "UPI PIN must contain 4 or 6 digits."
        )

        return redirect(
            url_for("index")
        )


    if upi_pin != confirm_upi_pin:

        flash(
            "UPI PINs do not match."
        )

        return redirect(
            url_for("index")
        )


    conn = get_db_connection()

    cursor = conn.cursor(
        dictionary=True
    )


    # =====================================================
    # CHECK USERNAME
    # =====================================================

    cursor.execute(
        """
        SELECT id
        FROM users
        WHERE username=%s
        """,
        (username,)
    )


    if cursor.fetchone():

        flash(
            "Username already exists."
        )

        cursor.close()

        conn.close()

        return redirect(
            url_for("index")
        )


    # =====================================================
    # CHECK MOBILE
    # =====================================================

    cursor.execute(
        """
        SELECT id
        FROM users
        WHERE mobile=%s
        """,
        (mobile,)
    )


    if cursor.fetchone():

        flash(
            "Mobile number already registered."
        )

        cursor.close()

        conn.close()

        return redirect(
            url_for("index")
        )


    # =====================================================
    # HASH PASSWORD
    # =====================================================

    hashed_password = generate_password_hash(
        password
    )

    hashed_upi_pin = generate_password_hash(
        upi_pin
    )


    # =====================================================
    # CREATE QR FOLDER
    # =====================================================

    os.makedirs(
        "static/qr",
        exist_ok=True
    )


    filename = (
        username.replace("@", "")
        + ".png"
    )


    img = qrcode.make(
        username
    )


    img.save(
        os.path.join(
            "static",
            "qr",
            filename
        )
    )


    qr_path = (
        "qr/"
        + filename
    )


    # =====================================================
    # INSERT USER
    # =====================================================

    cursor.execute("""
        INSERT INTO users
        (
            fullname,
            username,
            mobile,
            password,
            upi_pin,
            balance,
            qr_code
        )
        VALUES
        (
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s
        )

    """, (
        fullname,
        username,
        mobile,
        hashed_password,
        hashed_upi_pin,
        1000.00,
        qr_path
    ))


    conn.commit()


    cursor.close()

    conn.close()


    flash(
        "Registration Successful."
    )


    return redirect(
        url_for("index")
    )


# =========================================================
# PROFILE
# =========================================================

@app.route("/profile")
def profile():

    if "user_id" not in session:

        return redirect(
            url_for("index")
        )


    conn = get_db_connection()

    cursor = conn.cursor(
        dictionary=True
    )


    cursor.execute("""
        SELECT

            fullname,

            username,

            mobile,

            balance

        FROM users

        WHERE id=%s

    """, (
        session["user_id"],
    ))


    user = cursor.fetchone()


    cursor.close()

    conn.close()


    return render_template(
        "profile.html",
        user=user
    )


# =========================================================
# SEND MONEY PAGE
# =========================================================

@app.route("/send")
def send_page():

    if "user_id" not in session:

        return redirect(
            url_for("index")
        )


    return render_template(
        "send_money.html"
    )


# =========================================================
# SEND MONEY + BLOCKCHAIN
# =========================================================

@app.route(
    "/send_money",
    methods=["POST"]
)
def send_money():

    if "user_id" not in session:

        return redirect(
            url_for("index")
        )


    receiver_username = request.form[
        "receiver"
    ].strip().lower()

    upi_pin = request.form[
        "upi_pin"
    ]

    amount = request.form[
        "amount"
    ].strip()


    # =====================================================
    # VALIDATE AMOUNT
    # =====================================================

    try:

        amount = float(amount)


        if amount <= 0:

            flash(
                "Please enter a valid amount."
            )

            return redirect(
                url_for("send_page")
            )


    except ValueError:

        flash(
            "Invalid amount."
        )

        return redirect(
            url_for("send_page")
        )


    conn = get_db_connection()

    cursor = conn.cursor(
        dictionary=True
    )


    try:

        # =================================================
        # GET SENDER
        # =================================================

        cursor.execute(
            """
            SELECT *
            FROM users
            WHERE id=%s
            """,
            (session["user_id"],)
        )


        sender = cursor.fetchone()


        if sender is None:

            flash(
                "User not found."
            )

            return redirect(
                url_for("index")
            )


        # =================================================
        # VERIFY UPI PIN
        # =================================================

        if not check_password_hash(
            sender["upi_pin"],
            upi_pin
        ):

            flash(
                "Incorrect UPI PIN."
            )

            return redirect(
                url_for("send_page")
            )


        # =================================================
        # GET RECEIVER
        # =================================================

        cursor.execute(
            """
            SELECT *
            FROM users
            WHERE username=%s
            """,
            (receiver_username,)
        )


        receiver = cursor.fetchone()


        if receiver is None:

            flash(
                "Receiver username not found."
            )

            return redirect(
                url_for("send_page")
            )


        # =================================================
        # PREVENT SELF TRANSFER
        # =================================================

        if sender["id"] == receiver["id"]:

            flash(
                "You cannot send money to yourself."
            )

            return redirect(
                url_for("send_page")
            )


        # =================================================
        # CHECK BALANCE
        # =================================================

        if float(sender["balance"]) < amount:

            flash(
                "Insufficient wallet balance."
            )

            return redirect(
                url_for("send_page")
            )


        # =================================================
        # UPDATE BALANCES
        # =================================================

        sender_balance = (
            float(sender["balance"])
            - amount
        )

        receiver_balance = (
            float(receiver["balance"])
            + amount
        )


        cursor.execute(
            """
            UPDATE users

            SET balance=%s

            WHERE id=%s
            """,
            (
                sender_balance,
                sender["id"]
            )
        )


        cursor.execute(
            """
            UPDATE users

            SET balance=%s

            WHERE id=%s
            """,
            (
                receiver_balance,
                receiver["id"]
            )
        )


        # =================================================
        # SAVE TRANSACTION
        # =================================================

        cursor.execute("""
            INSERT INTO transactions
            (
                sender_id,
                receiver_id,
                amount,
                transaction_time
            )
            VALUES
            (
                %s,
                %s,
                %s,
                %s
            )

        """, (
            sender["id"],
            receiver["id"],
            amount,
            datetime.now()
        ))


        transaction_id = cursor.lastrowid


        # =================================================
        # GET PREVIOUS BLOCK
        # =================================================

        cursor.execute("""
            SELECT

                block_index,

                block_hash

            FROM blockchain_blocks

            ORDER BY block_index DESC

            LIMIT 1

        """)


        previous_block = cursor.fetchone()


        if previous_block is None:

            raise Exception(
                "Genesis block not found."
            )


        previous_index = (
            previous_block[
                "block_index"
            ]
        )


        previous_hash = (
            previous_block[
                "block_hash"
            ]
        )


        # =================================================
        # BLOCK DATA
        # =================================================

        block_data = {

            "transaction_id":
                transaction_id,

            "sender_id":
                sender["id"],

            "sender":
                sender["username"],

            "receiver_id":
                receiver["id"],

            "receiver":
                receiver["username"],

            "amount":
                round(amount, 2),

            "transaction_time":
                datetime.now().isoformat(),

            "type":
                "money_transfer"

        }


        # =================================================
        # CREATE AND MINE BLOCK
        # =================================================

        new_block = blockchain.create_block(

            previous_index + 1,

            block_data,

            previous_hash

        )


        # =================================================
        # SAVE BLOCK TO MYSQL
        # =================================================

        cursor.execute("""
            INSERT INTO blockchain_blocks
            (
                block_index,
                transaction_id,
                block_timestamp,
                block_data,
                previous_hash,
                nonce,
                block_hash
            )
            VALUES
            (
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s
            )

        """, (

            new_block.index,

            transaction_id,

            datetime.fromisoformat(
                new_block.timestamp
            ),

            json.dumps(
                block_data
            ),

            new_block.previous_hash,

            new_block.nonce,

            new_block.hash

        ))


        # =================================================
        # COMMIT EVERYTHING
        # =================================================

        conn.commit()


        flash(
            f"₹{amount:.2f} sent successfully "
            f"to {receiver['username']}."
        )


    except Exception as e:

        conn.rollback()

        flash(
            "Transaction failed."
        )

        print(
            "Transaction error:",
            e
        )


    finally:

        cursor.close()

        conn.close()


    return redirect(
        url_for("dashboard")
    )


# =========================================================
# TRANSACTION HISTORY
# =========================================================

@app.route("/history")
def history():

    if "user_id" not in session:

        return redirect(
            url_for("index")
        )


    conn = get_db_connection()

    cursor = conn.cursor(
        dictionary=True
    )


    cursor.execute(
        """
        SELECT *
        FROM users
        WHERE id=%s
        """,
        (session["user_id"],)
    )


    user = cursor.fetchone()


    cursor.execute("""
        SELECT

            t.amount,

            t.transaction_time,

            s.username AS sender,

            r.username AS receiver

        FROM transactions t

        JOIN users s
            ON t.sender_id = s.id

        JOIN users r
            ON t.receiver_id = r.id

        WHERE
            t.sender_id=%s
            OR
            t.receiver_id=%s

        ORDER BY
            t.transaction_time DESC

    """, (
        session["user_id"],
        session["user_id"]
    ))


    transactions = cursor.fetchall()


    cursor.close()

    conn.close()


    return render_template(

        "history.html",

        transactions=transactions,

        user=user

    )


# =========================================================
# ADD MONEY PAGE
# =========================================================

@app.route("/add_money")
def add_money_page():

    if "user_id" not in session:

        return redirect(
            url_for("index")
        )


    return render_template(
        "add_money.html"
    )


# =========================================================
# ADD MONEY
# =========================================================

@app.route(
    "/add_money",
    methods=["POST"]
)
def add_money():

    if "user_id" not in session:

        return redirect(
            url_for("index")
        )


    try:

        amount = float(
            request.form["amount"]
        )

        if amount <= 0:

            flash(
                "Please enter a valid amount."
            )

            return redirect(
                url_for("add_money_page")
            )


    except ValueError:

        flash(
            "Invalid amount."
        )

        return redirect(
            url_for("add_money_page")
        )


    conn = get_db_connection()

    cursor = conn.cursor()


    try:

        cursor.execute(
            """
            UPDATE users

            SET balance =
                balance + %s

            WHERE id=%s
            """,
            (
                amount,
                session["user_id"]
            )
        )


        conn.commit()


        flash(
            "Money Added Successfully"
        )


    except Exception as e:

        conn.rollback()

        print(
            "Add money error:",
            e
        )

        flash(
            "Unable to add money."
        )


    finally:

        cursor.close()

        conn.close()


    return redirect(
        url_for("dashboard")
    )


# =========================================================
# VIEW BLOCKCHAIN
# =========================================================

@app.route("/blockchain")
def view_blockchain():

    if "user_id" not in session:

        return redirect(
            url_for("index")
        )


    conn = get_db_connection()

    cursor = conn.cursor(
        dictionary=True
    )


    try:

        cursor.execute("""
            SELECT

                block_index,

                transaction_id,

                block_timestamp,

                block_data,

                previous_hash,

                nonce,

                block_hash

            FROM blockchain_blocks

            ORDER BY block_index ASC

        """)


        blocks = cursor.fetchall()


        for block in blocks:

            if isinstance(
                block["block_data"],
                str
            ):

                try:

                    block["block_data"] = json.loads(
                        block["block_data"]
                    )

                except json.JSONDecodeError:

                    pass


        return render_template(
            "blockchain.html",
            blocks=blocks
        )


    finally:

        cursor.close()

        conn.close()


# =========================================================
# VALIDATE BLOCKCHAIN
# =========================================================

@app.route("/validate_blockchain")
def validate_blockchain():

    if "user_id" not in session:

        return redirect(
            url_for("index")
        )


    conn = get_db_connection()

    cursor = conn.cursor(
        dictionary=True
    )


    try:

        cursor.execute("""
            SELECT

                block_index,

                block_timestamp,

                block_data,

                previous_hash,

                nonce,

                block_hash

            FROM blockchain_blocks

            ORDER BY block_index ASC

        """)


        blocks = cursor.fetchall()


        valid = True

        reason = "Blockchain is valid."


        # =================================================
        # CHECK EVERY BLOCK
        # =================================================

        for i, current in enumerate(
            blocks
        ):

            data = current[
                "block_data"
            ]


            if isinstance(
                data,
                str
            ):

                data = json.loads(
                    data
                )


            timestamp = (
                current[
                    "block_timestamp"
                ].isoformat()
            )


            calculated_hash = hashlib.sha256(

                (
                    str(
                        current[
                            "block_index"
                        ]
                    )

                    + timestamp

                    + json.dumps(
                        data,
                        sort_keys=True
                    )

                    + current[
                        "previous_hash"
                    ]

                    + str(
                        current[
                            "nonce"
                        ]
                    )
                ).encode()

            ).hexdigest()


            # =============================================
            # CHECK HASH
            # =============================================

            if calculated_hash != current[
                "block_hash"
            ]:

                valid = False

                reason = (
                    f"Block "
                    f"{current['block_index']} "
                    f"has been modified."
                )

                break


            # =============================================
            # CHECK PREVIOUS HASH
            # =============================================

            if i > 0:

                previous = blocks[i - 1]


                if current[
                    "previous_hash"
                ] != previous[
                    "block_hash"
                ]:

                    valid = False

                    reason = (
                        f"Block "
                        f"{current['block_index']} "
                        f"is not linked correctly."
                    )

                    break


        return {

            "blockchain_valid":
                valid,

            "message":
                reason,

            "total_blocks":
                len(blocks)

        }


    finally:

        cursor.close()

        conn.close()


# =========================================================
# RUN APPLICATION
# =========================================================

print(app.url_map)


if __name__ == "__main__":

    app.run(
        host="127.0.0.1",
        port=5000,
        debug=False
    )