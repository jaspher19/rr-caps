from flask import Flask, render_template, request, redirect, session, url_for, jsonify
from flask_mail import Mail, Message
from werkzeug.utils import secure_filename
import random, os, json, time, threading
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "rcaps4street_ultra_secret_key")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "STREET_BOSS_2026") 

# Use absolute paths to ensure Render finds them
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static/images/products')
PRODUCT_FILE = os.path.join(BASE_DIR, 'products.json')
ORDER_FILE = os.path.join(BASE_DIR, 'orders.json')
SHOP_EMAIL = 'jasphertampos5@gmail.com' 

if not os.path.exists(UPLOAD_FOLDER): 
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Ensure JSON files exist so the app doesn't crash on load
for file_path in [PRODUCT_FILE, ORDER_FILE]:
    if not os.path.exists(file_path):
        with open(file_path, 'w') as f:
            json.dump([], f)

# --- EMAIL CONFIG ---
app.config.update(
    MAIL_SERVER='smtp.gmail.com',
    MAIL_PORT=587,
    MAIL_USE_TLS=True,
    MAIL_USE_SSL=False,
    MAIL_USERNAME=SHOP_EMAIL,
    MAIL_PASSWORD=os.environ.get('MAIL_PASSWORD', 'bsjbptoaxqzjoern'),
    MAIL_DEFAULT_SENDER=SHOP_EMAIL
)
mail = Mail(app)

def send_async_email(app, msg):
    with app.app_context():
        try:
            mail.send(msg)
            print(">>> EMAIL SENT SUCCESSFULLY")
        except Exception as e:
            print(f">>> Background Mail Error: {e}")

# --- REPAIRED UTILS ---
def load_products():
    try:
        if os.path.exists(PRODUCT_FILE):
            with open(PRODUCT_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        print(f"Error loading products: {e}")
    return []

def save_products(products):
    with open(PRODUCT_FILE, 'w') as f:
        json.dump(products, f, indent=4)

def load_orders():
    try:
        if os.path.exists(ORDER_FILE):
            with open(ORDER_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        print(f"Error loading orders: {e}")
    return []

# --- ROUTES ---
@app.route("/")
@app.route("/shop")
def home():
    return render_template("index.html", products=load_products(), cart_count=len(session.get("cart", [])))

@app.route("/admin")
def admin():
    key = request.args.get('key')
    print(f"Admin Access Attempt with key: {key}") # This will show in Render Logs
    if key != ADMIN_PASSWORD:
        return f"Unauthorized. Hint: Check your URL key.", 403
    return render_template("admin.html", products=load_products(), admin_key=key)

# ... (Keep other routes like add_product, delete_product, checkout as they were) ...