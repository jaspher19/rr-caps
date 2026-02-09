from flask import Flask, render_template, request, redirect, session, url_for, jsonify
import requests
from werkzeug.utils import secure_filename
import random, os, time
from datetime import datetime
from pymongo import MongoClient

app = Flask(__name__)
# Security setup - Pulls from Render Environment Variables
app.secret_key = os.environ.get("SECRET_KEY", "rcaps4street_dev_key_123")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "STREET_BOSS_2026") 

# --- MONGODB CONFIG ---
# Pulls the URI from Render. Ensure MONGO_URI is added in Render settings.
MONGO_URI = os.environ.get("MONGO_URI", "REPLACE_THIS_IN_RENDER_DASHBOARD")
client = MongoClient(MONGO_URI)
db = client['rcaps_database']  
products_col = db['products']   
orders_col = db['orders']       

# --- FILE CONFIG ---
UPLOAD_FOLDER = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'static/images/products')
if not os.path.exists(UPLOAD_FOLDER): 
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# --- EMAIL CONFIG ---
MAIL_USER = os.environ.get('MAIL_USERNAME', 'ultrainstinct1596321@gmail.com')
BREVO_API_KEY = os.environ.get('BREVO_API_KEY')

# --- EMAIL VIA BREVO API FUNCTION ---
def send_the_email(order_id, customer_email, total_price, address, city):
    if not BREVO_API_KEY:
        print(">>> API ERROR: BREVO_API_KEY is missing!")
        return

    url = "https://api.brevo.com/v3/smtp/email"
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "api-key": BREVO_API_KEY
    }
    payload = {
        "sender": {"name": "RCAPS4STREETS", "email": MAIL_USER},
        "to": [{"email": customer_email}],
        "subject": f"Order Confirmation: {order_id}",
        "textContent": f"Order ID: {order_id}\nTotal: ₱{total_price}\nAddress: {address}, {city}\n\nThank you!",
        "bcc": [{"email": MAIL_USER}]
    }
    try:
        requests.post(url, json=payload, headers=headers, timeout=15)
        print(">>> SUCCESS: Email request sent to Brevo!")
    except Exception as e:
        print(f">>> API EXCEPTION: {str(e)}")

# --- SHOP ROUTES ---

@app.route("/")
@app.route("/shop")
def home():
    # Pulls directly from MongoDB (Recalls storage on load)
    all_products = list(products_col.find({}, {'_id': 0}))
    return render_template("index.html", products=all_products, cart_count=len(session.get("cart", [])))

@app.route("/cart")
def view_cart():
    cart_ids = session.get("cart", [])
    cart_items = []
    total_price = 0
    counts = {str(cid): cart_ids.count(str(cid)) for cid in set(cart_ids)}
    
    for pid, qty in counts.items():
        p = products_col.find_one({"id": int(pid)}, {'_id': 0})
        if p:
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
        
        checkout_items = []
        total_price = 0
        counts = {str(cid): cart_ids.count(str(cid)) for cid in set(cart_ids)}
        
        for pid, qty in counts.items():
            p = products_col.find_one({"id": int(pid)}, {'_id': 0})
            if p:
                item = p.copy()
                item['quantity'] = qty
                checkout_items.append(item)
                total_price += p["price"] * qty
        
        customer_email = request.form.get("email")
        customer_address = request.form.get("address", "N/A")
        customer_city = request.form.get("city", "N/A")
        order_id = f"RCAPS-{datetime.now().year}-{random.randint(1000, 9999)}"
        
        # Saves order to MongoDB permanent storage
        orders_col.insert_one({
            "order_id": order_id, 
            "email": customer_email,
            "address": customer_address, 
            "city": customer_city,
            "total": total_price, 
            "date": datetime.now().strftime("%b %d, %Y")
        })
        
        send_the_email(order_id, customer_email, total_price, customer_address, customer_city)
        
        session.pop("cart", None)
        return render_template("success.html", order_id=order_id, items=checkout_items, total=total_price, email=customer_email, address=customer_address, city=customer_city)
    except Exception as e:
        print(f"Checkout Error: {e}")
        return redirect(url_for('home'))

# --- ADMIN ROUTES ---

@app.route("/admin")
def admin():
    key = request.args.get('key')
    if key != ADMIN_PASSWORD: return "Unauthorized", 403
    all_products = list(products_col.find({}, {'_id': 0}))
    return render_template("admin.html", products=all_products, admin_key=key)

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
    
    # Saves new product to MongoDB
    products_col.insert_one({
        "id": int(time.time()), 
        "name": request.form.get("name"),
        "price": int(request.form.get("price", 0)),
        "image": image_path,
        "badge": request.form.get("badge"),
        "category": request.form.get("category")
    })
    return redirect(url_for('admin', key=key))

@app.route("/admin/edit_price/<int:product_id>", methods=["POST"])
def edit_price(product_id):
    key = request.args.get('key')
    if key != ADMIN_PASSWORD: return "Unauthorized", 403
    
    new_price = request.form.get("new_price")
    if new_price:
        products_col.update_one(
            {"id": product_id}, 
            {"$set": {"price": int(new_price)}}
        )
    return redirect(url_for('admin', key=key))

@app.route("/admin/delete/<int:product_id>", methods=["POST"])
def delete_product(product_id):
    key = request.args.get('key')
    if key != ADMIN_PASSWORD: return "Unauthorized", 403
    products_col.delete_one({"id": product_id})
    return redirect(url_for('admin', key=key))

if __name__ == "__main__":
    app.run(debug=True)