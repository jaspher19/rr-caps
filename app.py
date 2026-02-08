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

# --- UPDATED EMAIL CONFIG (PORT 465 SSL) ---
# This is the primary fix for the Render "Worker Timeout"
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 465
app.config['MAIL_USE_TLS'] = False
app.config['MAIL_USE_SSL'] = True
app.config['MAIL_USERNAME'] = SHOP_EMAIL
# Ensure your Render Environment Variable 'MAIL_PASSWORD' is a 16-character App Password
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD', 'bsjbptoaxqzjoern') 
app.config['MAIL_DEFAULT_SENDER'] = SHOP_EMAIL

mail = Mail(app)

# --- UTILITY FUNCTIONS ---
def load_products():
    if not os.path.exists(PRODUCT_FILE): return []
    with open(PRODUCT_FILE, 'r') as f: 
        try: return json.load(f)
        except: return []

def save_products(products):
    with open(PRODUCT_FILE, 'w') as f:
        json.dump(products, f, indent=4)

def load_orders():
    if not os.path.exists(ORDER_FILE): return []
    try:
        with open(ORDER_FILE, 'r') as f: return json.load(f)
    except: return []

def save_order_to_history(order_data):
    orders = load_orders()
    orders.append(order_data)
    with open(ORDER_FILE, 'w') as f:
        json.dump(orders, f, indent=4)

# --- PUBLIC ROUTES ---
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

# --- SECURE ADMIN ROUTES ---
@app.route("/admin")
def admin():
    key = request.args.get('key')
    if key != ADMIN_PASSWORD:
        return "Unauthorized Access", 403
    products = load_products()
    return render_template("admin.html", products=products, admin_key=key)

@app.route("/admin/add", methods=["POST"])
def add_product():
    key = request.args.get('key')
    if key != ADMIN_PASSWORD: return "Unauthorized", 403

    name = request.form.get("name")
    price = request.form.get("price", 0)
    category = request.form.get("category")
    badge = request.form.get("badge")
    
    try: price = int(price)
    except: price = 0
    
    file = request.files.get("photo")
    image_path = "images/products/default.jpg" 
    
    if file and file.filename != '':
        filename = secure_filename(file.filename)
        unique_name = f"{int(time.time())}_{filename}"
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_name))
        image_path = f"images/products/{unique_name}"

    products = load_products()
    products.append({
        "id": int(time.time()), 
        "name": name,
        "price": price,
        "category": category,
        "badge": badge,
        "image": image_path
    })
    save_products(products)
    return redirect(url_for('admin', key=key, success=1))

@app.route("/admin/delete/<int:product_id>", methods=["POST"])
def delete_product(product_id):
    key = request.args.get('key')
    if key != ADMIN_PASSWORD: return "Unauthorized", 403

    products = load_products()
    products = [p for p in products if p['id'] != product_id]
    save_products(products)
    return redirect(url_for('admin', key=key, deleted=1))

@app.route("/admin/clear-store", methods=["POST"])
def clear_store():
    key = request.args.get('key')
    if key != ADMIN_PASSWORD: return "Unauthorized", 403

    save_products([]) 
    return redirect(url_for('admin', key=key, cleared=1))

@app.route("/admin/orders")
def view_orders():
    key = request.args.get('key')
    if key != ADMIN_PASSWORD: return "Unauthorized", 403

    orders = load_orders()
    return render_template("orders.html", orders=orders, is_admin=True, admin_key=key)

# --- CART & CHECKOUT ROUTES ---
@app.route("/add-to-cart", methods=["POST"])
def add_to_cart():
    product_id = request.form.get("id")
    if product_id:
        if "cart" not in session: session["cart"] = []
        session["cart"].append(str(product_id))
        session.modified = True 
        return jsonify({"status": "success", "cart_count": len(session["cart"])})
    return jsonify({"status": "error"}), 400

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

# ROBUST CHECKOUT WITH TIMEOUT PROTECTION
@app.route("/checkout", methods=["POST"])
def checkout():
    products = load_products()
    cart_ids = session.get("cart", [])
    if not cart_ids: return redirect(url_for("home"))

    counts = {str(cid): cart_ids.count(cid) for cid in set(cart_ids)}
    customer_email = request.form.get("email")
    customer_address = request.form.get("address")
    customer_city = request.form.get("city")
    customer_zip = request.form.get("zip", "N/A")
    
    order_id = f"RR-{random.randint(1000, 9999)}"
    
    purchased_items = []
    grand_total = 0
    items_html_rows = ""
    
    for product_id, qty in counts.items():
        for p in products:
            if str(p["id"]) == product_id:
                line_total = p["price"] * qty
                grand_total += line_total
                item_data = p.copy()
                item_data['quantity'] = qty
                purchased_items.append(item_data)
                
                items_html_rows += f"""
                <tr style="border-bottom: 1px solid #333;">
                    <td style="padding: 10px; color: #fff;">{p['name']} (x{qty})</td>
                    <td style="padding: 10px; color: #fff; text-align: right;">₱{line_total}</td>
                </tr>"""

    # 1. SAVE ORDER DATA FIRST - Secure the sale before trying the email
    save_order_to_history({
        "order_id": order_id, 
        "date": datetime.now().strftime("%b %d, %Y"),
        "items": purchased_items, 
        "total": grand_total, 
        "email": customer_email,
        "shipping": f"{customer_address}, {customer_city}, {customer_zip}"
    })

    # 2. CLEAR CART
    session.pop("cart", None)
    session.modified = True

    # 3. ATTEMPT EMAIL
    # The try/except block ensures that if the email connection hangs,
    # the code won't reach the Gunicorn timeout limit before returning the success page.
    try:
        msg = Message(f"Order #{order_id} Confirmed - RCAPS4STREET", recipients=[customer_email, SHOP_EMAIL])
        msg.html = f"""
        <div style="background-color: #000; color: #fff; padding: 30px; font-family: sans-serif;">
            <h1 style="border-bottom: 1px solid #fff; padding-bottom: 10px;">RECEIPT</h1>
            <p>Order ID: {order_id}</p>
            <p>Shipping to: {customer_address}, {customer_city}, {customer_zip}</p>
            <table style="width: 100%; border-collapse: collapse;">{items_html_rows}</table>
            <h2 style="text-align: right; border-top: 1px solid #fff; padding-top: 10px;">TOTAL: ₱{grand_total}</h2>
        </div>
        """
        mail.send(msg)
    except Exception as e:
        print(f"SMTP Error: {e}")

    # 4. REDIRECT TO SUCCESS IMMEDIATELY
    return render_template("success.html", order_id=order_id, total=grand_total)

if __name__ == "__main__":
    app.run(debug=True)