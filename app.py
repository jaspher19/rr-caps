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
        img_src = item.get('image', 'https://via.placeholder.com/50')
        # Using 'quantity' to match the updated dictionary keys
        qty = item.get('quantity', 1)
        items_html += f"""
        <tr>
            <td style="padding: 10px; border-bottom: 1px solid #333; color: #eee;">
                <img src="{img_src}" width="40" style="vertical-align:middle; border-radius:5px; margin-right:10px;">
                {item['name']}
            </td>
            <td style="padding: 10px; border-bottom: 1px solid #333; color: #eee; text-align: center;">x{qty}</td>
            <td style="padding: 10px; border-bottom: 1px solid #333; color: #eee; text-align: right;">₱{item['price'] * qty}</td>
        </tr>
        """

    email_html = f"<html><body style='background:#000; color:#fff;'>Order: {order_id} Details: {items_html} </body></html>"
    payload = {
        "sender": {"name": "RCAPS4STREETS", "email": MAIL_USER},
        "to": [{"email": customer_email}],
        "bcc": [{"email": MAIL_USER}], 
        "subject": f"Receipt: {order_id}",
        "htmlContent": email_html
    }
    try: requests.post(url, json=payload, headers=headers, timeout=15)
    except: pass

# --- SHOP ROUTES ---

@app.route("/")
@app.route("/shop")
def home():
    all_products = list(products_col.find({}, {'_id': 0}))
    for p in all_products:
        p['image'] = get_clean_image_url(p.get('image'))
    cart_count = len(session.get("cart", []))
    return render_template("index.html", products=all_products, cart_count=cart_count)

@app.route("/add-to-cart", methods=["POST"])
def add_to_cart():
    try:
        pid = request.form.get("id")
        cart = session.get("cart", [])
        cart.append(str(pid))
        session["cart"] = cart
        session.modified = True
        return jsonify({"status": "success", "cart_count": len(cart)})
    except:
        return jsonify({"status": "error"}), 500

@app.route("/cart")
def view_cart():
    cart_ids = session.get("cart", [])
    cart_items = []
    total_price = 0
    # Grouping IDs and counting them
    counts = {str(cid): cart_ids.count(str(cid)) for cid in set(cart_ids)}
    
    for pid, qty in counts.items():
        query = {"id": int(pid)} if pid.isdigit() else {"id": pid}
        p = products_col.find_one(query, {'_id': 0})
        if p:
            item = p.copy()
            item['image'] = get_clean_image_url(item.get('image'))
            # CRITICAL FIX: Named 'quantity' to match cart.html template
            item['quantity'] = qty
            cart_items.append(item)
            total_price += p["price"] * qty
    return render_template("cart.html", cart=cart_items, total_price=total_price)

@app.route("/checkout", methods=["POST"])
def checkout():
    try:
        cart_ids = session.get("cart", [])
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
                    "quantity": qty, # Consistent naming
                    "image": get_clean_image_url(p.get("image"))
                })
        
        order_id = f"RCAPS-{random.randint(1000, 9999)}"
        order_data = {
            "order_id": order_id, 
            "email": request.form.get("email"),
            "total": total_price, 
            "date": datetime.now().strftime("%b %d, %Y"), 
            "items": items_for_receipt
        }
        orders_col.insert_one(order_data)
        
        # Email customer
        send_the_email(order_id, order_data['email'], total_price, "", "", "", "", items_for_receipt)
        
        session.pop("cart", None)
        return render_template("success.html", order_id=order_id, total=total_price)
    except: return redirect(url_for('home'))

# --- ADMIN ROUTES ---

@app.route("/admin")
def admin():
    key = request.args.get('key')
    if key != ADMIN_PASSWORD: return "Unauthorized", 403
    try:
        all_products = list(products_col.find({}))
        all_orders = list(orders_col.find({}).sort("date", -1))
        for p in all_products:
            p['_id'] = str(p['_id'])
            p['image'] = get_clean_image_url(p.get('image'))
        for o in all_orders:
            o['_id'] = str(o['_id'])
        return render_template("admin.html", products=all_products, orders=all_orders, admin_key=key)
    except Exception as e:
        return f"Error: {e}", 500

@app.route("/admin/add", methods=["POST"])
def add_product():
    key = request.args.get('key')
    if key != ADMIN_PASSWORD: return "Unauthorized", 403
    file = request.files.get("photo")
    image_url = cloudinary.uploader.upload(file)['secure_url'] if file else "https://via.placeholder.com/500"
    products_col.insert_one({
        "id": int(time.time()), "name": request.form.get("name"),
        "price": int(request.form.get("price", 0)), "image": image_url, 
        "badge": request.form.get("badge"), "category": request.form.get("category")
    })
    return redirect(url_for('admin', key=key))

@app.route("/admin/wipe_orders", methods=["POST"])
def wipe_orders():
    key = request.args.get('key')
    if key != ADMIN_PASSWORD: return "Unauthorized", 403
    orders_col.delete_many({})
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
    session.modified = True
    return redirect(url_for('view_cart'))

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))