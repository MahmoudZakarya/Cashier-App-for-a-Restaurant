from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    abort,
    flash,
    session,
    g,
    jsonify,
)
from flask_sqlalchemy import SQLAlchemy
from waitress import serve
import webbrowser
import threading
from datetime import datetime, UTC, timedelta, date
import os, signal
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from dotenv import load_dotenv
from flask_migrate import Migrate
from config import DevConfig, ProdConfig
from collections import Counter


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if g.user is None:
            flash("الرجاء تسجيل الدخول أولًا", "danger")
            return redirect(url_for("login"))
        return f(*args, **kwargs)

    return decorated_function


# Load .env file (default to .env)
env_file = os.environ.get("ENV_FILE", ".env")
load_dotenv(env_file)


app = Flask(__name__)
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.secret_key = os.getenv("SECRET_KEY", "fallback-secret")
if os.getenv("FLASK_ENV") == "production":
    app.config.from_object(ProdConfig)
else:
    app.config.from_object(DevConfig)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

migrate = Migrate(app, db)


@app.template_filter("ar_date")
def ar_date(value):
    if not value:
        return ""
    days = {
        "Monday": "الاثنين",
        "Tuesday": "الثلاثاء",
        "Wednesday": "الأربعاء",
        "Thursday": "الخميس",
        "Friday": "الجمعة",
        "Saturday": "السبت",
        "Sunday": "الأحد",
    }

    months = {
        1: "يناير",
        2: "فبراير",
        3: "مارس",
        4: "أبريل",
        5: "مايو",
        6: "يونيو",
        7: "يوليو",
        8: "أغسطس",
        9: "سبتمبر",
        10: "أكتوبر",
        11: "نوفمبر",
        12: "ديسمبر",
    }

    day_name = days[value.strftime("%A")]
    month_name = months[value.month]

    return f"{day_name}، {value.day:02d} {month_name} {value.year} - {value.strftime('%I:%M %p').replace('AM','ص').replace('PM','م')}"


# ======================= MODELS =======================
class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False, unique=True)
    type = db.Column(db.String(100), default="غير محدد")
    quantity_type = db.Column(db.String(50), default="كيلو")
    quantity = db.Column(db.Float, default=0.0)
    buy_price = db.Column(db.Float, default=0.0)


class Safe(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    balance = db.Column(db.Float, default=0.0)


class Purchase(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False)
    product = db.relationship("Product")
    quantity = db.Column(db.Float, nullable=False)
    unit_price = db.Column(db.Float, nullable=False)
    total_cost = db.Column(db.Float, nullable=False)
    date = db.Column(db.DateTime, default=datetime.now)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    user = db.relationship("User")


class ManualConsumption(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False)
    product = db.relationship("Product")
    quantity = db.Column(db.Float, nullable=False)
    date = db.Column(db.DateTime, default=datetime.now)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    user = db.relationship("User")


class Meal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False, unique=True)
    description = db.Column(db.String(500), nullable=False)
    sale_price = db.Column(db.Float, nullable=False)

    def calculate_cost(self):
        total_cost = 0
        for comp in self.components:
            if comp.product.buy_price:
                total_cost += comp.quantity * comp.product.buy_price
        return total_cost


class MealComponent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    meal_id = db.Column(db.Integer, db.ForeignKey("meal.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False)

    product = db.relationship("Product")
    meal = db.relationship("Meal", backref=db.backref("components", lazy=True))

    quantity = db.Column(db.Float, nullable=False)


class Sale(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    daily_order_number = db.Column(db.Integer, default=1)
    description = db.Column(db.String(250))
    note = db.Column(db.String(250))
    total_amount = db.Column(db.Float, nullable=False)
    date = db.Column(db.DateTime, default=datetime.now)
    sale_type = db.Column(db.String(20), default="normal")
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    user = db.relationship("User")


class SaleItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey("sale.id"), nullable=False)
    meal_id = db.Column(db.Integer, db.ForeignKey("meal.id"), nullable=False)
    sale = db.relationship("Sale", backref=db.backref("items", lazy=True))
    meal = db.relationship("Meal")


class Fund(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    amount = db.Column(db.Float, nullable=False)
    date = db.Column(db.DateTime, default=datetime.now)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    user = db.relationship("User")


class Withdrawal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    amount = db.Column(db.Float, nullable=False)
    note = db.Column(db.String(250))
    date = db.Column(db.DateTime, default=datetime.now)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    user = db.relationship("User")


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


def calculate_meal_cost(meal):
    total_cost = 0
    for comp in meal.components:
        if comp.product.buy_price > 0:
            total_cost += comp.quantity * comp.product.buy_price
    return total_cost


def calculate_cost_of_sales():
    total_cost = 0
    sales = SaleItem.query.all()
    for item in sales:
        meal_cost = calculate_meal_cost(item.meal)
        total_cost += meal_cost
    return total_cost


# ======================= HELPERS =======================
def get_safe():
    s = Safe.query.first()
    if not s:
        s = Safe(balance=0.0)
        db.session.add(s)
        db.session.commit()
    return s


# ======================= ROUTES =======================
@app.route("/")
@login_required
def index():
    safe = get_safe()
    total_purchases = db.session.query(db.func.sum(Purchase.total_cost)).scalar() or 0
    total_sales = db.session.query(db.func.sum(Sale.total_amount)).scalar() or 0
    profit_estimate = total_sales - total_purchases

    # Calculate cost of consumed ingredients
    cost_of_consumed = 0
    for item in SaleItem.query.all():
        cost_of_consumed += calculate_meal_cost(item.meal)

    profit_consumption = total_sales - cost_of_consumed

    return render_template(
        "index.html",
        safe_balance=safe.balance,
        total_purchases=total_purchases,
        total_sales=total_sales,
        profit_estimate=profit_estimate,
        profit_consumption=round(profit_consumption, 2),  # pass to template
    )


@app.route("/products")
@login_required
def products():
    return render_template("products.html", products=Product.query.all())


@app.route("/print_warehouse")
@login_required
def print_warehouse():
    products = Product.query.all()

    # حساب القيم
    total_value = 0
    for p in products:
        total_value += p.quantity * p.buy_price

    return render_template(
        "warehouse_print.html", products=products, total_value=round(total_value, 2)
    )


@app.route("/purchases")
@login_required
def purchases():
    today = date.today().isoformat()

    start = request.args.get("from", today)
    end = request.args.get("to", today)

    start_dt = datetime.fromisoformat(start)
    end_dt = datetime.fromisoformat(end) + timedelta(days=1)

    purchases = (
        Purchase.query.filter(Purchase.date >= start_dt, Purchase.date <= end_dt)
        .order_by(Purchase.date.desc())
        .all()
    )

    total_cost = sum(p.total_cost for p in purchases)

    # Fetch unique product names and types
    product_names = [p.name for p in Product.query.order_by(Product.name).all()]
    product_types = list(set(p.type for p in Product.query.all()))

    return render_template(
        "purchases.html",
        purchases=purchases,
        start=start,
        end=end,
        total_cost=round(total_cost, 2),
        product_names=product_names,
        product_types=product_types,
    )


@app.route("/print_purchases")
@login_required
def print_purchases():
    start = request.args.get("start")
    end = request.args.get("end")

    today = date.today().isoformat()
    start = start or today
    end = end or today

    start_dt = datetime.fromisoformat(start)
    end_dt = datetime.fromisoformat(end) + timedelta(days=1)

    purchases = (
        Purchase.query.filter(Purchase.date >= start_dt, Purchase.date <= end_dt)
        .order_by(Purchase.date.desc())
        .all()
    )

    return render_template(
        "purchases_print.html", purchases=purchases, start=start, end=end
    )


@app.route("/add_purchase", methods=["POST"])
@login_required
def add_purchase():
    if not g.user:
        flash("الرجاء تسجيل الدخول أولًا", "danger")
        return redirect(url_for("login"))

    name = request.form["name"].strip()
    type_ = request.form.get("type", "غير محدد").strip()
    quantity_type = request.form.get("quantity_type", "كيلو").strip()

    try:
        quantity = float(request.form["quantity"])
        unit_price = float(request.form["unit_price"])
    except:
        flash("الرجاء إدخال أرقام صحيحة.", "danger")
        return redirect(url_for("purchases"))

    total_cost = quantity * unit_price
    safe = get_safe()

    if safe.balance < total_cost:
        flash("الرصيد غير كافٍ.", "danger")
        return redirect(url_for("purchases"))

    product = Product.query.filter_by(name=name).first()
    if product:
        product.quantity += quantity
        product.buy_price = unit_price
    else:
        product = Product(
            name=name,
            type=type_,
            quantity_type=quantity_type,
            quantity=quantity,
            buy_price=unit_price,
        )
        db.session.add(product)
        db.session.flush()

    db.session.add(
        Purchase(
            product_id=product.id,
            quantity=quantity,
            unit_price=unit_price,
            total_cost=total_cost,
            user_id=g.user.id,
        )
    )
    safe.balance -= total_cost
    db.session.commit()

    flash("✅ تمت الإضافة", "success")
    return redirect(url_for("purchases"))


@app.route("/consume", methods=["GET", "POST"])
@login_required
def consume():
    if request.method == "POST":
        product_id = request.form["product_id"]
        quantity = float(request.form["quantity"])
        product = Product.query.get(product_id)

        if product.quantity < quantity:
            flash("لا توجد كمية كافية في المخزن", "danger")
            return redirect(url_for("consume"))

        product.quantity -= quantity
        db.session.add(
            ManualConsumption(
                product_id=product_id,
                quantity=quantity,
                user_id=g.user.id,
                date=datetime.now(),
            )
        )
        db.session.commit()
        flash("تم صرف المكونات بنجاح", "success")
        return redirect(url_for("consume"))

    today = date.today().isoformat()
    start = request.args.get("from", today)
    end = request.args.get("to", today)

    start_dt = datetime.fromisoformat(start)
    end_dt = datetime.fromisoformat(end) + timedelta(days=1)

    consumptions = (
        ManualConsumption.query.filter(
            ManualConsumption.date >= start_dt, ManualConsumption.date <= end_dt
        )
        .order_by(ManualConsumption.date.desc())
        .all()
    )

    products = Product.query.order_by(Product.name).all()

    return render_template(
        "consume.html",
        products=products,
        consumptions=consumptions,
        start=start,
        end=end,
    )


@app.route("/sales")
@login_required
def sales():
    meals = Meal.query.all()
    meals = [
        {
            "id": m.id,
            "name": m.name,
            "description": m.description,
            "sale_price": float(m.sale_price),
        }
        for m in meals
    ]

    today = date.today().isoformat()
    start = request.args.get("from", today)
    end = request.args.get("to", today)

    sale_type_filters = request.args.getlist("type")

    today = datetime.now().date()

    last_sale_today = (
        Sale.query.filter(db.func.date(Sale.date) == today)
        .order_by(Sale.daily_order_number.desc())
        .first()
    )

    if last_sale_today and last_sale_today.daily_order_number:
        next_number = last_sale_today.daily_order_number + 1
    else:
        next_number = 1

    query = Sale.query.filter(
        Sale.date >= datetime.fromisoformat(start),
        Sale.date <= datetime.fromisoformat(end) + timedelta(days=1),
    )

    # ✅ Apply sale type filters if any selected
    if sale_type_filters:
        query = query.filter(Sale.sale_type.in_(sale_type_filters))

    return render_template(
        "sales.html",
        meals=meals,
        sales=query.order_by(Sale.id.desc()).all(),
        request=request,
        today=today,
        start=start,
        end=end,
    )


@app.route("/add_sale", methods=["POST"])
@login_required
def add_sale():
    if not g.user:
        return jsonify({"error": "الرجاء تسجيل الدخول أولًا"}), 403

    meal_ids = request.form.get("meal_ids").split(",")
    total_amount = float(request.form.get("total_amount"))
    sale_type = request.form.get("sale_type", "normal").strip().lower()

    today = datetime.now().date()

    last_sale_today = (
        Sale.query.filter(db.func.date(Sale.date) == today)
        .order_by(Sale.daily_order_number.desc())
        .first()
    )

    next_number = (last_sale_today.daily_order_number + 1) if last_sale_today else 1
    print(db.session.get(Meal, int(mid)) for mid in meal_ids)
    meal_objects = [db.session.get(Meal, int(mid)) for mid in meal_ids]

    # ✅ 1) Calculate total required ingredients
    required = {}  # pid -> total quantity needed

    for meal in meal_objects:
        for comp in meal.components:
            if comp.product_id not in required:
                required[comp.product_id] = comp.quantity
            else:
                required[comp.product_id] += comp.quantity

    # ✅ 2) Check stock BEFORE committing anything
    if sale_type == "normal":
        for pid, qty_needed in required.items():
            product = db.session.get(Product, pid)
            if product.quantity < qty_needed:
                return (
                    jsonify({"error": f"❌ لا يوجد كمية كافية من {product.name}"}),
                    400,
                )
    # ✅ 3) Create sale
    note = request.form.get("note", "").strip()

    sale_description = " + ".join([m.name for m in meal_objects])
    note = request.form.get("note", "").strip()

    sale_description = " + ".join([m.name for m in meal_objects])

    sale = Sale(
        daily_order_number=next_number,
        total_amount=total_amount * (-1 if sale_type in ["return", "damage"] else 1),
        user_id=g.user.id,
        description=sale_description,
        note=note,  # ✅ Save directly
        sale_type=sale_type,
    )

    db.session.add(sale)

    safe = get_safe()

    if sale_type == "normal":
        safe.balance += total_amount
    else:
        safe.balance -= total_amount

    # ✅ 4) Deduct / restore stock safely after validation
    for meal in meal_objects:
        db.session.add(SaleItem(sale_id=sale.id, meal_id=meal.id))

    for pid, qty_needed in required.items():
        product = db.session.get(Product, pid)
        if sale_type == "normal":
            product.quantity -= qty_needed
        elif sale_type == "return":
            product.quantity += qty_needed

    db.session.commit()

    return jsonify({"sale_id": sale.id})


@app.route("/receipt/<int:sale_id>")
@login_required
def receipt_page(sale_id):
    sale = Sale.query.get_or_404(sale_id)
    grouped = {}
    for item in sale.items:
        meal = item.meal
        if meal.id not in grouped:
            grouped[meal.id] = {"name": meal.name, "price": meal.sale_price, "qty": 1}
        else:
            grouped[meal.id]["qty"] += 1

    return render_template("receipt.html", sale=sale, grouped=grouped.values())


@app.route("/print_sales")
@login_required
def print_sales():
    start = request.args.get("start")
    end = request.args.get("end")
    sale_type_filters = request.args.getlist("type")

    start_dt = datetime.fromisoformat(start)
    end_dt = datetime.fromisoformat(end) + timedelta(days=1)

    query = Sale.query.filter(Sale.date >= start_dt, Sale.date <= end_dt)

    if sale_type_filters:
        query = query.filter(Sale.sale_type.in_(sale_type_filters))

    sales = query.order_by(Sale.id.desc()).all()

    return render_template("sales_print.html", sales=sales, start=start, end=end)


@app.route("/safe")
@login_required
def safe_view():
    safe = get_safe()

    # Calculate total revenue (sales - cost of consumed ingredients)
    total_sales = db.session.query(db.func.sum(Sale.total_amount)).scalar() or 0
    cost_of_consumed = 0
    for item in SaleItem.query.all():
        cost_of_consumed += calculate_meal_cost(item.meal)
    revenue_balance = total_sales - cost_of_consumed

    withdrawals = Withdrawal.query.order_by(Withdrawal.date.desc()).all()
    funds_added = Fund.query.order_by(Fund.date.desc()).all()

    return render_template(
        "safe.html",
        safe=safe,
        revenue_balance=round(revenue_balance, 2),
        withdrawals=withdrawals,
        funds_added=funds_added,
    )


@app.route("/add_funds", methods=["POST"])
@login_required
def add_funds():
    if not g.user:
        flash("الرجاء تسجيل الدخول أولًا", "danger")
        return redirect(url_for("login"))

    amount = float(request.form["amount"])
    s = get_safe()
    s.balance += amount

    db.session.add(Fund(amount=amount, user_id=g.user.id))
    db.session.commit()
    flash(f"✅ تم إضافة {amount} جنيه", "success")
    return redirect(url_for("safe_view"))


@app.route("/withdraw", methods=["POST"])
@login_required
def withdraw():
    if not g.user:
        flash("الرجاء تسجيل الدخول أولًا", "danger")
        return redirect(url_for("login"))

    amount = float(request.form["amount"])
    note = request.form.get("note", "").strip()
    safe = get_safe()

    if amount <= 0:
        flash("الرجاء إدخال مبلغ صالح.", "danger")
        return redirect(url_for("safe_view"))

    if safe.balance < amount:
        flash("الرصيد غير كافٍ.", "danger")
        return redirect(url_for("safe_view"))

    safe.balance -= amount
    db.session.add(Withdrawal(amount=amount, note=note, user_id=g.user.id))
    db.session.commit()
    flash(f"✅ تم سحب {amount} جنيه بنجاح.", "success")
    return redirect(url_for("safe_view"))


@app.route("/menu")
@login_required
def menu():
    meals = Meal.query.all()
    products = Product.query.all()

    # Add calculated fields to each meal object
    for meal in meals:
        cost = calculate_meal_cost(meal)
        meal.cost = round(cost, 2)
        meal.profit = round(meal.sale_price - cost, 2)

    return render_template("menu.html", meals=meals, products=products)


@app.route("/add_meal", methods=["POST"])
@login_required
def add_meal():
    meal = Meal(
        name=request.form["name"],
        description=request.form["description"],
        sale_price=float(request.form["sale_price"]),
    )
    db.session.add(meal)
    db.session.flush()

    for pid, qty in zip(
        request.form.getlist("product_id[]"), request.form.getlist("quantity[]")
    ):
        if float(qty) > 0:
            db.session.add(
                MealComponent(meal_id=meal.id, product_id=int(pid), quantity=float(qty))
            )

    db.session.commit()
    flash("✅ تمت إضافة الوجبة", "success")
    return redirect(url_for("menu"))


@app.route("/edit_meal/<int:meal_id>", methods=["POST"])
@login_required
def edit_meal(meal_id):
    meal = Meal.query.get_or_404(meal_id)

    # Update meal basic info
    meal.name = request.form["name"]
    meal.description = request.form["description"]
    meal.sale_price = float(request.form["sale_price"])

    # 1) Delete old components
    MealComponent.query.filter_by(meal_id=meal.id).delete()

    # 2) Add new components from form
    product_ids = request.form.getlist("product_id[]")
    quantities = request.form.getlist("quantity[]")

    for product_id, quantity in zip(product_ids, quantities):
        if product_id and quantity:
            comp = MealComponent(
                meal_id=meal.id, product_id=int(product_id), quantity=float(quantity)
            )
            db.session.add(comp)

    # 3) Recalculate cost and profit
    meal.calculate_cost()  # ← مهم جداً
    db.session.commit()

    flash("تم تعديل الوجبة بنجاح", "success")
    return redirect(url_for("menu"))


@app.route("/delete_meal/<int:meal_id>")
@login_required
def delete_meal(meal_id):
    meal = Meal.query.get_or_404(meal_id)

    # Delete related meal components and sale items safely
    MealComponent.query.filter_by(meal_id=meal.id).delete()
    SaleItem.query.filter_by(meal_id=meal.id).delete()

    db.session.delete(meal)
    db.session.commit()

    flash("🗑️ تم حذف الوجبة", "success")
    return redirect(url_for("menu"))


@app.route("/report", methods=["GET"])
@login_required
def report():
    today = date.today().isoformat()
    start = request.args.get("from", today)
    end = request.args.get("to", today)

    start_dt = datetime.fromisoformat(start)
    end_dt = datetime.fromisoformat(end) + timedelta(days=1)

    # ----- Sales -----
    query_sales = Sale.query.filter(Sale.date >= start_dt, Sale.date <= end_dt)
    query_items = (
        SaleItem.query.join(Sale)
        .filter(Sale.date >= start_dt, Sale.date <= end_dt)
        .all()
    )

    total_sales = (
        db.session.query(db.func.sum(Sale.total_amount))
        .filter(Sale.date >= start_dt, Sale.date <= end_dt)
        .scalar()
        or 0
    )

    cost_of_sales = 0
    for item in query_items:
        cost_of_sales += calculate_meal_cost(item.meal)

    profit_real = total_sales - cost_of_sales

    # ----- Ingredients Usage (manual + meals) -----
    ingredients_usage = {}

    # Manual consumption
    manual = ManualConsumption.query.filter(
        ManualConsumption.date >= start_dt, ManualConsumption.date <= end_dt
    ).all()

    for m in manual:
        pid = m.product.id
        if pid not in ingredients_usage:
            ingredients_usage[pid] = {
                "name": m.product.name,
                "quantity_type": m.product.quantity_type,
                "quantity": 0,
                "cost": 0,
            }
        ingredients_usage[pid]["quantity"] += m.quantity
        ingredients_usage[pid]["cost"] += m.quantity * m.product.buy_price

    # Meal-based consumption
    for item in query_items:
        for comp in item.meal.components:
            pid = comp.product.id
            if pid not in ingredients_usage:
                ingredients_usage[pid] = {
                    "name": comp.product.name,
                    "quantity_type": comp.product.quantity_type,
                    "quantity": 0,
                    "cost": 0,
                }
            ingredients_usage[pid]["quantity"] += comp.quantity
            ingredients_usage[pid]["cost"] += comp.quantity * comp.product.buy_price

    ingredients_usage_list = list(ingredients_usage.values())
    total_ing_cost = sum(p["cost"] for p in ingredients_usage_list)

    # ----- Warehouse Movement -----
    products = Product.query.all()
    warehouse_movement = []

    for p in products:
        # Purchases
        bought = (
            db.session.query(db.func.sum(Purchase.quantity))
            .filter(
                Purchase.product_id == p.id,
                Purchase.date >= start_dt,
                Purchase.date <= end_dt,
            )
            .scalar()
            or 0
        )

        # Consumption through meals
        consumed = 0
        for item in query_items:
            for comp in item.meal.components:
                if comp.product_id == p.id:
                    consumed += comp.quantity

        # Manual consumption
        manual_consumed = (
            db.session.query(db.func.sum(ManualConsumption.quantity))
            .filter(
                ManualConsumption.product_id == p.id,
                ManualConsumption.date >= start_dt,
                ManualConsumption.date <= end_dt,
            )
            .scalar()
            or 0
        )

        consumed += manual_consumed

        warehouse_movement.append(
            {
                "name": p.name,
                "quantity_type": p.quantity_type,
                "consumed": consumed,
                "bought": bought,
                "remaining": p.quantity,
            }
        )

    return render_template(
        "report.html",
        total_sales=round(total_sales, 2),
        cost_of_sales=round(cost_of_sales, 2),
        profit_real=round(profit_real, 2),
        start=start,
        end=end,
        ingredients_usage=ingredients_usage_list,
        total_ing_cost=total_ing_cost,
        warehouse_movement=warehouse_movement,
    )


@app.route("/print_ingredients_report")
@login_required
def print_ingredients_report():
    start = request.args.get("start")
    end = request.args.get("end")

    start_dt = datetime.fromisoformat(start)
    end_dt = datetime.fromisoformat(end) + timedelta(days=1)

    query_items = SaleItem.query.join(Sale).filter(
        Sale.date >= start_dt, Sale.date <= end_dt
    )

    ingredients_usage = {}
    for item in query_items.all():
        for comp in item.meal.components:
            pid = comp.product.id
            if pid not in ingredients_usage:
                ingredients_usage[pid] = {
                    "name": comp.product.name,
                    "quantity_type": comp.product.quantity_type,
                    "quantity": 0,
                    "cost": 0,
                }
            ingredients_usage[pid]["quantity"] += comp.quantity
            ingredients_usage[pid]["cost"] += comp.quantity * comp.product.buy_price

    ingredients_usage_list = list(ingredients_usage.values())

    return render_template(
        "ingredients_report_print.html",
        start=start,
        end=end,
        ingredients_usage=ingredients_usage_list,
    )


@app.route("/print_warehouse_report")
@login_required
def print_warehouse_report():
    start = request.args.get("start")
    end = request.args.get("end")

    today = date.today().isoformat()
    start = start or today
    end = end or today

    start_dt = datetime.fromisoformat(start)
    end_dt = datetime.fromisoformat(end) + timedelta(days=1)

    products = Product.query.all()
    query_items = SaleItem.query.join(Sale).filter(
        Sale.date >= start_dt, Sale.date <= end_dt
    )

    warehouse_movement = []
    for p in products:
        bought = (
            db.session.query(db.func.sum(Purchase.quantity))
            .filter(
                Purchase.product_id == p.id,
                Purchase.date >= start_dt,
                Purchase.date <= end_dt,
            )
            .scalar()
            or 0
        )

        consumed = 0
        for item in query_items.all():
            for comp in item.meal.components:
                if comp.product_id == p.id:
                    consumed += comp.quantity

        warehouse_movement.append(
            {
                "name": p.name,
                "quantity_type": p.quantity_type,
                "consumed": float(consumed or 0),
                "bought": float(bought or 0),
                "remaining": float(p.quantity or 0),
            }
        )

    return render_template(
        "print_warehouse_report.html",
        start=start,
        end=end,
        warehouse_movement=warehouse_movement,
    )


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]
        if User.query.filter_by(username=username).first():
            flash("اسم المستخدم موجود مسبقًا", "danger")
            return redirect(url_for("signup"))
        user = User(username=username)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash("✅ تم إنشاء الحساب", "success")
        return redirect(url_for("login"))
    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            session["user_id"] = user.id
            flash(f"مرحبًا {user.username}", "success")
            return redirect(url_for("index"))
        flash("اسم المستخدم أو كلمة المرور غير صحيحة", "danger")
        return redirect(url_for("login"))
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.pop("user_id", None)
    flash("تم تسجيل الخروج", "success")
    return redirect(url_for("login"))


@app.route("/shutdown")
def shutdown():
    os.kill(os.getpid(), signal.SIGINT)
    return "Stopped"


# ================== Sessions ======================


@app.before_request
def load_user():
    g.user = None
    if "user_id" in session:
        g.user = db.session.get(User, session["user_id"])


with app.app_context():
    db.create_all()
    get_safe()


if __name__ == "__main__":
    threading.Thread(target=lambda: webbrowser.open("http://127.0.0.1:8000")).start()
    print("✅ Running at http://127.0.0.1:8000")
    serve(app, host="127.0.0.1", port=8000)
