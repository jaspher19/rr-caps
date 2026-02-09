from flask import Flask, render_template, request, redirect, session, url_for, jsonify
import requests  # Required for the API fix
from werkzeug.utils import secure_filename
import random, os, json, time
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "rcaps4street_ultra_secret_key")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "STREET_BOSS_2026") 

# --- PERSISTENT STORAGE CONFIG ---
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
if os.path.exists('/data'):
    DATA_DIR = '/data'
else:
    DATA_DIR = BASE_DIR

UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static/images/products')
PRODUCT_FILE = os.path.join(DATA_DIR, 'products.json')
ORDER_FILE = os.path.join(DATA_DIR, 'orders.json')

# API & Email Config
MAIL_USER = os.environ.get('MAIL_USERNAME', 'ultrainstinct1596321@gmail.com')

# SECURE FIX: We fetch the key from Render's environment, not from this file!
BREVO_API_KEY = os.environ.get('BREVO_API_KEY')

if not os.path.exists(UPLOAD_FOLDER): 
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Initialize JSON files
for file_path in [PRODUCT_FILE, ORDER_FILE]:
    if not os.path.exists(file_path):
        with open(file_path, 'w') as f:
            json.dump([], f)

# --- EMAIL VIA API FUNCTION ---
def send_the_email(order_id, customer_email, total_price, address, city):
    """Sends email via Brevo Web API to bypass Render network blocks."""
    url = "https://api.brevo.com/v3/smtp/email"
    
    payload = {
        "sender": {"name": "RCAPS4STREETS", "email": MAIL_USER},
        "to": [
            {"email": customer_email},
            {"email": MAIL_USER} # Carbon copy to yourself
        ],
        "subject": f"Order Confirmation: {order_id} - RCAPS4STREETS",
        "textContent": f"""
Hello,

This is a receipt for your order at RCAPS4STREETS.

Order ID: {order_id}
Total: ₱{total_price}
Shipping to: {address}, {city}

Thank you for shopping with us!
"""
    }
    
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "api-key": BREVO_API_KEY
    }

    try:
        print(f">>> API ATTEMPT: Sending via Brevo for Order {order_id}...")
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        if response.status_code == 201:
            print(">>> SUCCESS: Email sent successfully via Web API!")
        else:
            print(f">>> API FAILURE: {response.status_code} - {response.text}")
    except Exception as e:
        print(f">>> API ERROR: {str(e)}")

# --- UTILS ---
def load_products():
    try:
        with open(PRODUCT_FILE, 'r') as f: return json.load(f)
    except: return []

def save_products(products):
    with open(PRODUCT_FILE, 'w') as f: json.dump(products, f, indent=4)

def load_orders():
    try:
        with open(ORDER_FILE, 'r') as f: return json.load(f)
    except: return []

# --- ROUTES ---

@app.route("/")
@app.route("/shop")
def home():
    return render_template("index.html", products=load_products(), cart_count=len(session.get("cart", [])))

@app.route("/admin")
def admin():
    key = request.args.get('key')
    if key != ADMIN_PASSWORD: return "Unauthorized", 403
    return render_template("admin.html", products=load_products(), admin_key=key)

@app.route("/admin/add", methods=["POST"])
def add_product():
    key = request.args.get('key')
    if key != ADMIN_PASSWORD: return "Unauthorized", 403
    
    file = request.files.get("photo")
    image_path = "images/products/default.jpg"
    if file:
        filename = secure_filename(file.filename)
        unique_name = f"{int(time.time())}_{filename}"
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_name))
        image_path = f"images/products/{unique_name}"
    
    products = load_products()
    products.append({
        "id": int(time.time()), 
        "name": request.form.get("name"),
        "price": int(request.form.get("price", 0)),
        "image": image_path,
        "badge": request.form.get("badge"),
        "category": request.form.get("category")
    })
    save_products(products)
    return redirect(url_for('admin', key=key, success=True))

@app.route("/admin/delete/<int:product_id>", methods=["POST"])
def delete_product(product_id):
    key = request.args.get('key')
    if key != ADMIN_PASSWORD: return "Unauthorized", 403
    products = [p for p in load_products() if p['id'] != product_id]
    save_products(products)
    return redirect(url_for('admin', key=key))

@app.route("/admin/clear", methods=["POST"])
def clear_store():
    key = request.args.get('key')
    if key != ADMIN_PASSWORD: return "Unauthorized", 403
    save_products([])
    return redirect(url_for('admin', key=key))

@app.route("/admin/orders")
def order_history():
    key = request.args.get('key')
    if key != ADMIN_PASSWORD: return "Unauthorized", 403
    return render_template("orders.html", orders=load_orders(), admin_key=key)

# --- CART ---

@app.route("/cart")
def view_cart():
    products = load_products()
    cart_ids = session.get("cart", [])
    cart_items = []
    total_price = 0
    counts = {str(cid): cart_ids.count(str(cid)) for cid in set(cart_ids)}
    
    for pid, qty in counts.items():
        for p in products:
            if str(p["id"]) == pid:
                item = p.copy()
                item['quantity'] = qty
                cart_items.append(item)
                total_price += p["price"] * qty
    return render_template("cart.html", cart=cart_items, total_price=total_price)

@app.route("/add-to-cart", methods=["POST"])
def add_to_cart():
    if "cart" not in session: session["cart"] = []
    session["cart"].append(str(request.form.get("id")))
    session.modified = True
    return jsonify({"status": "success", "cart_count": len(session["cart"])})

@app.route("/remove-from-cart", methods=["POST"])
def remove_from_cart():
    product_id = request.form.get("product_id")
    if "cart" in session and str(product_id) in session["cart"]:
        session["cart"].remove(str(product_id))
        session.modified = True
    return redirect(url_for('view_cart'))

@app.route("/empty-cart", methods=["POST"])
def empty_cart():
    session.pop("cart", None)
    return redirect(url_for('view_cart'))

# --- CHECKOUT ---

@app.route("/checkout", methods=["POST"])
def checkout():
    try:
        cart_ids = session.get("cart", [])
        if not cart_ids: return redirect(url_for("home"))
        
        products = load_products()
        checkout_items = []
        total_price = 0
        counts = {str(cid): cart_ids.count(str(cid)) for cid in set(cart_ids)}
        for pid, qty in counts.items():
            for p in products:
                if str(p["id"]) == pid:
                    item = p.copy()
                    item['quantity'] = qty
                    checkout_items.append(item)
                    total_price += p["price"] * qty
        
        customer_email = request.form.get("email")
        customer_address = request.form.get("address", "N/A")
        customer_city = request.form.get("city", "N/A")

        current_year = datetime.now().year
        order_id = f"RCAPS-{current_year}-{random.randint(1000, 9999)}"
        
        orders = load_orders()
        orders.append({
            "order_id": order_id, 
            "email": customer_email,
            "address": customer_address,
            "city": customer_city,
            "total": total_price,
            "date": datetime.now().strftime("%b %d, %Y")
        })
        with open(ORDER_FILE, 'w') as f: json.dump(orders, f, indent=4)
        
        print(f">>> INITIATING CHECKOUT FOR: {customer_email}")
        
        # Trigger the API Email
        send_the_email(order_id, customer_email, total_price, customer_address, customer_city)

        session.pop("cart", None)
        session.modified = True

        return render_template("success.html", 
                               order_id=order_id, 
                               items=checkout_items, 
                               total=total_price, 
                               email=customer_email, 
                               address=customer_address, 
                               city=customer_city)
    except Exception as e:
        print(f"Checkout Error: {e}")
        return redirect(url_for('home'))

if __name__ == "__main__":
    app.run(debug=True)