# reports.py
from typing import Optional

from flask import Blueprint, render_template, request, session, flash, redirect, url_for, Response
from db import get_conn
from datetime import datetime
import re
import csv
import io



bp = Blueprint("reports", __name__, url_prefix="/analytics")

# --- локальні хелпери ---
def q_all(query, params=()):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SET search_path TO app, public;")
        cur.execute(query, params)
        return cur.fetchall()

def q_one(query, params=()):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SET search_path TO app, public;")
        cur.execute(query, params)
        return cur.fetchone()

def _csv_response(filename: str, headers: list, rows: list):
        output = io.StringIO()
        w = csv.writer(output, lineterminator='\n')
        if headers:
            w.writerow(headers)
        for r in rows:
            w.writerow(r)
        return Response(
            output.getvalue().encode('utf-8-sig'),
            headers={
                "Content-Type": "text/csv; charset=utf-8",
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )

def _date(s):
    return datetime.strptime(s, "%Y-%m-%d").date() if s else None

# довідники
def choices_products():
    return q_all("SELECT id, name FROM products WHERE is_active OR EXISTS (SELECT 1 FROM stock_movements m WHERE m.product_id=products.id) ORDER BY name")

def choices_suppliers():
    return q_all("SELECT id, name FROM suppliers ORDER BY name")

def choices_customers():
    return q_all("SELECT id, name FROM customers ORDER BY name")

# ------------------------------------
# Індекс
# ------------------------------------
@bp.get("/")
def index():
    return render_template("reports/index.html")

# ------------------------------------
# 1) Найактивніші покупці
# ------------------------------------
@bp.get("/top-customers")
def top_customers():
    d1 = _date(request.args.get("d1"))
    d2 = _date(request.args.get("d2"))
    metric = request.args.get("metric") or "sum"  # sum|qty
    limit = int(request.args.get("limit") or 10)

    rows = q_all("""
      SELECT c.id, c.name,
             COALESCE(SUM(CASE WHEN m.is_canceled=false AND m.mtype='OUT' THEN m.qty*m.price END),0) AS sum_total,
             COALESCE(SUM(CASE WHEN m.is_canceled=false AND m.mtype='OUT' THEN m.qty END),0) AS qty_total
      FROM customers c
      LEFT JOIN stock_movements m ON m.customer_id=c.id
           AND (%s IS NULL OR m.movement_dt::date >= %s)
           AND (%s IS NULL OR m.movement_dt::date <= %s)
      GROUP BY c.id, c.name
    """, (d1, d1, d2, d2))

    key_idx = 2 if metric == "sum" else 3
    rows_sorted = sorted(rows, key=lambda r: (r[key_idx] or 0), reverse=True)[:limit]

    if request.args.get("format") == "csv":
        return _csv_response(
            "top_customers.csv",
            ["CustomerID", "Покупець", "Сума", "К-сть"],
            rows_sorted
        )

    return render_template("reports/top_customers.html",
                           rows=rows_sorted, d1=d1, d2=d2, metric=metric, limit=limit)

# ------------------------------------
# 2) Обсяг і ціни на товар по всіх постачальниках (IN)
# ------------------------------------
@bp.get("/product-prices")
def product_prices():
    product_id = request.args.get("product_id")
    products = choices_products()
    rows = []
    if product_id:
        rows = q_all("""
          SELECT s.id, s.name,
                 COALESCE(SUM(CASE WHEN m.is_canceled=false AND m.mtype='IN' THEN m.qty END),0)               AS in_qty,
                 ROUND(AVG(CASE WHEN m.is_canceled=false AND m.mtype='IN' THEN m.price END)::numeric, 2)     AS avg_price,
                 MIN(CASE WHEN m.is_canceled=false AND m.mtype='IN' THEN m.price END)                        AS min_price,
                 MAX(CASE WHEN m.is_canceled=false AND m.mtype='IN' THEN m.price END)                        AS max_price
          FROM suppliers s
          LEFT JOIN stock_movements m ON m.supplier_id=s.id AND m.product_id=%s
          GROUP BY s.id, s.name
          ORDER BY s.name
        """, (product_id,))

        # CSV
        if request.args.get("format") == "csv":
            return _csv_response(
                "product_prices.csv",
                ["SupplierID", "Постачальник", "Прихід, к-сть", "Сер. ціна", "Мін. ціна", "Макс. ціна"],
                rows
            )

    return render_template("reports/product_prices.html",
                           products=products,
                           product_id=int(product_id) if product_id else None,
                           rows=rows)


# ------------------------------------
# 3) Покупці зазначеного товару за період (всі/за постачальником)
# ------------------------------------
@bp.get("/customers-of-product")
def customers_of_product():
    product_id = request.args.get("product_id")
    supplier_id_raw = request.args.get("supplier_id") or ""
    supplier_id = int(supplier_id_raw) if supplier_id_raw.isdigit() else None
    d1 = _date(request.args.get("d1"))
    d2 = _date(request.args.get("d2"))

    products = choices_products()
    suppliers = choices_suppliers()
    rows = []
    if product_id:
        rows = q_all("""
          SELECT c.id, c.name,
                 COALESCE(SUM(CASE WHEN m.is_canceled=false AND m.mtype='OUT' THEN m.qty END),0) AS qty_total,
                 COALESCE(SUM(CASE WHEN m.is_canceled=false AND m.mtype='OUT' THEN m.qty*m.price END),0) AS sum_total
          FROM customers c
          JOIN stock_movements m ON m.customer_id=c.id AND m.product_id=%s
               AND m.mtype='OUT' AND m.is_canceled=false
               AND (%s IS NULL OR m.movement_dt::date >= %s)
               AND (%s IS NULL OR m.movement_dt::date <= %s)
          JOIN products p ON p.id=m.product_id
          WHERE (%s IS NULL OR p.supplier_id=%s)
          GROUP BY c.id, c.name
          ORDER BY sum_total DESC
        """, (product_id, d1, d1, d2, d2, supplier_id, supplier_id))

        if request.args.get("format") == "csv":
            return _csv_response(
                "customers_of_product.csv",
                ["CustomerID", "Покупець", "К-сть", "Сума"],
                rows
            )

    return render_template("reports/customers_of_product.html",
                           products=products, suppliers=suppliers,
                           product_id=int(product_id) if product_id else None,
                           supplier_id=supplier_id_raw, d1=d1, d2=d2, rows=rows)

# ------------------------------------
# 4) Поставки (IN) певного товару від постачальника за весь час або період
# ------------------------------------
@bp.get("/supplies-by-supplier")
def supplies_by_supplier():
    product_id = request.args.get("product_id")
    supplier_id = request.args.get("supplier_id")
    d1 = _date(request.args.get("d1"))
    d2 = _date(request.args.get("d2"))

    products = choices_products()
    suppliers = choices_suppliers()
    rows, totals = [], (0, 0)
    if product_id and supplier_id:
        rows = q_all("""
          SELECT m.id, m.movement_dt, p.name, s.name, m.qty, m.price, m.sum_total
          FROM stock_movements m
          JOIN products p  ON p.id=m.product_id
          JOIN suppliers s ON s.id=m.supplier_id
          WHERE m.mtype='IN' AND m.is_canceled=false
            AND m.product_id=%s AND m.supplier_id=%s
            AND (%s IS NULL OR m.movement_dt::date >= %s)
            AND (%s IS NULL OR m.movement_dt::date <= %s)
          ORDER BY m.movement_dt
        """, (product_id, supplier_id, d1, d1, d2, d2))
        t = q_one("""
          SELECT COALESCE(SUM(m.qty),0), COALESCE(SUM(m.qty*m.price),0)
          FROM stock_movements m
          WHERE m.mtype='IN' AND m.is_canceled=false
            AND m.product_id=%s AND m.supplier_id=%s
            AND (%s IS NULL OR m.movement_dt::date >= %s)
            AND (%s IS NULL OR m.movement_dt::date <= %s)
        """, (product_id, supplier_id, d1, d1, d2, d2))
        totals = t or (0, 0)

        if request.args.get("format") == "csv":
            rows_csv = list(rows) + [['', 'Разом', '', '', totals[0], '', totals[1]]]
            return _csv_response(
                "supplies_by_supplier.csv",
                ["MovementID", "Дата", "Товар", "Постачальник", "К-сть", "Ціна", "Сума"],
                rows_csv
            )

    return render_template("reports/supplies_by_supplier.html",
                           products=products, suppliers=suppliers,
                           product_id=int(product_id) if product_id else None,
                           supplier_id=int(supplier_id) if supplier_id else None,
                           d1=d1, d2=d2, rows=rows, totals=totals)


# ------------------------------------
# 5) Поставки (за угодою) – рухи по номеру угоди (OUT)
# ------------------------------------
@bp.get("/by-agreement")
def by_agreement():
    agreement_no = (request.args.get("agreement_no") or "").strip()
    rows = []
    if agreement_no:
        rows = q_all("""
          SELECT m.id, m.movement_dt, p.name, c.name AS customer, m.qty, m.price, m.sum_total
          FROM agreements a
          JOIN stock_movements m ON m.agreement_id=a.id
          JOIN products p ON p.id=m.product_id
          LEFT JOIN customers c ON c.id=m.customer_id
          WHERE a.agreement_no=%s AND m.mtype='OUT' AND m.is_canceled=false
          ORDER BY m.movement_dt
        """, (agreement_no,))

        if request.args.get("format") == "csv":
            return _csv_response(
                "by_agreement.csv",
                ["MovementID", "Дата", "Товар", "Покупець", "К-сть", "Ціна", "Сума"],
                rows
            )

    return render_template("reports/by_agreement.html",
                           agreement_no=agreement_no, rows=rows)


# ------------------------------------
# 6) Обсяг продажів товару за період (OUT) по всіх постачальниках
#    + розбивка за постачальником (через products.supplier_id)
# ------------------------------------
@bp.get("/sales_of_product")
def sales_of_product():
    product_id = request.args.get("product_id")
    d1 = _date(request.args.get("d1"))
    d2 = _date(request.args.get("d2"))

    products = choices_products()
    total = (0, 0)
    breakdown = []
    if product_id:
        total = q_one("""
          SELECT COALESCE(SUM(m.qty),0), COALESCE(SUM(m.qty*m.price),0)
          FROM stock_movements m
          WHERE m.mtype='OUT' AND m.is_canceled=false
            AND m.product_id=%s
            AND (%s IS NULL OR m.movement_dt::date >= %s)
            AND (%s IS NULL OR m.movement_dt::date <= %s)
        """, (product_id, d1, d1, d2, d2)) or (0, 0)
        breakdown = q_all("""
          SELECT s.name,
                 COALESCE(SUM(m.qty),0) AS qty_total,
                 COALESCE(SUM(m.qty*m.price),0) AS sum_total
          FROM stock_movements m
          JOIN products p  ON p.id=m.product_id
          JOIN suppliers s ON s.id=p.supplier_id
          WHERE m.mtype='OUT' AND m.is_canceled=false
            AND m.product_id=%s
            AND (%s IS NULL OR m.movement_dt::date >= %s)
            AND (%s IS NULL OR m.movement_dt::date <= %s)
          GROUP BY s.name
          ORDER BY sum_total DESC
        """, (product_id, d1, d1, d2, d2))

        if request.args.get("format") == "csv":
            rows_csv = list(breakdown) + [['Разом', total[0], total[1]]]
            return _csv_response(
                "sales_of_product.csv",
                ["Постачальник (довідник товару)", "К-сть", "Сума"],
                rows_csv
            )

    return render_template("reports/sales_of_product.html",
                           products=products, product_id=int(product_id) if product_id else None,
                           d1=d1, d2=d2, total=total, breakdown=breakdown)


# ------------------------------------
# 7) Рентабельність: (∑ продажів / ∑ накладних) за період
# ------------------------------------
@bp.get("/profitability")
def profitability():
    d1 = _date(request.args.get("d1"))
    d2 = _date(request.args.get("d2"))

    sales = q_one("""
      SELECT COALESCE(SUM(m.qty*m.price),0)
      FROM stock_movements m
      WHERE m.mtype='OUT' AND m.is_canceled=false
        AND (%s IS NULL OR m.movement_dt::date >= %s)
        AND (%s IS NULL OR m.movement_dt::date <= %s)
    """, (d1, d1, d2, d2))[0]

    overheads = q_one("""
      SELECT COALESCE(SUM(amount),0) FROM overheads
      WHERE (%s IS NULL OR dt >= %s) AND (%s IS NULL OR dt <= %s)
    """, (d1, d1, d2, d2))[0]

    ratio = (sales / overheads) if overheads > 0 else None

    # для таблиці покажемо деталізацію накладних
    oh_rows = q_all("""
      SELECT dt, category, amount, note
      FROM overheads
      WHERE (%s IS NULL OR dt >= %s) AND (%s IS NULL OR dt <= %s)
      ORDER BY dt
    """, (d1, d1, d2, d2))

    return render_template("reports/profitability.html",
                           d1=d1, d2=d2, sales=sales, overheads=overheads, ratio=ratio, oh_rows=oh_rows)

# ------------------------------------
# 8) Номенклатура і обсяг товарів постачальника
# ------------------------------------
@bp.get("/supplier-nomenclature")
def supplier_nomenclature():
    supplier_id = request.args.get("supplier_id")
    suppliers = choices_suppliers()
    rows = []
    if supplier_id:
        rows = q_all("""
          SELECT p.id, p.name, p.unit,
                 COALESCE(SUM(CASE WHEN m.is_canceled=false AND m.mtype='IN'  THEN m.qty END),0) AS in_qty,
                 COALESCE(SUM(CASE WHEN m.is_canceled=false AND m.mtype='OUT' THEN m.qty END),0) AS out_qty,
                 COALESCE(SUM(CASE WHEN m.is_canceled=false AND m.mtype='IN'  THEN m.qty
                                   WHEN m.is_canceled=false AND m.mtype='OUT' THEN -m.qty END),0) AS balance
          FROM products p
          LEFT JOIN stock_movements m ON m.product_id=p.id
          WHERE p.supplier_id=%s
          GROUP BY p.id, p.name, p.unit
          ORDER BY p.name
        """, (supplier_id,))

        if request.args.get("format") == "csv":
            return _csv_response(
                "supplier_nomenclature.csv",
                ["ProductID", "Товар", "Од.", "Прихід", "Витрата", "Баланс"],
                rows
            )

    return render_template("reports/supplier_nomenclature.html",
                           suppliers=suppliers,
                           supplier_id=int(supplier_id) if supplier_id else None,
                           rows=rows)


# ------------------------------------
# 9) Перелік і кількість покупців, що купили товар за період або >= порогу
# ------------------------------------
@bp.get("/customers-threshold")
def customers_threshold():
    product_id = request.args.get("product_id")
    d1 = _date(request.args.get("d1"))
    d2 = _date(request.args.get("d2"))
    min_qty = float(request.args.get("min_qty") or 0)

    products = choices_products()
    rows = []
    total_customers = 0
    if product_id:
        rows = q_all("""
          SELECT c.id, c.name,
                 COALESCE(SUM(m.qty),0) AS qty_total,
                 COALESCE(SUM(m.qty*m.price),0) AS sum_total
          FROM stock_movements m
          JOIN customers c ON c.id=m.customer_id
          WHERE m.mtype='OUT' AND m.is_canceled=false
            AND m.product_id=%s
            AND (%s IS NULL OR m.movement_dt::date >= %s)
            AND (%s IS NULL OR m.movement_dt::date <= %s)
          GROUP BY c.id, c.name
          HAVING COALESCE(SUM(m.qty),0) >= %s
          ORDER BY qty_total DESC
        """, (product_id, d1, d1, d2, d2, min_qty))
        total_customers = len(rows)

        if request.args.get("format") == "csv":
            rows_csv = list(rows) + [['Усього покупців', total_customers, '', '']]
            return _csv_response(
                "customers_threshold.csv",
                ["CustomerID", "Покупець", "К-сть", "Сума"],
                rows_csv
            )

    return render_template("reports/customers_threshold.html",
                           products=products, product_id=int(product_id) if product_id else None,
                           d1=d1, d2=d2, min_qty=min_qty, rows=rows, total_customers=total_customers)


# ------------------------------------
# 10) Перелік і кількість постачальників, що постачали товар (IN) за період або >= порогу
# ------------------------------------
@bp.get("/suppliers-threshold")
def suppliers_threshold():
    product_id = request.args.get("product_id")
    d1 = _date(request.args.get("d1"))
    d2 = _date(request.args.get("d2"))
    min_qty = float(request.args.get("min_qty") or 0)

    products = choices_products()
    rows = []
    total_suppliers = 0
    if product_id:
        rows = q_all("""
          SELECT s.id, s.name,
                 COALESCE(SUM(m.qty),0) AS qty_total,
                 ROUND(AVG(m.price)::numeric, 2) AS avg_price
          FROM stock_movements m
          JOIN suppliers s ON s.id=m.supplier_id
          WHERE m.mtype='IN' AND m.is_canceled=false
            AND m.product_id=%s
            AND (%s IS NULL OR m.movement_dt::date >= %s)
            AND (%s IS NULL OR m.movement_dt::date <= %s)
          GROUP BY s.id, s.name
          HAVING COALESCE(SUM(m.qty),0) >= %s
          ORDER BY qty_total DESC
        """, (product_id, d1, d1, d2, d2, min_qty))
        total_suppliers = len(rows)

        if request.args.get("format") == "csv":
            rows_csv = list(rows) + [['Усього постачальників', total_suppliers, '', '']]
            return _csv_response(
                "suppliers_threshold.csv",
                ["SupplierID", "Постачальник", "К-сть", "Сер. ціна"],
                rows_csv
            )

    return render_template("reports/suppliers_threshold.html",
                           products=products, product_id=int(product_id) if product_id else None,
                           d1=d1, d2=d2, min_qty=min_qty, rows=rows, total_suppliers=total_suppliers)

FORBIDDEN_TOKENS = (
    'insert','update','delete','alter','drop','create','grant','revoke','truncate',
    'comment','merge','call','do','execute','prepare','deallocate','lock','copy','\\copy',
    'vacuum','analyze','cluster','index','sequence','set','reset','show'
)

def _sanitize_select(sql: str) -> str:
    s = (sql or '').strip()
    if not s:
        raise ValueError('Порожній запит')
    # прибираємо фінальну крапку з комою
    if s.endswith(';'):
        s = s[:-1].strip()

    low = s.lower()

    # лише SELECT або WITH (CTE)
    if not (low.startswith('select') or low.startswith('with')):
        raise ValueError('Дозволено лише SELECT або WITH (CTE)')

    # заборонені ключові слова
    for tok in FORBIDDEN_TOKENS:
        if re.search(rf'\b{tok}\b', low):
            raise ValueError(f'Заборонене слово у запиті: {tok.upper()}')

    # забороняємо SELECT ... INTO (створює таблицю)
    if re.search(r'\bselect\b[^;]*\binto\b', low):
        raise ValueError('Заборонено конструкцію SELECT ... INTO')

    # забороняємо кілька інструкцій через крапку з комою всередині
    if ';' in s:
        raise ValueError('Лише один вираз без ";" усередині')

    return s


def _build_wrapped_query(safe_sql: str, date_col: Optional[str], d1: Optional[str], d2: Optional[str], limit_raw:
Optional[str]):
    wrapped = f"SELECT * FROM ({safe_sql}) AS q"
    params = []

    if date_col:
        # дозволимо лише прості імена/alias (літери, цифри, підкреслення, крапка)
        if not re.match(r'^[A-Za-z_][\w\.]*$', date_col):
            raise ValueError('Некоректна назва колонки дати')
        where = []
        where.append(f"(%s IS NULL OR {date_col}::date >= %s)")
        params.extend([d1, d1])
        where.append(f"(%s IS NULL OR {date_col}::date <= %s)")
        params.extend([d2, d2])
        wrapped += " WHERE " + " AND ".join(where)

    try:
        limit = int(limit_raw) if limit_raw else 200
    except ValueError:
        limit = 200
    limit = max(1, min(limit, 1000))
    wrapped += f" LIMIT {limit}"

    return wrapped, tuple(params), limit


@bp.get("/sql")
def sql_console():
    role = session.get('user', {}).get('role')
    if role not in ('Admin', 'Operator'):
        flash('Доступ лише для оператора/адміністратора', 'error')
        return redirect(url_for('dashboard'))

    # вхідні параметри (форму робимо методом GET)
    sql_text  = request.args.get('sql') or ""
    date_col  = (request.args.get('date_col') or "").strip() or None
    d1        = (request.args.get('d1') or "").strip() or None
    d2        = (request.args.get('d2') or "").strip() or None
    limit_raw = request.args.get('limit') or "200"
    do_exec   = request.args.get('run') == '1' or bool(sql_text.strip())

    error = None
    headers = []
    rows = []
    limit = None

    if do_exec and sql_text.strip():
        try:
            safe_sql = _sanitize_select(sql_text)
            final_sql, params, limit = _build_wrapped_query(safe_sql, date_col, d1, d2, limit_raw)

            with get_conn() as conn, conn.cursor() as cur:
                # контекст виконання
                cur.execute("SET search_path TO app, public;")
                cur.execute("SET LOCAL statement_timeout = 3000;")
                cur.execute(final_sql, params)
                rows = cur.fetchall()
                headers = [d.name for d in cur.description]

            # CSV експорт
            if request.args.get('format') == 'csv':
                return _csv_response("sql_export.csv", headers, rows)

        except Exception as e:
            error = str(e)

    # приклад за замовчуванням (підказка)
    example = "SELECT id, movement_dt, mtype, product_id, qty, price FROM stock_movements ORDER BY movement_dt DESC"

    return render_template(
        "reports/sql_console.html",
        sql_text=sql_text or example,
        date_col=date_col or "movement_dt",
        d1=d1, d2=d2,
        limit=limit or limit_raw,
        headers=headers,
        rows=rows,
        error=error
    )


def _exec(q, p=()):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SET search_path TO app, public;")
        cur.execute(q, p)
        conn.commit()

def _role(*roles):
    return session.get("user", {}).get("role") in roles

@bp.post("/analytics/overheads/add")
def overheads_add():
    # лише Адмін/Оператор можуть додавати накладні витрати
    if not _role("Admin", "Operator"):
        flash("Доступ лише для Оператора/Адміністратора", "error")
        return redirect(url_for("reports.profitability"))

    d1 = request.args.get("d1") or request.form.get("d1") or None
    d2 = request.args.get("d2") or request.form.get("d2") or None
    amount_raw = (request.form.get("amount") or "").strip()
    note = (request.form.get("note") or "").strip() or None
    created_by = session.get("user", {}).get("login")

    try:
        amount = float(amount_raw)
    except ValueError:
        flash("Невірна сума витрат", "error")
        return redirect(url_for("reports.profitability", d1=d1 or "", d2=d2 or ""))

    _exec("""
        INSERT INTO overheads(period_start, period_end, amount, note, created_by)
        VALUES (NULLIF(%s,'')::date, NULLIF(%s,'')::date, %s::numeric, %s, %s)
    """, (d1 or "", d2 or "", amount, note, created_by))

    flash("Витрати додано", "ok")
    return redirect(url_for("reports.profitability", d1=d1 or "", d2=d2 or ""))

@bp.post("/analytics/overheads/<int:rid>/delete")
def overheads_delete(rid):
    if not _role("Admin", "Operator"):
        flash("Доступ лише для Оператора/Адміністратора", "error")
        return redirect(url_for("reports.profitability"))

    d1 = request.args.get("d1") or ""
    d2 = request.args.get("d2") or ""
    _exec("DELETE FROM overheads WHERE id=%s", (rid,))
    flash("Запис витрат видалено", "ok")
    return redirect(url_for("reports.profitability", d1=d1, d2=d2))