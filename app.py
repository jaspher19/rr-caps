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

def get_clean_image_url(img_path):
    """Standardizes image paths to fix broken links in Cart and Shop."""
    if not img_path:
        return 'https://via.placeholder.com/150'
    if img_path.startswith('http'):
        return img_path
    
    clean_path = img_path.lstrip('/')
    if not clean_path.startswith('static/'):
        folder = "images/" if not clean_path.startswith('images/') else ""
        final_path = f"static/{folder}{clean_path}"
    else:
        final_path = clean_path
    
    return "/" + urllib.parse.quote(final_path)

def send_the_email(order_id, customer_email, total_price, address, city, phone, description, items_list):
    if not BREVO_API_KEY: return
    
    url = "https://api.brevo.com/v3/smtp/email"
    headers = {"accept": "application/json", "content-type": "application/json", "api-key": BREVO_API_KEY}
    
    items_html = ""
    for item in items_list:
        img_url = item.get('image', 'https://via.placeholder.com/100')
        img_src = img_url if img_url.startswith('http') else "https://via.placeholder.com/50"
        
        items_html += f"""
        <tr>
            <td style="padding: 10px; border-bottom: 1px solid #333; color: #eee;">
                <img src="{img_src}" width="40" style="vertical-align:middle; border-radius:5px; margin-right:10px;">
                {item['name']}
            </td>
            <td style="padding: 10px; border-bottom: 1px solid #333; color: #eee; text-align: center;">x{item['qty']}</td>
            <td style="padding: 10px; border-bottom: 1px solid #333; color: #eee; text-align: right;">₱{item['price'] * item['qty']}</td>
        </tr>
        """

    email_html = f"""
    <html>
    <body style="background-color: #000; color: #ffffff; font-family: 'Arial', sans-serif; padding: 20px;">
        <div style="max-width: 600px; margin: auto; background: #111; padding: 30px; border-radius: 10px; border: 1px solid #222;">
            <div style="text-align: center; margin-bottom: 20px; border-bottom: 2px solid #2ecc71; padding-bottom: 20px;">
                <h1 style="color: #2ecc71; margin: 0; letter-spacing: 2px;">ORDER RECEIVED</h1>
                <p style="color: #888;">Order ID: {order_id}</p>
            </div>
            <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
                <thead>
                    <tr style="background: #222; color: #2ecc71;">
                        <th style="padding: 10px; text-align: left;">Item</th>
                        <th style="padding: 10px; text-align: center;">Qty</th>
                        <th style="padding: 10px; text-align: right;">Price</th>
                    </tr>
                </thead>
                <tbody>{items_html}</tbody>
            </table>
            <div style="text-align: right; font-size: 20px; color: #2ecc71;">
                <strong>TOTAL: ₱{total_price}</strong>
            </div>
            <div style="margin-top: 30px; background: #1a1a1a; padding: 15px; border-radius: 8px; color: #ccc;">
                <h3 style="color: #fff; margin-top: 0;">Shipping Details</h3>
                <p><strong>Phone:</strong> {phone}</p>
                <p><strong>Address:</strong> {address}, {city}</p>
                <p style="font-style: italic;">Note: {description}</p>
            </div>
        </div>
    </body>
    </html>
    """

    payload = {
        "sender": {"name": "RCAPS4STREETS", "email": MAIL_USER},
        "to": [{"email": customer_email}],
        "bcc": [{"email": MAIL_USER}], 
        "subject": f"Receipt: {order_id} - RCAPS4STREETS",
        "htmlContent": email_html
    }
    
    try: requests.post(url, json=payload, headers=headers, timeout=15)
    except Exception as e: print(f"EMAIL ERROR: {e}")

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
                item['image'] = get_clean_image_url(item.get('image'))
                item['qty'] = qty
                item['quantity'] = qty 
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
            query = {"id": int(pid)} if pid.isdigit() else {"id": pid}
            p = products_col.find_one(query, {'_id': 0})
            if p:
                total_price += p["price"] * qty
                items_for_receipt.append({
                    "name": p["name"], 
                    "price": p["price"], 
                    "qty": qty, 
                    "image": get_clean_image_url(p.get("image"))
                })
        
        customer_email = request.form.get("email")
        phone = request.form.get("phone")
        address = request.form.get("address")
        city = request.form.get("city")
        notes = request.form.get("description", "No additional notes.")
        
        order_id = f"RCAPS-{random.randint(1000, 9999)}"
        orders_col.insert_one({
            "order_id": order_id, "email": customer_email, "phone": phone, 
            "address": address, "city": city, "items": items_for_receipt, 
            "total": total_price, "date": datetime.now().strftime("%b %d, %Y")
        })

        send_the_email(order_id, customer_email, total_price, address, city, phone, notes, items_for_receipt)
        session.pop("cart", None)

        return render_template("success.html", order_id=order_id, total=total_price, items=items_for_receipt, address=f"{address}, {city}", phone=phone)
    except Exception as e:
        return redirect(url_for('home'))

# --- ADMIN ROUTES ---

@app.route("/admin")
def admin():
    key = request.args.get('key')
    if key != ADMIN_PASSWORD: 
        return "Unauthorized", 403
    
    try:
        all_products = list(products_col.find({}))
        all_orders = list(orders_col.find({}).sort("date", -1))
        
        # Convert MongoDB ObjectId to string for safe rendering
        for p in all_products:
            if '_id' in p: p['_id'] = str(p['_id'])
        for o in all_orders:
            if '_id' in o: o['_id'] = str(o['_id'])

        return render_template("admin.html", products=all_products, orders=all_orders, admin_key=key)
    except Exception as e:
        print(f"ADMIN PAGE ERROR: {e}")
        return f"Admin Panel Error: {e}", 500

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

@app.route("/admin/edit_price/<int:product_id>", methods=["POST"])
def edit_price(product_id):
    key = request.args.get('key')
    if key != ADMIN_PASSWORD: return "Unauthorized", 403
    new_price = request.form.get("price")
    if new_price:
        products_col.update_one({"id": product_id}, {"$set": {"price": int(new_price)}})
    return redirect(url_for('admin', key=key))

@app.route("/admin/edit_badge/<int:product_id>", methods=["POST"])
def edit_badge(product_id):
    key = request.args.get('key')
    if key != ADMIN_PASSWORD: return "Unauthorized", 403
    new_badge = request.form.get("badge")
    products_col.update_one({"id": product_id}, {"$set": {"badge": new_badge}})
    return redirect(url_for('admin', key=key))

@app.route("/admin/delete/<int:product_id>", methods=["POST"])
def delete_product(product_id):
    key = request.args.get('key')
    if key != ADMIN_PASSWORD: return "Unauthorized", 403
    products_col.delete_one({"id": product_id})
    return redirect(url_for('admin', key=key))

# --- HELPER ROUTES ---

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

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))