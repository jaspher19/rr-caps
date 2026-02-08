from flask import Flask, render_template, request, redirect, session, url_for, jsonify
from flask_mail import Mail, Message
from werkzeug.utils import secure_filename
import random, os, json, time, threading
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "rcaps4street_ultra_secret_key")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "STREET_BOSS_2026") 

UPLOAD_FOLDER = 'static/images/products'
PRODUCT_FILE = 'products.json'
ORDER_FILE = 'orders.json'
SHOP_EMAIL = 'jasphertampos5@gmail.com' 

if not os.path.exists(UPLOAD_FOLDER): os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# --- ULTRA STABLE EMAIL CONFIG ---
app.config.update(
    MAIL_SERVER='smtp.gmail.com',
    MAIL_PORT=587,
    MAIL_USE_TLS=True,
    MAIL_USE_SSL=False,
    MAIL_USERNAME=SHOP_EMAIL,
    # MUST BE A 16-CHARACTER GMAIL APP PASSWORD
    MAIL_PASSWORD=os.environ.get('MAIL_PASSWORD', 'bsjbptoaxqzjoern'),
    MAIL_DEFAULT_SENDER=SHOP_EMAIL,
    MAIL_ASCII_ATTACHMENTS=False
)
mail = Mail(app)

# --- ASYNC EMAIL HELPER WITH RETRY LOGIC ---
def send_async_email(app, msg):
    with app.app_context():
        for attempt in range(3):  # Try 3 times before giving up
            try:
                mail.send(msg)
                print(f">>> EMAIL SENT SUCCESSFULLY ON ATTEMPT {attempt + 1}")
                return 
            except Exception as e:
                print(f">>> Attempt {attempt + 1} failed: {e}")
                time.sleep(2) # Wait 2 seconds before trying again
        print(">>> ALL EMAIL ATTEMPTS FAILED.")

# --- UTILS ---
def load_products():
    if not os.path.exists(PRODUCT_FILE): return []
    try:
        with open(PRODUCT_FILE, 'r') as f: return json.load(f)
    except: return []

def save_products(products):
    with open(PRODUCT_FILE, 'w') as f: json.dump(products, f, indent=4)

def load_orders():
    if not os.path.exists(ORDER_FILE): return []
    try:
        with open(ORDER_FILE, 'r') as f: return json.load(f)
    except: return []

def save_order_to_history(order_data):
    try:
        orders = load_orders()
        orders.append(order_data)
        with open(ORDER_FILE, 'w') as f: json.dump(orders, f, indent=4)
    except Exception as e: print(f"File Error: {e}")

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
        "image": image_path
    })
    save_products(products)
    return redirect(url_for('admin', key=key))

@app.route("/admin/delete/<int:product_id>", methods=["POST"])
def delete_product(product_id):
    key = request.args.get('key')
    if key != ADMIN_PASSWORD: return "Unauthorized", 403
    products = [p for p in load_products() if p['id'] != product_id]
    save_products(products)
    return redirect(url_for('admin', key=key))

@app.route("/cart")
def cart():
    products = load_products()
    cart_ids = session.get("cart", [])
    counts = {str(cid): cart_ids.count(cid) for cid in set(cart_ids)}
    cart_items = []
    total_price = 0
    for pid, qty in counts.items():
        for p in products:
            if str(p["id"]) == pid:
                item = p.copy(); item['quantity'] = qty
                cart_items.append(item); total_price += p["price"] * qty
    return render_template("cart.html", cart=cart_items, total_price=total_price)

@app.route("/add-to-cart", methods=["POST"])
def add_to_cart():
    if "cart" not in session: session["cart"] = []
    session["cart"].append(str(request.form.get("id")))
    session.modified = True
    return jsonify({"status": "success", "cart_count": len(session["cart"])})

@app.route("/remove-from-cart", methods=["POST"])
def remove_from_cart():
    cart = session.get("cart", [])
    pid = str(request.form.get("product_id"))
    if pid in cart: cart.remove(pid); session["cart"] = cart; session.modified = True
    return redirect(url_for('cart'))

@app.route("/empty-cart", methods=["POST"])
def empty_cart():
    session.pop("cart", None); return redirect(url_for('cart'))

@app.route("/checkout", methods=["POST"])
def checkout():
    try:
        cart_ids = session.get("cart", [])
        if not cart_ids: return redirect(url_for("home"))
        
        customer_email = request.form.get("email")
        order_id = f"RR-{random.randint(1000, 9999)}"
        
        # Save order info locally
        save_order_to_history({
            "order_id": order_id, 
            "email": customer_email,
            "date": datetime.now().strftime("%b %d, %Y")
        })
        
        # Clear cart
        session.pop("cart", None)
        session.modified = True

        # Prepare Message
        msg = Message(
            subject=f"Order {order_id} Confirmed",
            sender=SHOP_EMAIL,
            recipients=[customer_email, SHOP_EMAIL]
        )
        msg.body = f"Thank you for your order! Your Order ID is {order_id}."

        # Start Async Thread
        threading.Thread(target=send_async_email, args=(app, msg)).start()

        return render_template("success.html", order_id=order_id)

    except Exception as e:
        print(f"Checkout Error: {e}")
        return redirect(url_for('home'))

if __name__ == "__main__":
    app.run(debug=True)