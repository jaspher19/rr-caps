from flask import Flask, render_template, request, redirect, session, url_for, jsonify
import requests
from werkzeug.utils import secure_filename
import random, os, time
from datetime import datetime
from pymongo import MongoClient
import certifi
import cloudinary
import cloudinary.uploader

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "rcaps4street_dev_key_123")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "STREET_BOSS_2026") 

# --- CLOUDINARY CONFIG ---
cloudinary.config( 
  cloud_name = os.environ.get("CLOUDINARY_NAME"), 
  api_key = os.environ.get("CLOUDINARY_API_KEY"), 
  api_secret = os.environ.get("CLOUDINARY_API_SECRET") 
)

# --- MONGODB CONFIG ---
ca = certifi.where()
MONGO_URI = os.environ.get("MONGO_URI")
client = MongoClient(MONGO_URI, tlsCAFile=ca)
db = client['rcaps_database']  
products_col = db['products']   
orders_col = db['orders']       

# --- EMAIL CONFIG ---
MAIL_USER = os.environ.get('MAIL_USERNAME', 'ultrainstinct1596321@gmail.com')
BREVO_API_KEY = os.environ.get('BREVO_API_KEY')

def send_the_email(order_id, customer_email, total_price, address, city, phone, description, items_list):
    if not BREVO_API_KEY: return
    url = "https://api.brevo.com/v3/smtp/email"
    headers = {"accept": "application/json", "content-type": "application/json", "api-key": BREVO_API_KEY}
    
    items_text = "\n".join([f"- {item['name']} (x{item['qty']}): ₱{item['price'] * item['qty']}\n  Image: {item['image']}" for item in items_list])
    
    email_body = (
        f"Order Confirmation: {order_id}\n"
        f"-----------------------------------\n"
        f"CUSTOMER DETAILS:\n"
        f"Email: {customer_email}\n"
        f"Phone: {phone}\n"
        f"Address: {address}, {city}\n"
        f"Note: {description}\n\n"
        f"ITEMS ORDERED:\n"
        f"{items_text}\n"
        f"-----------------------------------\n"
        f"GRAND TOTAL: ₱{total_price}\n\n"
        f"Thank you for shopping with RCAPS4STREETS!"
    )
    payload = {
        "sender": {"name": "RCAPS4STREETS", "email": MAIL_USER},
        "to": [{"email": customer_email}],
        "bcc": [{"email": MAIL_USER}], 
        "subject": f"Receipt for Order {order_id}",
        "textContent": email_body
    }
    try: requests.post(url, json=payload, headers=headers, timeout=15)
    except Exception as e: print(f"Email Error: {e}")

# --- SHOP ROUTES ---

@app.route("/")
@app.route("/shop")
def home():
    all_products = list(products_col.find({}, {'_id': 0}))
    cart_count = len(session.get("cart", []))
    return render_template("index.html", products=all_products, cart_count=cart_count)

# --- NEW: ADD TO CART ROUTE (FIXES YOUR 404) ---
@app.route("/add-to-cart", methods=["POST"])
def add_to_cart():
    try:
        pid = request.form.get("id")
        if not pid:
            return jsonify({"status": "error", "message": "Missing ID"}), 400

        # Create/Get session cart
        cart = session.get("cart", [])
        
        # Verify product exists in DB before adding
        # We check both int and str versions of the ID for safety
        p = products_col.find_one({"id": int(pid)}) or products_col.find_one({"id": str(pid)})
        
        if p:
            cart.append(str(pid)) # We store the ID as a string in the session
            session["cart"] = cart
            session.modified = True
            return jsonify({"status": "success", "cart_count": len(cart)})
        
        return jsonify({"status": "error", "message": "Product not found in database"}), 404
    except Exception as e:
        print(f"Cart Error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/cart")
def view_cart():
    cart_ids = session.get("cart", [])
    cart_items = []
    total_price = 0
    counts = {str(cid): cart_ids.count(str(cid)) for cid in set(cart_ids)}
    for pid, qty in counts.items():
        try:
            # Check both int and str to find product
            p = products_col.find_one({"id": int(pid)}, {'_id': 0}) or products_col.find_one({"id": str(pid)}, {'_id': 0})
            if p:
                item = p.copy()
                item['qty'] = qty
                cart_items.append(item)
                total_price += p["price"] * qty
        except: continue
    return render_template("cart.html", cart=cart_items, total_price=total_price)

@app.route("/checkout", methods=["POST"])
def checkout():
    try:
        cart_ids = session.get("cart", [])
        if not cart_ids: return redirect(url_for("home"))
        
        items_for_receipt = []
        total_price = 0
        counts = {str(cid): cart_ids.count(str(cid)) for cid in set(cart_ids)}
        
        for pid, qty in counts.items():
            p = products_col.find_one({"id": int(pid)}, {'_id': 0}) or products_col.find_one({"id": str(pid)}, {'_id': 0})
            if p:
                total_price += p["price"] * qty
                items_for_receipt.append({
                    "name": p["name"], 
                    "price": p["price"], 
                    "qty": qty,
                    "image": p.get("image", "")
                })
        
        customer_email = request.form.get("email")
        phone = request.form.get("phone", "N/A")
        address = request.form.get("address", "N/A")
        city = request.form.get("city", "N/A")
        description = request.form.get("description", "No extra details")
        order_id = f"RCAPS-{datetime.now().year}-{random.randint(1000, 9999)}"
        
        orders_col.insert_one({
            "order_id": order_id, "email": customer_email, "phone": phone,
            "address": address, "city": city, "description": description,
            "items": items_for_receipt, "total": total_price, 
            "date": datetime.now().strftime("%b %d, %Y")
        })

        send_the_email(order_id, customer_email, total_price, address, city, phone, description, items_for_receipt)
        
        session.pop("cart", None)
        return render_template("success.html", 
                               order_id=order_id, 
                               total=total_price, 
                               email=customer_email,
                               address=address,
                               city=city,
                               items=items_for_receipt)
    except Exception as e:
        print(f"Checkout Error: {e}")
        return redirect(url_for('home'))

# --- ADMIN ROUTES ---

@app.route("/admin")
def admin():
    key = request.args.get('key')
    if key != ADMIN_PASSWORD: return "Unauthorized", 403
    all_products = list(products_col.find({}, {'_id': 0}))
    all_orders = list(orders_col.find({}, {'_id': 0}).sort("date", -1))
    return render_template("admin.html", products=all_products, orders=all_orders, admin_key=key)

@app.route("/admin/add", methods=["POST"])
def add_product():
    key = request.args.get('key')
    if key != ADMIN_PASSWORD: return "Unauthorized", 403
    
    file = request.files.get("photo")
    image_url = "https://via.placeholder.com/500" 
    
    if file:
        upload_result = cloudinary.uploader.upload(file)
        image_url = upload_result['secure_url']
    
    products_col.insert_one({
        "id": int(time.time()), 
        "name": request.form.get("name"),
        "price": int(request.form.get("price", 0)),
        "image": image_url, 
        "badge": request.form.get("badge"),
        "category": request.form.get("category")
    })
    return redirect(url_for('admin', key=key, success=True))
    @app.route("/empty-cart", methods=["POST"])
def empty_cart():
    session.pop("cart", None)
    session.modified = True
    return redirect(url_for('view_cart'))

@app.route("/admin/edit-price/<int:product_id>", methods=["POST"])
def edit_price(product_id):
    key = request.args.get('key')
    if key != ADMIN_PASSWORD: return "Unauthorized", 403
    new_price = request.form.get("new_price")
    products_col.update_one({"id": product_id}, {"$set": {"price": int(new_price)}})
    return redirect(url_for('admin', key=key))

@app.route("/admin/delete/<int:product_id>", methods=["POST"])
def delete_product(product_id):
    key = request.args.get('key')
    if key != ADMIN_PASSWORD: return "Unauthorized", 403
    products_col.delete_one({"id": product_id})
    return redirect(url_for('admin', key=key))

@app.route("/wipe_orders/<key>", methods=["POST"])
def wipe_orders(key):
    if key != ADMIN_PASSWORD: return "Unauthorized", 403
    orders_col.delete_many({})
    return redirect(url_for('admin', key=key))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)