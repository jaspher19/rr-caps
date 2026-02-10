from flask import Flask, render_template, request, redirect, session, url_for, jsonify
import requests
from werkzeug.utils import secure_filename
import random, os, time, urllib.parse
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
    if not BREVO_API_KEY: 
        print("EMAIL ERROR: No BREVO_API_KEY found.")
        return
    
    url = "https://api.brevo.com/v3/smtp/email"
    headers = {"accept": "application/json", "content-type": "application/json", "api-key": BREVO_API_KEY}
    
    items_text = "\n".join([f"- {item['name']} (x{item['qty']}): ₱{item['price'] * item['qty']}" for item in items_list])
    
    email_body = (
        f"Order Confirmation: {order_id}\n"
        f"-----------------------------------\n"
        f"Total: ₱{total_price}\n"
        f"Address: {address}, {city}\n"
        f"Phone: {phone}\n\n"
        f"Items Ordered:\n{items_text}\n\n"
        f"Thank you for shopping with RCAPS4STREETS!"
    )
    payload = {
        "sender": {"name": "RCAPS4STREETS", "email": MAIL_USER},
        "to": [{"email": customer_email}],
        "bcc": [{"email": MAIL_USER}], 
        "subject": f"Order Received - {order_id}",
        "textContent": email_body
    }
    try: 
        requests.post(url, json=payload, headers=headers, timeout=15)
    except Exception as e: 
        print(f"EMAIL ERROR: {e}")

# --- SHOP ROUTES ---

@app.route("/")
@app.route("/shop")
def home():
    all_products = list(products_col.find({}, {'_id': 0}))
    cart_count = len(session.get("cart", []))
    return render_template("index.html", products=all_products, cart_count=cart_count)

@app.route("/add-to-cart", methods=["POST"])
def add_to_cart():
    try:
        pid = request.form.get("id")
        if not pid: return jsonify({"status": "error"}), 400
        cart = session.get("cart", [])
        cart.append(str(pid))
        session["cart"] = cart
        session.modified = True
        return jsonify({"status": "success", "cart_count": len(cart)})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/cart")
def view_cart():
    cart_ids = session.get("cart", [])
    cart_items = []
    total_price = 0
    counts = {str(cid): cart_ids.count(str(cid)) for cid in set(cart_ids)}
    
    for pid, qty in counts.items():
        try:
            query = {"id": int(pid)} if pid.isdigit() else {"id": pid}
            p = products_col.find_one(query, {'_id': 0})
            
            if p:
                item = p.copy()
                img = item.get('image', '')

                # --- FIX: URL encoding for filenames with ' or spaces ---
                if not img:
                    item['image'] = 'https://via.placeholder.com/150'
                elif img.startswith('http'):
                    item['image'] = img
                else:
                    clean_path = img.lstrip('/')
                    if not clean_path.startswith('static/'):
                        folder = "images/" if not clean_path.startswith('images/') else ""
                        final_path = f"static/{folder}{clean_path}"
                    else:
                        final_path = clean_path
                    item['image'] = "/" + urllib.parse.quote(final_path)

                # --- FIX: Added 'quantity' to prevent Jinja2 UndefinedError ---
                item['qty'] = qty
                item['quantity'] = qty 
                
                cart_items.append(item)
                total_price += p["price"] * qty
        except: continue
            
    return render_template("cart.html", cart=cart_items, total_price=total_price)

@app.route("/remove-from-cart", methods=["POST"])
def remove_from_cart():
    pid = str(request.form.get("id"))
    cart = session.get("cart", [])
    if pid in cart:
        cart.remove(pid) 
        session["cart"] = cart
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
        
        items_for_receipt = []
        total_price = 0
        counts = {str(cid): cart_ids.count(str(cid)) for cid in set(cart_ids)}
        
        for pid, qty in counts.items():
            query = {"id": int(pid)} if pid.isdigit() else {"id": pid}
            p = products_col.find_one(query, {'_id': 0})
            if p:
                total_price += p["price"] * qty
                items_for_receipt.append({"name": p["name"], "price": p["price"], "qty": qty})
        
        order_id = f"RCAPS-{random.randint(1000, 9999)}"
        orders_col.insert_one({
            "order_id": order_id, "email": request.form.get("email"), 
            "items": items_for_receipt, "total": total_price, 
            "date": datetime.now().strftime("%b %d, %Y")
        })

        send_the_email(order_id, request.form.get("email"), total_price, 
                       request.form.get("address"), request.form.get("city"), 
                       request.form.get("phone"), "", items_for_receipt)
        
        session.pop("cart", None)
        return render_template("success.html", order_id=order_id, total=total_price)
    except:
        return redirect(url_for('home'))

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
        res = cloudinary.uploader.upload(file)
        image_url = res['secure_url']
    
    products_col.insert_one({
        "id": int(time.time()), "name": request.form.get("name"),
        "price": int(request.form.get("price", 0)), "image": image_url, 
        "badge": request.form.get("badge"), "category": request.form.get("category")
    })
    return redirect(url_for('admin', key=key))

@app.route("/admin/delete/<int:product_id>", methods=["POST"])
def delete_product(product_id):
    key = request.args.get('key')
    if key != ADMIN_PASSWORD: return "Unauthorized", 403
    products_col.delete_one({"id": product_id})
    return redirect(url_for('admin', key=key))

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))