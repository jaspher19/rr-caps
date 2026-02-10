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
    if not img_path: return 'https://via.placeholder.com/150'
    if img_path.startswith('http'): return img_path
    clean_path = img_path.lstrip('/')
    if not clean_path.startswith('static/'):
        folder = "images/" if not clean_path.startswith('images/') else ""
        final_path = f"static/{folder}{clean_path}"
    else: final_path = clean_path
    return "/" + urllib.parse.quote(final_path)

def send_the_email(order_id, customer_email, customer_name, total_price, address, phone, items_list, payment_method, proof_url=None):
    if not BREVO_API_KEY: return
    url = "https://api.brevo.com/v3/smtp/email"
    headers = {"accept": "application/json", "content-type": "application/json", "api-key": BREVO_API_KEY}
    
    # NEW: Determine status for the email stamp
    payment_status = "PAID" if payment_method == "GCash" else "TO PAY"
    status_color = "#00ff00" if payment_status == "PAID" else "#ffaa00"

    items_html = ""
    for item in items_list:
        img_src = item.get('image', 'https://via.placeholder.com/50')
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

    proof_link_html = f"<p style='color: #00ffff;'><strong>Proof:</strong> <a href='{proof_url}' style='color: #00ffff;'>View Receipt</a></p>" if proof_url else ""

    email_html = f"""
    <html>
        <body style='background:#000; color:#fff; font-family: sans-serif; padding: 20px;'>
            <div style="border: 2px solid {status_color}; color: {status_color}; padding: 10px; display: inline-block; margin-bottom: 20px; font-weight: bold; text-transform: uppercase;">
                {payment_status}
            </div>
            <h2 style="color: #fff;">ORDER CONFIRMED</h2>
            <p>Reference: {order_id}</p>
            <p><strong>Customer:</strong> {customer_name}</p>
            <p><strong>Payment Method:</strong> {payment_method}</p>
            {proof_link_html}
            <hr style="border: 1px solid #333;">
            <table width="100%" style="color: #eee;">{items_html}</table>
            <p><strong>Total Due: ₱{total_price}</strong></p>
            <p><strong>Shipping to:</strong> {address}</p>
            <p><strong>Phone:</strong> {phone}</p>
        </body>
    </html>
    """
    
    payload = {
        "sender": {"name": "RCAPS4STREETS", "email": MAIL_USER},
        "to": [{"email": customer_email}],
        "bcc": [{"email": MAIL_USER}], 
        "subject": f"[{payment_status}] Receipt: {order_id} - {customer_name}",
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
        p['stock'] = p.get('stock', 0)
    cart_count = len(session.get("cart", []))
    return render_template("index.html", products=all_products, cart_count=cart_count)

@app.route("/add-to-cart", methods=["POST"])
def add_to_cart():
    try:
        pid = request.form.get("id")
        query = {"id": int(pid)} if pid.isdigit() else {"id": pid}
        product = products_col.find_one(query)
        
        if product and product.get('stock', 0) <= 0:
            return jsonify({"status": "error", "message": "Item Out of Stock"}), 400

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
    counts = {str(cid): cart_ids.count(str(cid)) for cid in set(cart_ids)}
    
    for pid, qty in counts.items():
        query = {"id": int(pid)} if pid.isdigit() else {"id": pid}
        p = products_col.find_one(query, {'_id': 0})
        if p:
            item = p.copy()
            item['image'] = get_clean_image_url(item.get('image'))
            item['quantity'] = qty
            cart_items.append(item)
            total_price += p["price"] * qty
    return render_template("cart.html", cart=cart_items, total_price=total_price)

@app.route("/checkout", methods=["POST"])
def checkout():
    try:
        cart_ids = session.get("cart", [])
        if not cart_ids: return redirect(url_for('home'))

        customer_name = request.form.get("customer_name")
        items_for_receipt = []
        total_price = 0
        counts = {str(cid): cart_ids.count(str(cid)) for cid in set(cart_ids)}
        
        for pid, qty in counts.items():
            query = {"id": int(pid)} if pid.isdigit() else {"id": pid}
            p = products_col.find_one(query)
            if p:
                current_stock = p.get('stock', 0)
                new_stock = max(0, current_stock - qty)
                products_col.update_one({"id": p['id']}, {"$set": {"stock": new_stock}})

                total_price += p["price"] * qty
                items_for_receipt.append({
                    "name": p["name"], 
                    "price": p["price"], 
                    "quantity": qty,
                    "image": get_clean_image_url(p.get("image"))
                })
        
        full_address = f"{request.form.get('address')}, {request.form.get('city')}, {request.form.get('zip')}"
        order_id = f"RCAPS-{random.randint(1000, 9999)}"
        payment_choice = request.form.get("payment_method", "Cash on Delivery")

        # NEW: Logic for Receipt Status
        payment_status = "PAID" if payment_choice == "GCash" else "TO PAY"

        proof_url = None
        if payment_choice == "GCash":
            file = request.files.get("payment_proof")
            if file and file.filename != '':
                upload_result = cloudinary.uploader.upload(file, folder="gcash_receipts")
                proof_url = upload_result.get("secure_url")
        
        order_data = {
            "order_id": order_id, 
            "customer_name": customer_name,
            "email": request.form.get("email"),
            "phone": request.form.get("phone"),
            "address": full_address,
            "total": total_price, 
            "payment_method": payment_choice,
            "payment_status": payment_status, # NEW: Save status to DB
            "payment_proof": proof_url,
            "date": datetime.now().strftime("%b %d, %Y %I:%M %p"), 
            "items": items_for_receipt
        }
        
        orders_col.insert_one(order_data)
        
        send_the_email(
            order_id, 
            order_data['email'], 
            customer_name, 
            total_price, 
            full_address, 
            order_data['phone'], 
            items_for_receipt, 
            payment_choice, 
            proof_url
        )
        
        session.pop("cart", None)
        session.modified = True
        
        return render_template("success.html", **order_data)
    except Exception as e:
        print(f"Checkout Error: {e}")
        return redirect(url_for('home'))

# --- ADMIN ROUTES ---

@app.route("/admin")
def admin():
    key = request.args.get('key')
    if key != ADMIN_PASSWORD: return "Unauthorized", 403
    try:
        all_products = list(products_col.find({}))
        all_orders = list(orders_col.find({}).sort("_id", -1))
        for p in all_products:
            p['_id'] = str(p['_id'])
            p['image'] = get_clean_image_url(p.get('image'))
            p['stock'] = p.get('stock', 0)
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
        "id": int(time.time()), 
        "name": request.form.get("name"),
        "price": int(request.form.get("price", 0)), 
        "stock": int(request.form.get("stock", 0)),
        "image": image_url, 
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
        products_col.update_one({"id": product_id}, {"$set": {"price": int(new_price)}})
    return redirect(url_for('admin', key=key))

@app.route("/admin/edit_stock/<int:product_id>", methods=["POST"])
def edit_stock(product_id):
    key = request.args.get('key')
    if key != ADMIN_PASSWORD: return "Unauthorized", 403
    new_stock = request.form.get("new_stock")
    if new_stock:
        products_col.update_one({"id": product_id}, {"$set": {"stock": int(new_stock)}})
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