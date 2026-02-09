from flask import Flask, render_template, request, redirect, session, url_for, jsonify
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from werkzeug.utils import secure_filename
import random, os, json, time
from datetime import datetime

app = Flask(__name__)
# Security setup
app.secret_key = os.environ.get("SECRET_KEY", "rcaps4street_dev_key_123")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "STREET_BOSS_2026") 

# --- PERSISTENT STORAGE CONFIG ---
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATA_DIR = '/data' if os.path.exists('/data') else BASE_DIR

UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static/images/products')
PRODUCT_FILE = os.path.join(DATA_DIR, 'products.json')
ORDER_FILE = os.path.join(DATA_DIR, 'orders.json')

# --- EMAIL CONFIG ---
MAIL_USER = os.environ.get('MAIL_USERNAME', 'ultrainstinct1596321@gmail.com')
BREVO_API_KEY = os.environ.get('BREVO_API_KEY')

if not os.path.exists(UPLOAD_FOLDER): 
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Initialize JSON files
for file_path in [PRODUCT_FILE, ORDER_FILE]:
    if not os.path.exists(file_path):
        with open(file_path, 'w') as f:
            json.dump([], f)

# --- EMAIL VIA BREVO SMTP FUNCTION ---
def send_the_email(order_id, customer_email, total_price, address, city):
    """Sends email via Brevo SMTP SSL. Optimized to prevent Render timeouts."""
    if not BREVO_API_KEY:
        print(">>> SMTP ERROR: BREVO_API_KEY is missing!")
        return

    smtp_server = "smtp-relay.brevo.com"
    smtp_port = 465 
    
    msg = MIMEMultipart()
    msg['From'] = f"RCAPS4STREETS <{MAIL_USER}>"
    msg['To'] = customer_email
    msg['Subject'] = f"Order Confirmation: {order_id}"

    body = f"Order Confirmation\n\nOrder ID: {order_id}\nTotal: ₱{total_price}\nAddress: {address}, {city}"
    msg.attach(MIMEText(body, 'plain'))

    try:
        print(f">>> SMTP ATTEMPT: Connecting via SSL...")
        server = smtplib.SMTP_SSL(smtp_server, smtp_port, timeout=10)
        server.login(MAIL_USER, BREVO_API_KEY)
        server.send_message(msg)
        
        # Self copy for admin
        msg['To'] = MAIL_USER
        server.send_message(msg)
        server.quit()
        print(">>> SUCCESS: Email sent via SSL!")
    except Exception as e:
        print(f">>> SMTP FAILURE: {str(e)}")

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

# --- SHOP ROUTES ---

@app.route("/")
@app.route("/shop")
def home():
    return render_template("index.html", products=load_products(), cart_count=len(session.get("cart", [])))

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

@app.route("/checkout", methods=["POST"])
def checkout():
    try:
        cart_ids = session.get("cart", [])
        if not cart_ids: return redirect(url_for("home"))
        
        products = load_