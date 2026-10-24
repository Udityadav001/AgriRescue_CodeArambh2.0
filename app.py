from pathlib import Path
from dotenv import load_dotenv
import os
import hmac

BASE_DIR = Path(__file__).resolve().parent

# Load .env before reading credentials
load_dotenv(BASE_DIR / ".env", override=True)

# Load admin credentials
ADMIN_PHONE = os.getenv("AGRI_ADMIN_PHONE")
ADMIN_PASSWORD = os.getenv("AGRI_ADMIN_PASSWORD")

print("Admin phone loaded:", bool(ADMIN_PHONE))
print("Admin password loaded:", bool(ADMIN_PASSWORD))
import uuid
import math
import requests
from dotenv import load_dotenv
from flask import Flask, request, jsonify, session, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from pathlib import Path
import sqlite3
import re
import os

load_dotenv()

CASHFREE_APP_ID = os.getenv("CASHFREE_APP_ID")
CASHFREE_SECRET_KEY = os.getenv("CASHFREE_SECRET_KEY")
CASHFREE_ENV = os.getenv("CASHFREE_ENV", "sandbox").lower()

if CASHFREE_ENV == "sandbox":
    CASHFREE_BASE_URL = "https://sandbox.cashfree.com/pg"
elif CASHFREE_ENV == "production":
    CASHFREE_BASE_URL = "https://api.cashfree.com/pg"
else:
    raise ValueError("CASHFREE_ENV must be sandbox or production")


app = Flask(__name__)

BASE_DIR = Path(__file__).resolve().parent
DATABASE = BASE_DIR / "agri_rescue.db"

app.secret_key = os.environ.get(
    "AGRI_RESCUE_SECRET_KEY",
    "development-key-change-before-deployment"
)


BASE_DIR = Path(__file__).resolve().parent
DATABASE = BASE_DIR / "agri_rescue.db"


# ---------------- DATABASE ----------------

def connect_db():
    conn = sqlite3.connect(DATABASE, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def create_tables():
    conn = connect_db()

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('farmer','buyer')),
            address TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            farmer_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            price REAL NOT NULL CHECK(price >= 0),
            quantity INTEGER NOT NULL CHECK(quantity >= 0),
            location TEXT NOT NULL,
            FOREIGN KEY(farmer_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            buyer_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL CHECK(quantity > 0),
            total REAL NOT NULL,
            address TEXT NOT NULL,
            status TEXT DEFAULT 'Placed',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(buyer_id) REFERENCES users(id),
            FOREIGN KEY(product_id) REFERENCES products(id)
        );
        
CREATE TABLE IF NOT EXISTS payment_attempts (
    cashfree_order_id TEXT PRIMARY KEY,
    buyer_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL,
    total REAL NOT NULL,
    address TEXT NOT NULL,
    payment_session_id TEXT NOT NULL,
    status TEXT DEFAULT 'PENDING',
    order_id INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

    """)

    conn.commit()
    conn.close()


def login_required(role=None):
    def decorator(function):
        from functools import wraps

        @wraps(function)
        def wrapper(*args, **kwargs):
            if not session.get("user_id"):
                return jsonify({"error": "Please log in first."}), 401

            if role and session.get("role") != role:
                return jsonify({"error": f"{role.title()} account required."}), 403

            return function(*args, **kwargs)

        return wrapper
    return decorator


# ---------------- HOME ----------------

@app.route("/")
def home():
    return send_from_directory(BASE_DIR, "index.html")


@app.route("/style.css")
def css():
    return send_from_directory(BASE_DIR, "style.css")


@app.route("/script.js")
def js():
    return send_from_directory(BASE_DIR, "script.js")

# Admin page files
@app.route("/admin")
def admin_page():
    return send_from_directory(BASE_DIR, "admin.html")

@app.route("/admin.css")
def admin_css():
    return send_from_directory(BASE_DIR, "admin.css")

@app.route("/admin.js")
def admin_js():
    return send_from_directory(BASE_DIR, "admin.js")



@app.route("/api/health")
def health():
    return jsonify({
        "message": "Agri-Rescue backend is running!"
    })


# ---------------- REGISTER ----------------

@app.route("/api/register", methods=["POST"])
def register():
    data = request.get_json(silent=True) or {}

    name = str(data.get("name", "")).strip()
    phone = str(data.get("phone", "")).strip()
    password = str(data.get("password", ""))
    role = str(data.get("role", "")).lower().strip()
    address = str(data.get("address", "")).strip()

    if len(name) < 2:
        return jsonify({"error": "Enter your name."}), 400

    if not re.fullmatch(r"[6-9]\d{9}", phone):
        return jsonify({"error": "Enter a valid Indian mobile number."}), 400

    if len(password) < 8:
        return jsonify({"error": "Password must have at least 8 characters."}), 400

    if role not in ("farmer", "buyer"):
        return jsonify({"error": "Select farmer or buyer."}), 400

    conn = connect_db()

    try:
        cursor = conn.execute("""
            INSERT INTO users (name, phone, password, role, address)
            VALUES (?, ?, ?, ?, ?)
        """, (
            name,
            phone,
            generate_password_hash(password),
            role,
            address
        ))

        conn.commit()

        session.clear()
        session["user_id"] = cursor.lastrowid
        session["role"] = role

        return jsonify({
            "message": "Registration successful!",
            "user": {
                "id": cursor.lastrowid,
                "name": name,
                "phone": phone,
                "role": role
            }
        }), 201

    except sqlite3.IntegrityError:
        return jsonify({"error": "This phone number is already registered."}), 409

    finally:
        conn.close()


# ---------------- LOGIN ----------------

@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}

    phone = str(data.get("phone", "")).strip()
    password = str(data.get("password", ""))

    conn = connect_db()

    user = conn.execute(
        "SELECT * FROM users WHERE phone = ?",
        (phone,)
    ).fetchone()

    conn.close()

    if not user or not check_password_hash(user["password"], password):
        return jsonify({"error": "Invalid phone number or password."}), 401

    session.clear()
    session["user_id"] = user["id"]
    session["role"] = user["role"]

    return jsonify({
        "message": "Login successful!",
        "user": {
            "id": user["id"],
            "name": user["name"],
            "phone": user["phone"],
            "role": user["role"]
        }
    })


# ---------------- LOGOUT ----------------

@app.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"message": "Logged out successfully."})


# ---------------- VIEW PRODUCTS ----------------

@app.route("/api/products", methods=["GET"])
def get_products():
    search = request.args.get("search", "").strip()
    location = request.args.get("location", "").strip()

    conn = connect_db()

    products = conn.execute("""
        SELECT products.*, users.name AS farmer_name
        FROM products
        JOIN users ON users.id = products.farmer_id
        WHERE products.quantity > 0
          AND products.name LIKE ?
          AND products.location LIKE ?
        ORDER BY products.id DESC
    """, (f"%{search}%", f"%{location}%")).fetchall()

    conn.close()

    return jsonify([dict(product) for product in products])


# ---------------- ADD PRODUCT ----------------

@app.route("/api/products", methods=["POST"])
@login_required("farmer")
def add_product():
    data = request.get_json(silent=True) or {}

    name = str(data.get("name", "")).strip()
    location = str(data.get("location", "")).strip()

    try:
        price = float(data.get("price"))
        quantity = float(data.get("quantity"))

        if not math.isfinite(price) or not math.isfinite(quantity):
            raise ValueError("Invalid number")

    except (TypeError, ValueError):
        return jsonify({
            "error": "Enter a valid price and quantity."
        }), 400

    if not name or not location:
        return jsonify({
            "error": "Enter product name and location."
        }), 400

    if price <= 0 or quantity <= 0:
        return jsonify({
            "error": "Price and quantity must be greater than zero."
        }), 400

    # Yahan apna existing database insert wala code rakho.

    conn = connect_db()

    cursor = conn.execute("""
        INSERT INTO products (farmer_id, name, price, quantity, location)
        VALUES (?, ?, ?, ?, ?)
    """, (
        session["user_id"],
        name,
        price,
        quantity,
        location
    ))

    conn.commit()
    product_id = cursor.lastrowid
    conn.close()

    return jsonify({
        "message": "Product added successfully!",
        "product_id": product_id
    }), 201


# ---------------- FARMER'S PRODUCTS ----------------

@app.route("/api/my-products")
@login_required("farmer")
def my_products():
    conn = connect_db()

    products = conn.execute("""
        SELECT * FROM products
        WHERE farmer_id = ?
        ORDER BY id DESC
    """, (session["user_id"],)).fetchall()

    conn.close()

    return jsonify([dict(product) for product in products])


# ---------------- DELETE PRODUCT ----------------

@app.route("/api/products/<int:product_id>", methods=["DELETE"])
@login_required("farmer")
def delete_product(product_id):
    conn = connect_db()

    product = conn.execute("""
        SELECT id FROM products
        WHERE id = ? AND farmer_id = ?
    """, (product_id, session["user_id"])).fetchone()

    if not product:
        conn.close()
        return jsonify({"error": "Product not found in your listings."}), 404

    # Preserve product records referenced by previous orders.
    order = conn.execute(
        "SELECT id FROM orders WHERE product_id = ? LIMIT 1",
        (product_id,)
    ).fetchone()

    if order:
        conn.execute(
            "UPDATE products SET quantity = 0 WHERE id = ?",
            (product_id,)
        )
        message = "Listing closed; order history preserved."
    else:
        conn.execute(
            "DELETE FROM products WHERE id = ?",
            (product_id,)
        )
        message = "Product deleted successfully."

    conn.commit()
    conn.close()

    return jsonify({"message": message})


# ---------------- BUY PRODUCT ----------------

'''@app.route("/api/orders", methods=["POST"])
@login_required("buyer")
def buy_product():
    data = request.get_json(silent=True) or {}

    try:
        product_id = int(data.get("product_id"))
        quantity = int(data.get("quantity"))
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid product or quantity."}), 400

    address = str(data.get("address", "")).strip()

    if quantity <= 0 or len(address) < 5:
        return jsonify({"error": "Enter a valid quantity and address."}), 400

    conn = connect_db()

    try:
        # Lock the write transaction so stock cannot be oversold.
        conn.execute("BEGIN IMMEDIATE")

        product = conn.execute(
            "SELECT * FROM products WHERE id = ?",
            (product_id,)
        ).fetchone()

        if not product:
            conn.rollback()
            return jsonify({"error": "Product not found."}), 404

        if product["farmer_id"] == session["user_id"]:
            conn.rollback()
            return jsonify({"error": "You cannot buy your own product."}), 400

        if product["quantity"] < quantity:
            conn.rollback()
            return jsonify({"error": "Insufficient stock."}), 409

        total = round(product["price"] * quantity, 2)

        conn.execute("""
            UPDATE products
            SET quantity = quantity - ?
            WHERE id = ?
        """, (quantity, product_id))

        cursor = conn.execute("""
            INSERT INTO orders
            (buyer_id, product_id, quantity, total, address)
            VALUES (?, ?, ?, ?, ?)
        """, (
            session["user_id"],
            product_id,
            quantity,
            total,
            address
        ))

        order_id = cursor.lastrowid
        conn.commit()

        return jsonify({
            "message": "Order placed successfully!",
            "order_id": order_id,
            "total": total
        }), 201

    except sqlite3.Error:
        conn.rollback()
        app.logger.exception("Order processing failed")
        return jsonify({"error": "Unable to place order."}), 500

    finally:
        conn.close()'''
        
@app.route("/api/payments/create", methods=["POST"])
@login_required("buyer")
def create_cashfree_payment():
    if not CASHFREE_APP_ID or not CASHFREE_SECRET_KEY:
        return jsonify({
            "error": "Cashfree sandbox credentials are missing in .env"
        }), 503

    data = request.get_json(silent=True) or {}

    try:
        product_id = int(data.get("product_id"))
        quantity = float(data.get("quantity"))

        if not math.isfinite(quantity):
            raise ValueError("Invalid quantity")

    except (TypeError, ValueError):
        return jsonify({
            "error": "Invalid product or quantity."
        }), 400

    address = str(data.get("address", "")).strip()

    if product_id <= 0 or quantity <= 0 or len(address) < 5:
        return jsonify({
            "error": "Enter a valid product, quantity and address."
        }), 400

    # Iske neeche apna existing Cashfree payment code rakho.
    conn = connect_db()

    try:
        product = conn.execute(
            "SELECT * FROM products WHERE id = ?",
            (product_id,)
        ).fetchone()

        if not product:
            return jsonify({"error": "Product not found."}), 404

        if product["farmer_id"] == session["user_id"]:
            return jsonify({"error": "You cannot buy your own product."}), 400

        if product["quantity"] < quantity:
            return jsonify({"error": "Insufficient stock."}), 409

        buyer = conn.execute(
            "SELECT id, name, phone FROM users WHERE id = ?",
            (session["user_id"],)
        ).fetchone()

        total = round(float(product["price"]) * quantity, 2)
        cf_order_id = "AR" + uuid.uuid4().hex[:20]

        payload = {
            "order_id": cf_order_id,
            "order_amount": total,
            "order_currency": "INR",
            "customer_details": {
                "customer_id": f"buyer_{buyer['id']}",
                "customer_name": buyer["name"],
                "customer_phone": buyer["phone"]
            },
            "order_meta": {
                "return_url": (
                    request.host_url.rstrip("/")
                    + "/payment/return?order_id={order_id}"
                )
            }
        }

        response = requests.post(
            f"{CASHFREE_BASE_URL}/orders",
            headers={
                "x-client-id": CASHFREE_APP_ID,
                "x-client-secret": CASHFREE_SECRET_KEY,
                "x-api-version": "2025-01-01",
                "Content-Type": "application/json",
                "Accept": "application/json"
            },
            json=payload,
            timeout=20
        )

        if response.status_code not in (200, 201):
            app.logger.error(
                "Cashfree order creation failed: %s",
                response.text
            )
            return jsonify({
                "error": "Cashfree order creation failed. Check credentials."
            }), 502

        cf_data = response.json()
        payment_session_id = cf_data.get("payment_session_id")

        if not payment_session_id:
            return jsonify({
                "error": "Cashfree did not return a payment session."
            }), 502

        conn.execute("""
            INSERT INTO payment_attempts (
                cashfree_order_id, buyer_id, product_id,
                quantity, total, address, payment_session_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            cf_order_id, session["user_id"], product_id,
            quantity, total, address, payment_session_id
        ))

        conn.commit()

        return jsonify({
            "order_id": cf_order_id,
            "payment_session_id": payment_session_id,
            "total": total
        }), 201

    except requests.RequestException:
        app.logger.exception("Cashfree connection failed")
        return jsonify({"error": "Could not connect to Cashfree."}), 502

    except sqlite3.Error:
        conn.rollback()
        app.logger.exception("Payment attempt could not be saved")
        return jsonify({"error": "Could not save payment attempt."}), 500

    finally:
        conn.close()

'''@app.route("/api/payments/verify", methods=["POST"])
@login_required("buyer")
def verify_cashfree_payment():
    data = request.get_json(silent=True) or {}
    cf_order_id = str(data.get("order_id", "")).strip()

    if not cf_order_id:
        return jsonify({"error": "Missing Cashfree order ID."}), 400

    if not CASHFREE_APP_ID or not CASHFREE_SECRET_KEY:
        return jsonify({"error": "Cashfree credentials are missing."}), 503

    conn = connect_db()

    try:
        attempt = conn.execute("""
            SELECT * FROM payment_attempts
            WHERE cashfree_order_id = ? AND buyer_id = ?
        """, (cf_order_id, session["user_id"])).fetchone()

        if not attempt:
            return jsonify({"error": "Payment order not found."}), 404

        if attempt["status"] == "PAID" and attempt["order_id"]:
            return jsonify({
                "status": "PAID",
                "order_id": attempt["order_id"],
                "message": "Order already confirmed."
            })

        headers = {
            "x-client-id": CASHFREE_APP_ID,
            "x-client-secret": CASHFREE_SECRET_KEY,
            "x-api-version": "2025-01-01",
            "Accept": "application/json"
        }

        # Check the order status directly with Cashfree.
        order_response = requests.get(
            f"{CASHFREE_BASE_URL}/orders/{cf_order_id}",
            headers=headers,
            timeout=20
        )
        order_response.raise_for_status()
        cf_order = order_response.json()

        if (
            cf_order.get("order_status") != "PAID"
            or cf_order.get("order_currency") != "INR"
            or round(float(cf_order.get("order_amount", 0)), 2)
            != round(float(attempt["total"]), 2)
        ):
            return jsonify({
                "status": cf_order.get("order_status", "PENDING"),
                "message": "Payment is not confirmed yet."
            }), 202

        # Confirm that at least one transaction succeeded.
        payment_response = requests.get(
            f"{CASHFREE_BASE_URL}/orders/{cf_order_id}/payments",
            headers=headers,
            timeout=20
        )
        payment_response.raise_for_status()
        payments = payment_response.json()

        if not isinstance(payments, list) or not any(
            p.get("payment_status") == "SUCCESS" for p in payments
        ):
            return jsonify({
                "status": "PENDING",
                "message": "Successful payment transaction not found."
            }), 202

        # Start a write transaction before changing stock or orders.
        conn.execute("BEGIN IMMEDIATE")

        current = conn.execute("""
            SELECT * FROM payment_attempts
            WHERE cashfree_order_id = ?
        """, (cf_order_id,)).fetchone()

        if current["status"] == "PAID" and current["order_id"]:
            conn.commit()
            return jsonify({
                "status": "PAID",
                "order_id": current["order_id"],
                "message": "Order already confirmed."
            })

        product = conn.execute("""
            SELECT quantity FROM products WHERE id = ?
        """, (attempt["product_id"],)).fetchone()

        if not product or product["quantity"] < attempt["quantity"]:
            conn.rollback()
            return jsonify({
                "error": "Stock unavailable. Payment requires review."
            }), 409

        conn.execute("""
            UPDATE products
            SET quantity = quantity - ?
            WHERE id = ?
        """, (attempt["quantity"], attempt["product_id"]))

        cursor = conn.execute("""
            INSERT INTO orders (
                buyer_id, product_id, quantity,
                total, address, status
            ) VALUES (?, ?, ?, ?, ?, 'Paid')
        """, (
            attempt["buyer_id"],
            attempt["product_id"],
            attempt["quantity"],
            attempt["total"],
            attempt["address"]
        ))

        db_order_id = cursor.lastrowid

        conn.execute("""
            UPDATE payment_attempts
            SET status = 'PAID', order_id = ?
            WHERE cashfree_order_id = ?
        """, (db_order_id, cf_order_id))

        conn.commit()

        return jsonify({
            "status": "PAID",
            "order_id": db_order_id,
            "total": attempt["total"],
            "commission": 0,
            "message": "Payment verified and order confirmed."
        })

    except requests.RequestException:
        conn.rollback()
        app.logger.exception("Cashfree verification request failed")
        return jsonify({
            "error": "Unable to verify payment with Cashfree."
        }), 502

    except (sqlite3.Error, ValueError, TypeError):
        conn.rollback()
        app.logger.exception("Order confirmation failed")
        return jsonify({
            "error": "Unable to complete order confirmation."
        }), 500

    finally:
        conn.close()'''

@app.route("/api/payments/verify", methods=["POST"])
@login_required("buyer")
def verify_cashfree_payment():
    data = request.get_json(silent=True) or {}
    cf_order_id = str(data.get("order_id", "")).strip()

    if not cf_order_id:
        return jsonify({"error": "Missing Cashfree order ID."}), 400

    if not CASHFREE_APP_ID or not CASHFREE_SECRET_KEY:
        return jsonify({"error": "Cashfree credentials are missing."}), 503

    conn = connect_db()

    try:
        attempt = conn.execute("""
            SELECT * FROM payment_attempts
            WHERE cashfree_order_id = ? AND buyer_id = ?
        """, (cf_order_id, session["user_id"])).fetchone()

        if not attempt:
            return jsonify({"error": "Payment order not found."}), 404

        if attempt["status"] == "PAID" and attempt["order_id"]:
            return jsonify({
                "status": "PAID",
                "order_id": attempt["order_id"],
                "message": "Order already confirmed."
            })

        headers = {
            "x-client-id": CASHFREE_APP_ID,
            "x-client-secret": CASHFREE_SECRET_KEY,
            "x-api-version": "2025-01-01",
            "Accept": "application/json"
        }

        # Check the order status directly with Cashfree.
        order_response = requests.get(
            f"{CASHFREE_BASE_URL}/orders/{cf_order_id}",
            headers=headers,
            timeout=20
        )
        order_response.raise_for_status()
        cf_order = order_response.json()

        if (
            cf_order.get("order_status") != "PAID"
            or cf_order.get("order_currency") != "INR"
            or round(float(cf_order.get("order_amount", 0)), 2)
            != round(float(attempt["total"]), 2)
        ):
            return jsonify({
                "status": cf_order.get("order_status", "PENDING"),
                "message": "Payment is not confirmed yet."
            }), 202

        # Confirm that at least one transaction succeeded.
        payment_response = requests.get(
            f"{CASHFREE_BASE_URL}/orders/{cf_order_id}/payments",
            headers=headers,
            timeout=20
        )
        payment_response.raise_for_status()
        payments = payment_response.json()

        if not isinstance(payments, list) or not any(
            p.get("payment_status") == "SUCCESS" for p in payments
        ):
            return jsonify({
                "status": "PENDING",
                "message": "Successful payment transaction not found."
            }), 202

        # Start a write transaction before changing stock or orders.
        conn.execute("BEGIN IMMEDIATE")

        current = conn.execute("""
            SELECT * FROM payment_attempts
            WHERE cashfree_order_id = ?
        """, (cf_order_id,)).fetchone()

        if current["status"] == "PAID" and current["order_id"]:
            conn.commit()
            return jsonify({
                "status": "PAID",
                "order_id": current["order_id"],
                "message": "Order already confirmed."
            })

        product = conn.execute("""
            SELECT quantity FROM products WHERE id = ?
        """, (attempt["product_id"],)).fetchone()

        if not product or product["quantity"] < attempt["quantity"]:
            conn.rollback()
            return jsonify({
                "error": "Stock unavailable. Payment requires review."
            }), 409

        conn.execute("""
            UPDATE products
            SET quantity = quantity - ?
            WHERE id = ?
        """, (attempt["quantity"], attempt["product_id"]))

        cursor = conn.execute("""
            INSERT INTO orders (
                buyer_id, product_id, quantity,
                total, address, status
            ) VALUES (?, ?, ?, ?, ?, 'Paid')
        """, (
            attempt["buyer_id"],
            attempt["product_id"],
            attempt["quantity"],
            attempt["total"],
            attempt["address"]
        ))

        db_order_id = cursor.lastrowid

        conn.execute("""
            UPDATE payment_attempts
            SET status = 'PAID', order_id = ?
            WHERE cashfree_order_id = ?
        """, (db_order_id, cf_order_id))

        conn.commit()

        return jsonify({
            "status": "PAID",
            "order_id": db_order_id,
            "total": attempt["total"],
            "commission": 0,
            "message": "Payment verified and order confirmed."
        })

    except requests.RequestException:
        conn.rollback()
        app.logger.exception("Cashfree verification request failed")
        return jsonify({
            "error": "Unable to verify payment with Cashfree."
        }), 502

    except (sqlite3.Error, ValueError, TypeError):
        conn.rollback()
        app.logger.exception("Order confirmation failed")
        return jsonify({
            "error": "Unable to complete order confirmation."
        }), 500

    finally:
        conn.close()
        # ---------------- CASHFREE PAYMENT RETURN ----------------

@app.route("/payment/return")
def payment_return():
    return send_from_directory(BASE_DIR, "index.html")



# ---------------- VIEW ORDERS ----------------


# ---------------- VIEW ORDERS ----------------

@app.route("/api/my-orders")
@login_required()
def my_orders():
    conn = connect_db()

    try:
        if session.get("role") == "buyer":
            query = """
                SELECT orders.*, products.name AS product_name
                FROM orders
                JOIN products ON products.id = orders.product_id
                WHERE orders.buyer_id = ?
                ORDER BY orders.id DESC
            """
        elif session.get("role") == "farmer":
            query = """
                SELECT orders.*, products.name AS product_name
                FROM orders
                JOIN products ON products.id = orders.product_id
                JOIN users ON users.id = products.farmer_id
                WHERE users.id = ?
                ORDER BY orders.id DESC
            """
        else:
            return jsonify({"error": "Invalid user role."}), 403

        orders = conn.execute(
            query, (session["user_id"],)
        ).fetchall()

        return jsonify([dict(order) for order in orders])

    finally:
        conn.close()
        # ---------------- ADMIN LOGIN ----------------


@app.route("/api/admin/login", methods=["POST"])
def admin_login():
    data = request.get_json(silent=True) or {}

    phone = str(data.get("phone", "")).strip()
    password = str(data.get("password", ""))

    if not ADMIN_PHONE or not ADMIN_PASSWORD:
        return jsonify({
            "error": "Admin credentials are not configured."
        }), 503

    if (
    not hmac.compare_digest(phone, ADMIN_PHONE)
    or not hmac.compare_digest(password, ADMIN_PASSWORD)
):
        return jsonify({
            "error": "Invalid admin mobile number or password."
        }), 401

    session.clear()
    session["role"] = "admin"
    session["user_id"] = -1

    return jsonify({"message": "Admin login successful!"})


@app.route("/api/admin/logout", methods=["POST"])
@login_required("admin")
def admin_logout():
    session.clear()
    return jsonify({"message": "Admin logged out successfully."})
# ---------------- ADMIN: DASHBOARD SUMMARY ----------------

@app.route("/api/admin/summary")
@login_required("admin")
def admin_summary():
    conn = connect_db()

    try:
        farmers = conn.execute(
            "SELECT COUNT(*) FROM users WHERE role = 'farmer'"
        ).fetchone()[0]

        buyers = conn.execute(
            "SELECT COUNT(*) FROM users WHERE role = 'buyer'"
        ).fetchone()[0]

        products = conn.execute(
            "SELECT COUNT(*) FROM products"
        ).fetchone()[0]

        orders = conn.execute(
            "SELECT COUNT(*) FROM orders"
        ).fetchone()[0]

        return jsonify({
            "farmers": farmers,
            "buyers": buyers,
            "products": products,
            "orders": orders
        })

    finally:
        conn.close()

# ---------------- ADMIN: VIEW USERS ----------------

@app.route("/api/admin/users")
@login_required("admin")
def admin_users():
    conn = connect_db()

    try:
        rows = conn.execute("""
            SELECT id, name, phone, role, address
            FROM users
            ORDER BY id DESC
        """).fetchall()

        return jsonify([dict(row) for row in rows])
    finally:
        conn.close()


# ---------------- ADMIN: VIEW PRODUCTS ----------------

@app.route("/api/admin/products")
@login_required("admin")
def admin_products():
    conn = connect_db()

    try:
        rows = conn.execute("""
            SELECT
                products.id,
                products.name,
                products.price,
                products.quantity,
                products.location,
                users.name AS farmer_name
            FROM products
            JOIN users ON users.id = products.farmer_id
            ORDER BY products.id DESC
        """).fetchall()

        return jsonify([dict(row) for row in rows])
    finally:
        conn.close()


# ---------------- ADMIN: VIEW ORDERS ----------------

@app.route("/api/admin/orders")
@login_required("admin")
def admin_orders():
    conn = connect_db()

    try:
        rows = conn.execute("""
            SELECT
                orders.id,
                orders.quantity,
                orders.total,
                orders.address,
                orders.status,
                orders.created_at,
                products.name AS product_name,
                users.name AS buyer_name
            FROM orders
            JOIN products ON products.id = orders.product_id
            JOIN users ON users.id = orders.buyer_id
            ORDER BY orders.id DESC
        """).fetchall()

        return jsonify([dict(row) for row in rows])
    finally:
        conn.close()
# All Flask routes should be defined above this point.

create_tables()

if __name__ == "__main__":
    app.run(debug=True)
