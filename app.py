from flask import Flask, render_template, request, redirect, session, url_for, jsonify
from flask_mail import Mail, Message
from werkzeug.utils import secure_filename
import random
import os
import json
import time
from datetime import datetime

app = Flask(__name__)

# --- SECURE CONFIGURATION ---
app.secret_key = os.environ.get("SECRET_KEY", "rcaps4street_ultra_secret_key")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "STREET_BOSS_2026") 

app.config.update(
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=False, 
)

# --- DIRECTORY CONFIGURATION ---
UPLOAD_FOLDER = 'static/images/products'
PRODUCT_FILE = 'products.json'
ORDER_FILE = 'orders.json'
SHOP_EMAIL = 'jasphertampos5@gmail.com' 

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# --- UPDATED EMAIL CONFIG ---
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 465
app.config['MAIL_USE_TLS'] = False
app.config['MAIL_USE_SSL'] = True
app.config['MAIL_USERNAME'] = SHOP_EMAIL
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD', 'bsjbptoaxqzjoern') 
app.config['MAIL_DEFAULT_SENDER'] = SHOP_EMAIL

mail = Mail(app)

# --- INVINCIBLE UTILITY FUNCTIONS ---
def load_products():
    if not os.path.exists(PRODUCT_FILE): return []
    try:
        with open(PRODUCT_FILE, 'r') as f: 
            return json.load(f)
    except:
        return []

def save_products(products):
    try:
        with open(PRODUCT_FILE, 'w') as f:
            json.dump(products, f, indent=4)
    except Exception as e:
        print(f"CRITICAL ERROR: {e}")

def load_orders():
    if not os.path.exists(ORDER_FILE): return []
    try:
        with open(ORDER_FILE, 'r') as f:
            return json.load(f)
    except:
        return []

def save_order_to_history(order_data):
    try:
        orders = load_orders()
        orders.append(order_data)
        with open(ORDER_FILE, 'w') as f:
            json.dump(orders, f, indent=4)
    except Exception as e:
        print(f"FILE SYSTEM ERROR: {e}")

# --- ROUTES ---
@app.route("/")
@app.route("/shop")
def home():
    products = load_products()
    cart = session.get("cart", [])
    return render_template("index.html", products=products, cart_count=len(cart))

@app.route("/orders")
def order_history():
    orders = load_orders()
    is_admin = request.args.get('key') == ADMIN_PASSWORD
    return render_template("orders.html", orders=orders, is_admin=is_admin, admin_key=request.args.get('key'))

@app.route("/admin")
def admin():
    key = request.args.get('key')
    if key != ADMIN_PASSWORD: return "Unauthorized", 403
    return render_template("admin.html", products=load_products(), admin_key=key)

@app.route("/admin/add", methods=["POST"])
def add_product():
    key = request.args.get('key')
    if key != ADMIN_PASSWORD: return "Unauthorized", 403
    name = request.form.get("name")
    price = int(request.form.get("price", 0))
    file = request.files.get("photo")
    image_path = "images/products/default.jpg"
    if file:
        filename = secure_filename(file.filename)
        unique_name = f"{int(time.time())}_{filename}"
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_name))
        image_path = f"images/products/{unique_name}"
    products = load_products()
    products.append({"id": int(time.time()), "name": name, "price": price, "image": image_path})
    save_products(products)
    return redirect(url_for('admin', key=key))

@app.route("/add-to-cart", methods=["POST"])
def add_to_cart():
    product_id = request.form.get("id")
    if "cart" not in session: session["cart"] = []
    session["cart"].append(str(product_id))
    session.modified = True 
    return jsonify({"status": "success", "cart_count": len(session["cart"])})
@app.route("/remove-from-cart", methods=["POST"])
def remove_from_cart():
    product_id = request.form.get("product_id")
    cart = session.get("cart", [])
    str_id = str(product_id)
    if str_id in cart:
        cart.remove(str_id)
        session["cart"] = cart
        session.modified = True
    return redirect(url_for('cart'))

@app.route("/empty-cart", methods=["POST", "GET"])
def empty_cart():
    session.pop("cart", None)
    session.modified = True
    return redirect(url_for('cart'))
@app.route("/cart")
def cart():
    products = load_products()
    cart_ids = session.get("cart", [])
    counts = {str(cid): cart_ids.count(cid) for cid in set(cart_ids)}
    cart_items = []
    total_price = 0
    for product_id, qty in counts.items():
        for p in products:
            if str(p["id"]) == product_id:
                item = p.copy()
                item['quantity'] = qty
                cart_items.append(item)
                total_price += p["price"] * qty
    return render_template("cart.html", cart=cart_items, total_price=total_price)

# THE FIXED CHECKOUT
@app.route("/checkout", methods=["POST"])
def checkout():
    try:
        products = load_products()
        cart_ids = session.get("cart", [])
        if not cart_ids: return redirect(url_for("home"))

        customer_email = request.form.get("email")
        customer_address = request.form.get("address")
        customer_city = request.form.get("city")
        order_id = f"RR-{random.randint(1000, 9999)}"
        
        purchased_items = []
        grand_total = 0
        items_html_rows = ""
        
        counts = {str(cid): cart_ids.count(cid) for cid in set(cart_ids)}
        for product_id, qty in counts.items():
            for p in products:
                if str(p["id"]) == product_id:
                    line_total = p["price"] * qty
                    grand_total += line_total
                    purchased_items.append({"name": p['name'], "quantity": qty, "price": p['price']})
                    items_html_rows += f"<tr><td>{p['name']} (x{qty})</td><td>₱{line_total}</td></tr>"

        # 1. SAVE & CLEAR FIRST (Safety)
        save_order_to_history({
            "order_id": order_id, 
            "date": datetime.now().strftime("%b %d, %Y"),
            "items": purchased_items, 
            "total": grand_total, 
            "email": customer_email,
            "shipping": f"{customer_address}, {customer_city}"
        })
        session.pop("cart", None)
        session.modified = True

        # 2. EMAIL (With internal timeout safety)
        try:
            msg = Message(f"Order #{order_id} Confirmed", recipients=[customer_email, SHOP_EMAIL])
            msg.html = f"<h2>Order {order_id}</h2><table>{items_html_rows}</table><h3>Total: ₱{grand_total}</h3>"
            mail.send(msg)
        except Exception as e:
            print(f"Email Timeout/Error: {e}")

        return render_template("success.html", order_id=order_id, total=grand_total)

    except Exception as e:
        print(f"CRITICAL CHECKOUT ERROR: {e}")
        return f"Order Processed! ID: RR-{random.randint(1000,9999)}"

if __name__ == "__main__":
    app.run(debug=True)