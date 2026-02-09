from flask import Flask, render_template, request, redirect, session, url_for, jsonify
import requests 
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from werkzeug.utils import secure_filename
import random, os, json, time
from datetime import datetime

app = Flask(__name__)
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

# --- FIXED EMAIL FUNCTION (PORT 465 + SSL) ---
def send_the_email(order_id, customer_email, total_price, address, city):
    """Sends email via Brevo SMTP SSL. Optimized to prevent Render timeouts."""
    if not BREVO_API_KEY:
        print(">>> SMTP ERROR: BREVO_API_KEY is missing from Env Vars!")
        return

    # Configuration for SSL
    smtp_server = "smtp-relay.brevo.com"
    smtp_port = 465 
    
    msg = MIMEMultipart()
    msg['From'] = f"RCAPS4STREETS <{MAIL_USER}>"
    msg['To'] = customer_email
    msg['Subject'] = f"Order Confirmation: {order_id}"

    body = f"Order Confirmation\n\nOrder ID: {order_id}\nTotal: ₱{total_price}\nAddress: {address}, {city}"
    msg.attach(MIMEText(body, 'plain'))

    try:
        print(f">>> SMTP ATTEMPT: Connecting to {smtp_server} via SSL...")
        # timeout=10 is CRITICAL. It stops the app from hanging if the connection is slow.
        server = smtplib.SMTP_SSL(smtp_server, smtp_port, timeout=10)
        server.login(MAIL_USER, BREVO_API_KEY)
        server.send_message(msg)
        
        # Admin copy
        msg['To'] = MAIL_USER
        server.send_message(msg)
        
        server.quit()
        print(">>> SUCCESS: Email sent via SSL!")
    except Exception as e:
        # We catch the error so the website doesn't crash for the customer
        print(f">>> SMTP FAILURE (Non-Critical): {str(e)}")

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
        order_id = f"RCAPS-{datetime.now().year}-{random.randint(1000, 9999)}"
        
        orders = load_orders()
        orders.append({
            "order_id": order_id, "email": customer_email,
            "address": customer_address, "city": customer_city,
            "total": total_price, "date": datetime.now().strftime("%b %d, %Y")
        })
        with open(ORDER_FILE, 'w') as f: json.dump(orders, f, indent=4)
        
        # Trigger email without crashing the request
        send_the_email(order_id, customer_email, total_price, customer_address, customer_city)
        
        session.pop("cart", None)
        return render_template("success.html", order_id=order_id, items=checkout_items, total=total_price, email=customer_email, address=customer_address, city=customer_city)
    except Exception as e:
        print(f"Checkout Error: {e}")
        return redirect(url_for('home'))

# Include your add-to-cart, remove, etc. routes below...
@app.route("/add-to-cart", methods=["POST"])
def add_to_cart():
    if "cart" not in session: session["cart"] = []
    session["cart"].append(str(request.form.get("id")))
    session.modified = True
    return jsonify({"status": "success", "cart_count": len(session["cart"])})

if __name__ == "__main__":
    app.run(debug=True)