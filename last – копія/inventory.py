from flask import Blueprint, render_template, request, redirect, url_for, session, flash, Response
from db import get_conn
import csv, io
from urllib.parse import urlencode
import math
from flask import session


bp = Blueprint('inv', __name__)

def require_role(*roles):
    role = session.get('user',{}).get('role')
    return role in roles

# ---------- Helpers ----------
def fetchall(query, params=()):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SET search_path TO app, public;")
        cur.execute(query, params)
        return cur.fetchall()

def fetchone(query, params=()):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SET search_path TO app, public;")
        cur.execute(query, params)
        return cur.fetchone()

def execute(query, params=()):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SET search_path TO app, public;")
        cur.execute(query, params)
        conn.commit()

def log_archive(entity, eid, action, reason=None):
    who = (session.get('user') or {}).get('login') or 'system'
    execute("""
        INSERT INTO archive_history(entity_type, entity_id, action, performed_by, reason)
        VALUES (%s,%s,%s,%s,%s)
    """, (entity, eid, action, who, reason))

def archive_entity(table, entity_type, entity_id, reason):
    user = (session.get('user') or {}).get('login') or 'system'
    execute(f"""
        UPDATE {table}
           SET is_active = false,
               archived_at = now(),
               archived_by = %s,
               archive_reason = %s
         WHERE id = %s
    """, (user, reason, entity_id))
    execute("""
        INSERT INTO archive_history(entity_type, entity_id, action, performed_by, reason)
        VALUES (%s, %s, 'archive', %s, %s)          
    """, (entity_type, entity_id, user, reason))

def restore_entity(table, entity_type, entity_id):
    user = (session.get('user') or {}).get('login') or 'system'
    execute(f"""
        UPDATE {table}
           SET is_active = true,
               archived_at = NULL,
               archived_by = NULL,
               archive_reason = NULL
         WHERE id = %s
    """, (entity_id,))
    execute("""
        INSERT INTO archive_history(entity_type, entity_id, action, performed_by)
        VALUES (%s, %s, 'restore', %s)              
    """, (entity_type, entity_id, user))

def _pg_args():
    args = request.args.to_dict(flat=True)
    per_page_default = _pref('per_page', 20)
    page = int(args.pop('page', 1) or 1)
    per_page = int(args.pop('per_page', per_page_default) or per_page_default)
    page = 1 if page < 1 else page
    per_page = 5 if per_page < 5 else (100 if per_page > 100 else per_page)
    qs_base = ''
    if args:
        clean = {k: v for k, v in args.items() if v not in (None, '', [])}
        if clean:
            qs_base = '&' + urlencode(clean)
    return page, per_page, qs_base, args


def _pref(name, default=None):
    return (session.get('prefs') or {}).get(name, default)

def _pref_df(key, default=''):
    df = (session.get('prefs') or {}).get('default_filter') or {}
    return df.get(key, default)


# ---------- Suppliers ----------
@bp.get('/suppliers')
def suppliers_list():
    page, per_page, qs_base, args = _pg_args()
    q = (args.get('q') or _pref_df('suppliers.q', '')).strip()
    like = f"%{q}%"
    where = ""
    params = []
    if q:
        where = "WHERE (s.name ILIKE %s OR s.address ILIKE %s OR s.phone ILIKE %s)"
        params = [like, like, like]

    total = fetchone(f"SELECT COUNT(*) FROM suppliers s {where}", params)[0]
    pages = max(1, math.ceil(total/per_page))
    offset = (page-1)*per_page

    rows = fetchall(f"""
      SELECT s.id, s.name, s.address, s.phone,
             s.is_active, s.archived_at, s.archived_by,
             COALESCE(p.products_cnt,0), COALESCE(m.moves_cnt,0)
      FROM suppliers s
      LEFT JOIN (
        SELECT supplier_id, COUNT(*) products_cnt FROM products GROUP BY supplier_id
      ) p ON p.supplier_id = s.id
      LEFT JOIN (
        SELECT supplier_id, COUNT(*) moves_cnt FROM stock_movements WHERE mtype='IN' GROUP BY supplier_id
      ) m ON m.supplier_id = s.id
      {where}
      ORDER BY s.id DESC
      LIMIT %s OFFSET %s
    """, params + [per_page, offset])

    return render_template("suppliers.html",
        rows=rows, q=q,
        page=page, pages=pages, per_page=per_page, qs_base=qs_base, total=total
    )

@bp.post('/suppliers/add')
def suppliers_add():
    if not require_role('Admin','Operator'):
        flash('Доступ лише для оператора/адміністратора', 'error')
        return redirect(url_for('inv.suppliers_list'))
    name = request.form['name'].strip()
    address = request.form.get('address', '').strip()
    phone = request.form.get('phone', '').strip()
    execute("INSERT INTO suppliers(name,address,phone) VALUES (%s,%s,%s)", (name,address,phone))
    flash('Постачальника додано', 'ok')
    return redirect(url_for('inv.suppliers_list'))

@bp.post('/suppliers/<int:rid>/archive')
def suppliers_archive(rid):
    if not require_role('Admin','Operator'):
        flash('Доступ лише для оператора/адміністратора', 'error')
        return redirect(url_for('inv.suppliers_list'))
    reason = request.form.get('reason', '').strip() or None
    archive_entity('suppliers','supplier', rid, reason)
    flash('Постачальника архівовано', 'ok')
    return redirect(url_for('inv.suppliers_list'))

@bp.post('/suppliers/<int:rid>/restore')
def suppliers_restore(rid):
    if not require_role('Admin'):
        flash('Відновлювати може лише адміністратор', 'error')
        return redirect(url_for('inv.suppliers_list'))
    restore_entity('suppliers','supplier', rid)
    flash('Постачальника відновлено', 'ok')
    return redirect(url_for('inv.suppliers_list'))

# ---------- Customers ----------
@bp.get('/customers')
def customers_list():
    page, per_page, qs_base, args = _pg_args()
    q = (args.get('q') or _pref_df('customers.q', '')).strip()
    like = f"%{q}%"
    where = ""
    params = []
    if q:
        where = "WHERE (c.name ILIKE %s OR c.address ILIKE %s OR c.phone ILIKE %s)"
        params = [like, like, like]

    total = fetchone(f"SELECT COUNT(*) FROM customers c {where}", params)[0]
    pages = max(1, math.ceil(total/per_page))
    offset = (page-1)*per_page

    rows = fetchall(f"""
      SELECT c.id, c.name, c.address, c.phone,
             c.archived_at, c.archived_by,
             COALESCE(m.cnt,0)
      FROM customers c
      LEFT JOIN (
        SELECT customer_id, COUNT(*) cnt FROM stock_movements WHERE mtype='OUT' GROUP BY customer_id
      ) m ON m.customer_id = c.id
      {where}
      ORDER BY c.id DESC
      LIMIT %s OFFSET %s
    """, params + [per_page, offset])

    return render_template("customers.html",
        rows=rows, q=q,
        page=page, pages=pages, per_page=per_page, qs_base=qs_base, total=total
    )

@bp.post('/customers/add')
def customers_add():
    if not require_role('Admin','Operator'):
        flash('Доступ лише для оператора/адміністратора', 'error')
        return redirect(url_for('inv.customers_list'))
    name = request.form['name'].strip()
    address = request.form.get('address','').strip()
    phone = request.form.get('phone','').strip()
    execute("INSERT INTO customers(name,address,phone) VALUES (%s,%s,%s)", (name,address,phone))
    flash('Покупця додано', 'ok')
    return redirect(url_for('inv.customers_list'))

@bp.post('/customers/<int:rid>/archive')
def customers_archive(rid):
    if not require_role('Admin','Operator'):
        flash('Доступ лише для оператора/адміністратора', 'error')
        return redirect(url_for('inv.customers_list'))
    reason = request.form.get('reason', '').strip() or None
    archive_entity('customers','customer', rid, reason)
    flash('Покупця архівовано', 'ok')
    return redirect(url_for('inv.customers_list'))

@bp.post('/customers/<int:rid>/restore')
def customers_restore(rid):
    if not require_role('Admin'):
        flash('Відновлювати може лише адміністратор', 'error')
        return redirect(url_for('inv.customers_list'))
    restore_entity('customers','customer', rid)
    flash('Покупця відновлено', 'ok')
    return redirect(url_for('inv.customers_list'))

# ---------- Products ----------
@bp.get('/products')
def products_list():
    page, per_page, qs_base, args = _pg_args()
    q = (args.get('q') or _pref_df('products.q', '')).strip()
    like = f"%{q}%"
    where = ""
    params = []
    if q:
        where = "WHERE (p.name ILIKE %s OR p.unit ILIKE %s OR s.name ILIKE %s)"
        params = [like, like, like]

    total = fetchone(f"""
      SELECT COUNT(*) FROM products p
      JOIN suppliers s ON s.id = p.supplier_id
      {where}
    """, params)[0]

    pages = max(1, math.ceil(total/per_page))
    offset = (page-1)*per_page

    rows = fetchall(f"""
      SELECT p.id, p.name, p.unit, p.purchase_price, p.sale_price,
             s.name AS supplier_name, p.supplier_id,
             p.is_active, p.archived_at, p.archived_by
      FROM products p
      JOIN suppliers s ON s.id = p.supplier_id
      {where}
      ORDER BY p.id DESC
      LIMIT %s OFFSET %s
    """, params + [per_page, offset])

    suppliers = fetchall("SELECT id, name FROM suppliers WHERE is_active ORDER BY name")
    return render_template("products.html",
        rows=rows, suppliers=suppliers, q=q,
        page=page, pages=pages, per_page=per_page, qs_base=qs_base, total=total
    )

@bp.post('/products/add')
def products_add():
    if not require_role('Admin','Operator'):
        flash('Доступ лише для оператора/адміністратора', 'error')
        return redirect(url_for('inv.products_list'))
    supplier_id = request.form.get('supplier_id')
    name = request.form['name'].strip()
    unit = request.form['unit'].strip()
    purchase_price = request.form.get('purchase_price')
    sale_price = request.form.get('sale_price')
    execute("""
        INSERT INTO products(supplier_id,name,unit,purchase_price,sale_price)
        VALUES (%s,%s,%s,%s,%s)
    """, (supplier_id,name,unit,purchase_price,sale_price))
    flash('Товар додано', 'ok')
    return redirect(url_for('inv.products_list'))

@bp.post('/products/<int:rid>/archive')
def products_archive(rid):
    if not require_role('Admin','Operator'):
        flash('Доступ лише для оператора/адміністратора', 'error')
        return redirect(url_for('inv.products_list'))
    reason = request.form.get('reason', '').strip() or None
    archive_entity('products','product', rid, reason)
    flash('Товар архівовано', 'ok')
    return redirect(url_for('inv.products_list'))

@bp.post('/products/<int:rid>/restore')
def products_restore(rid):
    if not require_role('Admin'):
        flash('Відновлювати може лише адміністратор', 'error')
        return redirect(url_for('inv.products_list'))
    restore_entity('products','product', rid)
    flash('Товар відновлено', 'ok')
    return redirect(url_for('inv.products_list'))

# ---------- Agreements ----------
@bp.get('/agreements')
def agreements_list():
    page, per_page, qs_base, args = _pg_args()
    q = (args.get('q') or '').strip()
    like = f"%{q}%"
    where = ""
    params = []
    if q:
        where = "WHERE (a.agreement_no ILIKE %s OR c.name ILIKE %s)"
        params = [like, like]

    total = fetchone(f"""
      SELECT COUNT(*) FROM agreements a
      JOIN customers c ON c.id = a.customer_id
      {where}
    """, params)[0]

    pages = max(1, math.ceil(total/per_page))
    offset = (page-1)*per_page

    rows = fetchall(f"""
      SELECT a.id, a.agreement_no, a.agreement_dt,
             c.name AS customer_name, a.customer_id,
             a.is_active, a.archived_at, a.archived_by
      FROM agreements a
      JOIN customers c ON c.id = a.customer_id
      {where}
      ORDER BY a.id DESC
      LIMIT %s OFFSET %s
    """, params + [per_page, offset])

    customers = fetchall("SELECT id, name FROM customers WHERE archived_at IS NULL ORDER BY name")
    return render_template("agreements.html",
        rows=rows, customers=customers, q=q,
        page=page, pages=pages, per_page=per_page, qs_base=qs_base, total=total
    )

@bp.post('/agreements/add')
def agreements_add():
    if not require_role('Admin','Operator'):
        flash('Доступ лише для оператора/адміністратора', 'error')
        return redirect(url_for('inv.agreements_list'))
    customer_id = request.form.get('customer_id')
    agreement_no = request.form['agreement_no'].strip()
    agreement_dt = request.form.get('agreement_dt')
    execute("""
        INSERT INTO agreements(customer_id, agreement_no, agreement_dt)
        VALUES (%s,%s,%s)
    """, (customer_id, agreement_no, agreement_dt))
    flash('Угоду додано', 'ok')
    return redirect(url_for('inv.agreements_list'))

@bp.post('/agreements/<int:rid>/archive')
def agreements_archive(rid):
    if not require_role('Admin','Operator'):
        flash('Доступ лише для оператора/адміністратора', 'error')
        return redirect(url_for('inv.agreements_list'))
    reason = request.form.get('reason', '').strip() or None
    archive_entity('agreements','agreement', rid, reason)
    flash('Угоду архівовано', 'ok')
    return redirect(url_for('inv.agreements_list'))

@bp.post('/agreements/<int:rid>/restore')
def agreements_restore(rid):
    if not require_role('Admin'):
        flash('Відновлювати може лише адміністратор', 'error')
        return redirect(url_for('inv.agreements_list'))
    restore_entity('agreements','agreement', rid)
    flash('Угоду відновлено', 'ok')
    return redirect(url_for('inv.agreements_list'))

# ---------- Stock Movements (IN/OUT) ----------
@bp.get('/movements')
def movements_list():
    page, per_page, qs_base, args = _pg_args()
    q = (args.get('q') or '').strip()
    like = f"%{q}%"
    where = ""
    params = []
    if q:
        where = """WHERE (
           p.name ILIKE %s OR
           COALESCE(s.name,'') ILIKE %s OR
           COALESCE(c.name,'') ILIKE %s OR
           COALESCE(a.agreement_no,'') ILIKE %s
        )"""
        params = [like, like, like, like]

    total = fetchone(f"""
      SELECT COUNT(*)
      FROM stock_movements m
      JOIN products p   ON p.id = m.product_id
      LEFT JOIN suppliers s ON s.id = m.supplier_id
      LEFT JOIN customers c ON c.id = m.customer_id
      LEFT JOIN agreements a ON a.id = m.agreement_id
      {where}
    """, params)[0]

    pages = max(1, math.ceil(total/per_page))
    offset = (page-1)*per_page

    rows = fetchall(f"""
      SELECT
        m.id, to_char(m.movement_dt,'YYYY-MM-DD HH24:MI:SS') as dt,
        m.mtype,
        p.name as product_name, p.id as product_id,
        s.name as supplier_name,
        c.name as customer_name,
        m.qty, m.price, (m.qty*m.price) as sum_total,
        a.agreement_no,
        m.is_canceled, m.canceled_at, m.canceled_by
      FROM stock_movements m
      JOIN products p   ON p.id = m.product_id
      LEFT JOIN suppliers s ON s.id = m.supplier_id
      LEFT JOIN customers c ON c.id = m.customer_id
      LEFT JOIN agreements a ON a.id = m.agreement_id
      {where}
      ORDER BY m.id DESC
      LIMIT %s OFFSET %s
    """, params + [per_page, offset])

    products   = fetchall("SELECT id, name FROM products WHERE archived_at IS NULL ORDER BY name")
    suppliers  = fetchall("SELECT id, name FROM suppliers WHERE is_active ORDER BY name")
    customers  = fetchall("SELECT id, name FROM customers WHERE archived_at IS NULL ORDER BY name")
    agreements = fetchall("SELECT id, agreement_no FROM agreements WHERE is_active ORDER BY agreement_no")

    return render_template("movements.html",
        rows=rows, products=products, suppliers=suppliers, customers=customers, agreements=agreements,
        q=q, page=page, pages=pages, per_page=per_page, qs_base=qs_base, total=total
    )


# ---------- Movements: спільна логіка ----------

def _back(msg):
    flash(msg, 'error')
    return redirect(url_for('inv.movements_list'))


def _read_movement_form():
    f = request.form
    return {
        'mtype': f.get('mtype'),
        'movement_dt': f.get('movement_dt') or None,
        'product_id': f.get('product_id'),
        'qty': f.get('qty'),
        'price': f.get('price'),
        'supplier_id': f.get('supplier_id') or None,
        'customer_id': f.get('customer_id') or None,
        'agreement_id': f.get('agreement_id') or None,
    }


def _normalize_parties(m):
    """IN — без клієнта, OUT — без постачальника. False, якщо тип невірний."""
    if m['mtype'] == 'IN':
        m['customer_id'] = None
    elif m['mtype'] == 'OUT':
        m['supplier_id'] = None
    else:
        return False
    return True


def _qty_error(qty):
    try:
        value = float(qty)
    except (TypeError, ValueError):
        return 'Невірна кількість'
    return None if value > 0 else 'Кількість має бути додатною'


def _available_qty(product_id, exclude_id=None):
    row = fetchone("""
        SELECT COALESCE(SUM(CASE WHEN mtype='IN' THEN qty ELSE -qty END), 0)
        FROM stock_movements
        WHERE product_id=%s AND is_canceled=false
          AND (%s IS NULL OR id <> %s)
    """, (product_id, exclude_id, exclude_id))
    return row[0] if row else 0


def _validate_movement(m, exclude_id=None):
    """Повертає текст помилки або None, якщо рух коректний."""
    error = _qty_error(m['qty'])
    if error:
        return error
    if not _normalize_parties(m):
        return 'Невірний тип руху'
    if m['mtype'] != 'OUT':
        return None
    available = _available_qty(m['product_id'], exclude_id)
    if available < float(m['qty']):
        return f"Недостатньо залишку. Доступно: {available}, запитано: {m['qty']}"
    return None


def _insert_movement(m):
    execute("""
      INSERT INTO stock_movements(movement_dt, mtype, product_id, supplier_id,
                                  customer_id, agreement_id, qty, price)
      VALUES (COALESCE(%s::timestamptz, now()), %s, %s, %s, %s, %s, %s, %s)
    """, (m['movement_dt'], m['mtype'], m['product_id'], m['supplier_id'],
          m['customer_id'], m['agreement_id'], m['qty'], m['price']))

@bp.post('/movements/add')
def movements_add():
    if not require_role('Admin', 'Operator'):
        return _back('Доступ лише для оператора/адміністратора')
    m = _read_movement_form()
    error = _validate_movement(m)
    if error:
        return _back(error)
    _insert_movement(m)
    flash('Рух додано', 'ok')
    return redirect(url_for('inv.movements_list'))

@bp.post('/movements/<int:rid>/cancel')
def movements_cancel(rid):
    if not require_role('Admin','Operator'):
        flash('Скасувати рух може оператор або адміністратор', 'error')
        return redirect(url_for('inv.movements_list'))
    reason = (request.form.get('reason') or '').strip() or None
    actor = (session.get('user') or {}).get('login') or 'system'
    execute("""
            UPDATE stock_movements
            SET is_canceled   = true,
                canceled_at   = now(),
                canceled_by   = %s,
                cancel_reason = %s
            WHERE id = %s
            """, (actor, reason, rid))
    execute("""
            INSERT INTO archive_history(entity_type, entity_id, action, performed_by, reason)
            VALUES ('movement', %s, 'cancel', %s, %s) -- <==== 'cancel'
            """, (rid, actor, reason))
    flash('Рух скасовано', 'ok')
    return redirect(url_for('inv.movements_list'))

@bp.post('/movements/<int:rid>/uncancel')
def movements_uncancel(rid):
    if not require_role('Admin'):
        flash('Повернути зі скасованих може лише адміністратор', 'error')
        return redirect(url_for('inv.movements_list'))
    actor = (session.get('user') or {}).get('login') or 'system'
    execute("""
            UPDATE stock_movements
            SET is_canceled   = false,
                canceled_at   = NULL,
                canceled_by   = NULL,
                cancel_reason = NULL
            WHERE id = %s
            """, (rid,))
    execute("""
            INSERT INTO archive_history(entity_type, entity_id, action, performed_by)
            VALUES ('movement', %s, 'uncancel', %s) -- <==== 'uncancel'
            """, (rid, actor))
    flash('Рух відновлено', 'ok')
    return redirect(url_for('inv.movements_list'))

@bp.get('/archive-history')
def archive_history_page():
    page, per_page, qs_base, args = _pg_args()
    q = (args.get('q') or '').strip()
    like = f"%{q}%"
    where = ""
    params = []
    if q:
        where = "WHERE (entity_type ILIKE %s OR performed_by ILIKE %s OR COALESCE(reason,'') ILIKE %s)"
        params = [like, like, like]

    total = fetchone(f"SELECT COUNT(*) FROM archive_history {where}", params)[0]
    pages = max(1, math.ceil(total/per_page))
    offset = (page-1)*per_page

    rows = fetchall(f"""
      SELECT performed_at, entity_type, entity_id, action, performed_by, reason
      FROM archive_history
      {where}
      ORDER BY performed_at DESC
      LIMIT %s OFFSET %s
    """, params + [per_page, offset])

    return render_template("archive_history.html",
        rows=rows, q=q,
        page=page, pages=pages, per_page=per_page, qs_base=qs_base, total=total)



# ========================= EDIT/UPDATE ROUTES =========================

# ---- Suppliers ----
@bp.get('/suppliers/<int:rid>/edit')
def suppliers_edit(rid):
    if not require_role('Admin','Operator'):
        flash('Редагувати може лише оператор/адміністратор', 'error')
        return redirect(url_for('inv.suppliers_list'))
    rows = fetchall("SELECT id, name, address, phone, is_active FROM suppliers WHERE id=%s", (rid,))
    if not rows:
        flash('Постачальника не знайдено', 'error')
        return redirect(url_for('inv.suppliers_list'))
    r = rows[0]
    return render_template('suppliers_edit.html', r=r)

@bp.post('/suppliers/<int:rid>/update')
def suppliers_update(rid):
    if not require_role('Admin','Operator'):
        flash('Редагувати може лише оператор/адміністратор', 'error')
        return redirect(url_for('inv.suppliers_list'))
    name = request.form.get('name','').strip()
    address = request.form.get('address','').strip() or None
    phone = request.form.get('phone','').strip() or None
    execute("UPDATE suppliers SET name=%s, address=%s, phone=%s WHERE id=%s",
            (name, address, phone, rid))
    flash('Зміни збережено', 'ok')
    return redirect(url_for('inv.suppliers_list'))

# ---- Customers ----
@bp.get('/customers/<int:rid>/edit')
def customers_edit(rid):
    if not require_role('Admin','Operator'):
        flash('Редагувати може лише оператор/адміністратор', 'error')
        return redirect(url_for('inv.customers_list'))
    rows = fetchall("SELECT id, name, address, phone, is_active FROM customers WHERE id=%s", (rid,))
    if not rows:
        flash('Покупця не знайдено', 'error')
        return redirect(url_for('inv.customers_list'))
    r = rows[0]
    return render_template('customers_edit.html', r=r)

@bp.post('/customers/<int:rid>/update')
def customers_update(rid):
    if not require_role('Admin','Operator'):
        flash('Редагувати може лише оператор/адміністратор', 'error')
        return redirect(url_for('inv.customers_list'))
    name = request.form.get('name','').strip()
    address = request.form.get('address','').strip() or None
    phone = request.form.get('phone','').strip() or None
    execute("UPDATE customers SET name=%s, address=%s, phone=%s WHERE id=%s",
            (name, address, phone, rid))
    flash('Зміни збережено', 'ok')
    return redirect(url_for('inv.customers_list'))

# ---- Products ----
@bp.get('/products/<int:rid>/edit')
def products_edit(rid):
    if not require_role('Admin','Operator'):
        flash('Редагувати може лише оператор/адміністратор', 'error')
        return redirect(url_for('inv.products_list'))
    rows = fetchall("SELECT id, supplier_id, name, unit, purchase_price, sale_price, is_active FROM products WHERE id=%s", (rid,))
    if not rows:
        flash('Товар не знайдено', 'error')
        return redirect(url_for('inv.products_list'))
    r = rows[0]
    suppliers = fetchall("SELECT id, name FROM suppliers WHERE is_active=true OR id=%s ORDER BY name", (r[1],))
    return render_template('products_edit.html', r=r, suppliers=suppliers)

@bp.post('/products/<int:rid>/update')
def products_update(rid):
    if not require_role('Admin','Operator'):
        flash('Редагувати може лише оператор/адміністратор', 'error')
        return redirect(url_for('inv.products_list'))
    supplier_id = request.form.get('supplier_id')
    name = request.form.get('name','').strip()
    unit = request.form.get('unit','').strip()
    purchase_price = request.form.get('purchase_price')
    sale_price = request.form.get('sale_price')
    execute("""
        UPDATE products
           SET supplier_id=%s, name=%s, unit=%s, purchase_price=%s, sale_price=%s
         WHERE id=%s
    """, (supplier_id, name, unit, purchase_price, sale_price, rid))
    flash('Зміни збережено', 'ok')
    return redirect(url_for('inv.products_list'))

# ---- Agreements ----
@bp.get('/agreements/<int:rid>/edit')
def agreements_edit(rid):
    if not require_role('Admin','Operator'):
        flash('Редагувати може лише оператор/адміністратор', 'error')
        return redirect(url_for('inv.agreements_list'))
    rows = fetchall("SELECT id, customer_id, agreement_no, agreement_dt, is_active FROM agreements WHERE id=%s", (rid,))
    if not rows:
        flash('Угоду не знайдено', 'error')
        return redirect(url_for('inv.agreements_list'))
    r = rows[0]
    customers = fetchall("SELECT id, name FROM customers WHERE is_active=true OR id=%s ORDER BY name", (r[1],))
    return render_template('agreements_edit.html', r=r, customers=customers)

@bp.post('/agreements/<int:rid>/update')
def agreements_update(rid):
    if not require_role('Admin','Operator'):
        flash('Редагувати може лише оператор/адміністратор', 'error')
        return redirect(url_for('inv.agreements_list'))
    customer_id = request.form.get('customer_id')
    agreement_no = request.form.get('agreement_no','').strip()
    agreement_dt = request.form.get('agreement_dt')
    execute("""
        UPDATE agreements
           SET customer_id=%s, agreement_no=%s, agreement_dt=%s
         WHERE id=%s
    """, (customer_id, agreement_no, agreement_dt, rid))
    flash('Зміни збережено', 'ok')
    return redirect(url_for('inv.agreements_list'))

# ---- Movements (limited edit, not allowed if canceled) ----
@bp.get('/movements/<int:rid>/edit')
def movements_edit(rid):
    if not require_role('Admin','Operator'):
        flash('Редагувати може лише оператор/адміністратор', 'error')
        return redirect(url_for('inv.movements_list'))
    rows = fetchall("""
        SELECT id, movement_dt, mtype, product_id, supplier_id, customer_id, agreement_id, qty, price, is_canceled
          FROM stock_movements WHERE id=%s
    """, (rid,))
    if not rows:
        flash('Рух не знайдено', 'error')
        return redirect(url_for('inv.movements_list'))
    r = rows[0]
    if r[9]:
        flash('Скасований рух редагувати не можна', 'error')
        return redirect(url_for('inv.movements_list'))
    products  = fetchall("SELECT id, name FROM products WHERE is_active=true OR id=%s ORDER BY name", (r[3],))
    suppliers = fetchall("SELECT id, name FROM suppliers WHERE is_active=true OR id=%s ORDER BY name", (r[4],))
    customers = fetchall("SELECT id, name FROM customers WHERE is_active=true OR id=%s ORDER BY name", (r[5],))
    agreements= fetchall("SELECT id, agreement_no FROM agreements WHERE is_active=true OR id=%s ORDER BY agreement_no", (r[6],))
    return render_template('movements_edit.html', r=r, products=products, suppliers=suppliers, customers=customers, agreements=agreements)

@bp.post('/movements/<int:rid>/update')
def movements_update(rid):
    if not require_role('Admin', 'Operator'):
        return _back('Редагувати може лише оператор/адміністратор')
    rows = fetchall("SELECT is_canceled FROM stock_movements WHERE id=%s", (rid,))
    if not rows:
        return _back('Рух не знайдено')
    if rows[0][0]:
        return _back('Скасований рух редагувати не можна')
    m = _read_movement_form()
    error = _validate_movement(m, exclude_id=rid)
    if error:
        return _back(error)
    execute("""
        UPDATE stock_movements
           SET movement_dt = COALESCE(%s::timestamptz, movement_dt),
               mtype=%s, product_id=%s, supplier_id=%s, customer_id=%s,
               agreement_id=%s, qty=%s, price=%s
         WHERE id=%s
    """, (m['movement_dt'], m['mtype'], m['product_id'], m['supplier_id'],
          m['customer_id'], m['agreement_id'], m['qty'], m['price'], rid))
    flash('Зміни збережено', 'ok')
    return redirect(url_for('inv.movements_list'))



#---- Залишок -----


@bp.get('/balance')
def balance_page():
    q = (request.args.get('q') or '').strip()

    # БЕЗПЕЧНО: перетворюємо supplier_id у int або None
    supplier_id_raw = request.args.get('supplier_id') or ''
    supplier_id = int(supplier_id_raw) if supplier_id_raw.isdigit() else None

    show_zero = (request.args.get('show_zero') == 'on')

    sql = """
      SELECT product_id, product, unit, supplier_id, supplier, in_qty, out_qty, balance_qty
      FROM stock_balance
      WHERE (%s = '' OR product ILIKE '%%' || %s || '%%')
        AND (%s IS NULL OR supplier_id = %s)
        AND (balance_qty <> 0 OR %s)
      ORDER BY product
    """
    rows = fetchall(sql, (q, q, supplier_id, supplier_id, show_zero))
    suppliers = fetchall("SELECT id, name FROM suppliers ORDER BY name")

    return render_template('balance.html',
                           rows=rows, suppliers=suppliers,
                           q=q, supplier_id=supplier_id_raw, show_zero=show_zero)


@bp.get('/balance.csv')
def balance_csv():
    q = (request.args.get('q') or '').strip()

    supplier_id_raw = request.args.get('supplier_id') or ''
    supplier_id = int(supplier_id_raw) if supplier_id_raw.isdigit() else None

    show_zero = (request.args.get('show_zero') == 'on')

    sql = """
      SELECT product_id, product, unit, supplier, in_qty, out_qty, balance_qty
      FROM stock_balance
      WHERE (%s = '' OR product ILIKE '%%' || %s || '%%')
        AND (%s IS NULL OR supplier_id = %s)
        AND (balance_qty <> 0 OR %s)
      ORDER BY product
    """
    rows = fetchall(sql, (q, q, supplier_id, supplier_id, show_zero))

    import csv, io
    from flask import Response
    output = io.StringIO()
    w = csv.writer(output, lineterminator='\n')
    w.writerow(['ID товару', 'Товар', 'Од.', 'Постачальник', 'Прихід', 'Витрата', 'Залишок'])
    for r in rows:
        w.writerow(r)

    return Response(
        output.getvalue().encode('utf-8-sig'),
        headers={
            "Content-Type": "text/csv; charset=utf-8",
            "Content-Disposition": "attachment; filename=stock_balance.csv"
        }
    )
