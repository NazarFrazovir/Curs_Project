from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from db import get_conn
from urllib.parse import urlencode
import math
import json

bp = Blueprint('auth', __name__)

def fetchone(query, params=()):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SET search_path TO app, public;")
        cur.execute(query, params)
        return cur.fetchone()

def fetchall(query, params=()):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SET search_path TO app, public;")
        cur.execute(query, params)
        return cur.fetchall()

def execute(query, params=()):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SET search_path TO app, public;")
        cur.execute(query, params)
        conn.commit()

def _pg_args():
        args = request.args.to_dict(flat=True)
        page = int(args.pop('page', 1) or 1)
        per_page = int(args.pop('per_page', 20) or 20)
        page = 1 if page < 1 else page
        per_page = 5 if per_page < 5 else (100 if per_page > 100 else per_page)
        qs_base = ''
        if args:
            # прибираємо пусті значення, збираємо рядок для ?a=1&b=2…
            clean = {k: v for k, v in args.items() if v not in (None, '', [])}
            if clean:
                qs_base = '&' + urlencode(clean)
        return page, per_page, qs_base, args

def _get_prefs(login):
    row = _exec_one("SELECT theme, density, per_page, default_filter FROM user_prefs WHERE user_login=%s", (login,))
    if not row:
        return {"theme":"dark","density":"normal","per_page":20,"default_filter":{}}
    return {"theme":row[0], "density":row[1], "per_page":row[2], "default_filter":row[3] or {}}



@bp.get("/login")
def login_get():
    return render_template("login.html")

@bp.post("/login")
def login_post():
    login = request.form.get("login","").strip()
    pwd = request.form.get("password","").strip()
    row = fetchone("SELECT login, password, role, last_login FROM keys WHERE login=%s", (login,))
    if not row or row[1] != pwd:
        flash("Невірний логін або пароль", "error")
        return redirect(url_for("auth.login_get"))

    # зберігаємо попередній вхід і оновлюємо last_login
    prev_login = row[3]
    execute("UPDATE keys SET last_login=now() WHERE login=%s", (row[0],))

    session["user"] = {"login": row[0], "role": row[2], "last_login": prev_login}
    session["prefs"] = _get_prefs(row[0])
    flash("Вітаємо, " + row[0], "ok")
    return redirect(url_for("dashboard"))

@bp.get("/logout")
def logout():
    session.clear()
    flash("Вихід виконано", "ok")
    return redirect(url_for("auth.login_get"))


# ======== Адмін: Користувачі (Keys) ========

from flask import request, render_template, redirect, url_for, session, flash
from db import get_conn

def _is_admin():
    return session.get('user', {}).get('role') == 'Admin'

def _require_admin_redirect(default_endpoint='dashboard'):
    if not _is_admin():
        flash('Доступ лише для адміністратора', 'error')
        return redirect(url_for(default_endpoint))
    return None

def _exec_all(q, p=()):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SET search_path TO app, public;")
        cur.execute(q, p)
        return cur.fetchall()

def _exec_one(q, p=()):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SET search_path TO app, public;")
        cur.execute(q, p)
        return cur.fetchone()

def _exec_do(q, p=()):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SET search_path TO app, public;")
        cur.execute(q, p)
        conn.commit()

@bp.get('/admin/users')
def users_list():
    redir = _require_admin_redirect()
    if redir: return redir

    page, per_page, qs_base, args = _pg_args()
    q = (args.get('q') or '').strip()
    like = f"%{q}%"
    where = ""
    params = []
    if q:
        where = "WHERE login ILIKE %s"
        params = [like]

    total = _exec_one(f"SELECT COUNT(*) FROM keys {where}", params)[0]
    pages = max(1, math.ceil(total/per_page))
    offset = (page-1)*per_page

    rows = _exec_all(f"""
      SELECT id, login, password, role
        FROM keys
        {where}
        ORDER BY id DESC
        LIMIT %s OFFSET %s
    """, params + [per_page, offset])

    return render_template('admin_users.html',
        rows=rows, q=q,
        page=page, pages=pages, per_page=per_page, qs_base=qs_base, total=total
    )

@bp.post('/admin/users/add')
def users_add():
    redir = _require_admin_redirect('auth.users_list')
    if redir: return redir
    login = (request.form.get('login') or '').strip()
    password = (request.form.get('password') or '').strip()
    role = request.form.get('role') or 'Guest'
    if not login or not password:
        flash('Логін і пароль обовʼязкові', 'error')
        return redirect(url_for('auth.users_list'))
    try:
        _exec_do("INSERT INTO keys(login,password,role) VALUES(%s,%s,%s)", (login, password, role))
        flash('Користувача додано', 'ok')
    except Exception as e:
        flash(f'Помилка: {e}', 'error')
    return redirect(url_for('auth.users_list'))

@bp.get('/admin/users/<int:rid>/edit')
def users_edit(rid):
    redir = _require_admin_redirect('auth.users_list')
    if redir: return redir
    r = _exec_one("SELECT id, login, password, role FROM keys WHERE id=%s", (rid,))
    if not r:
        flash('Користувача не знайдено', 'error')
        return redirect(url_for('auth.users_list'))
    return render_template('admin_user_edit.html', r=r)

@bp.post('/admin/users/<int:rid>/update')
def users_update(rid):
    redir = _require_admin_redirect('auth.users_list')
    if redir: return redir
    login = (request.form.get('login') or '').strip()
    password = (request.form.get('password') or '').strip()
    role = request.form.get('role') or 'Guest'
    if not login or not password:
        flash('Логін і пароль обовʼязкові', 'error')
        return redirect(url_for('auth.users_edit', rid=rid))
    try:
        _exec_do("UPDATE keys SET login=%s, password=%s, role=%s WHERE id=%s",
                 (login, password, role, rid))
        flash('Зміни збережено', 'ok')
    except Exception as e:
        flash(f'Помилка: {e}', 'error')
    return redirect(url_for('auth.users_list'))

# ======== Forgot password ========


# ======== Forgot password (GET+POST) ========
@bp.route('/forgot', methods=['GET', 'POST'])
def forgot():
    login_q = ""
    rows = None
    if request.method == 'POST':
        login_q = (request.form.get('login') or '').strip()
        if login_q:
            rows = fetchall(
                "SELECT login, password, role FROM keys WHERE login ILIKE %s ORDER BY login",
                (login_q,)  # напр., 'admin' -> точний збіг; хочеш префікс — підстав '%'+login_q+'%'
            )
    return render_template('forgot.html', login_q=login_q, rows=rows)

# ======== Заявка доступу (Гість -> Авторизований) ========

@bp.get('/request-access')
def request_access_get():
    user = session.get('user') or {}
    if not user:
        flash('Спершу увійдіть у систему', 'error')
        return redirect(url_for('auth.login_get'))
    # Показати форму будь-кому; реальна перевірка нижче
    return render_template('access_request.html')

@bp.post('/request-access')
def request_access_post():
    user = session.get('user') or {}
    login = user.get('login')
    role = user.get('role')
    if not login:
        flash('Спершу увійдіть у систему', 'error')
        return redirect(url_for('auth.login_get'))
    if role != 'Guest':
        flash('Заявку можуть надсилати лише користувачі з роллю "Гість"', 'error')
        return redirect(url_for('dashboard'))

    # Знайти його user_id в keys
    k = _exec_one("SELECT id FROM keys WHERE login=%s", (login,))
    if not k:
        flash('Ваш обліковий запис не знайдено в Keys', 'error')
        return redirect(url_for('dashboard'))
    user_id = k[0]

    # Перевірити, чи немає вже "pending"
    exists = _exec_one("SELECT 1 FROM access_requests WHERE user_id=%s AND status='pending'", (user_id,))
    if exists:
        flash('У вас вже є відкрита заявка', 'error')
        return redirect(url_for('dashboard'))

    message = (request.form.get('message') or '').strip() or None
    _exec_do("INSERT INTO access_requests(user_id, message) VALUES(%s, %s)", (user_id, message))
    flash('Заявку відправлено адміністратору', 'ok')
    return redirect(url_for('dashboard'))

# ======== Адмін: перегляд/схвалення/відхилення заявок ========

@bp.get('/admin/access-requests')
def requests_list():
    redir = _require_admin_redirect()
    if redir: return redir
    rows = _exec_all("""
      SELECT ar.id, k.login, k.role, ar.requested_role, ar.message, ar.status,
             ar.requested_at, ar.processed_at, ar.processed_by, ar.admin_comment
      FROM access_requests ar
      JOIN keys k ON k.id=ar.user_id
      ORDER BY ar.requested_at DESC, ar.id DESC
    """)
    return render_template('admin_requests.html', rows=rows)

@bp.post('/admin/access-requests/<int:rid>/approve')
def requests_approve(rid):
    redir = _require_admin_redirect('auth.requests_list')
    if redir: return redir
    admin = session.get('user',{}).get('login') or 'admin'
    # Отримаємо user_id і бажану роль
    row = _exec_one("SELECT user_id, requested_role FROM access_requests WHERE id=%s AND status='pending'", (rid,))
    if not row:
        flash('Заявку не знайдено або вона вже оброблена', 'error')
        return redirect(url_for('auth.requests_list'))
    user_id, requested_role = row
    # Оновлюємо роль у Keys та фіксуємо обробку
    _exec_do("UPDATE keys SET role=%s WHERE id=%s", (requested_role, user_id))
    _exec_do("""
      UPDATE access_requests
         SET status='approved', processed_at=now(), processed_by=%s
       WHERE id=%s
    """, (admin, rid))
    flash('Заявку схвалено, роль оновлено', 'ok')
    return redirect(url_for('auth.requests_list'))

@bp.post('/admin/access-requests/<int:rid>/deny')
def requests_deny(rid):
    redir = _require_admin_redirect('auth.requests_list')
    if redir: return redir
    admin = session.get('user',{}).get('login') or 'admin'
    comment = (request.form.get('admin_comment') or '').strip() or None
    _exec_do("""
      UPDATE access_requests
         SET status='denied', processed_at=now(), processed_by=%s, admin_comment=%s
       WHERE id=%s AND status='pending'
    """, (admin, comment, rid))
    flash('Заявку відхилено', 'ok')
    return redirect(url_for('auth.requests_list'))


# ======== Профіль користувача ========

def _require_login_redirect():
    if not session.get('user'):
        flash('Спершу увійдіть у систему', 'error')
        return redirect(url_for('auth.login_get'))
    return None

@bp.get('/profile')
def profile_get():
    redir = _require_login_redirect()
    if redir: return redir

    login = session['user']['login']
    k = _exec_one("SELECT id, login, role FROM keys WHERE login=%s", (login,))
    if not k:
        flash('Обліковий запис не знайдено', 'error')
        return redirect(url_for('dashboard'))

    # остання заявка користувача (якщо є)
    last_req = _exec_one("""
      SELECT id, requested_role, status, requested_at, processed_at, processed_by, admin_comment
        FROM access_requests
       WHERE user_id = %s
       ORDER BY requested_at DESC
       LIMIT 1
    """, (k[0],))

    return render_template('profile.html', k=k, last_req=last_req)

@bp.post('/profile/change-password')
def profile_change_password():
    redir = _require_login_redirect()
    if redir: return redir

    login = session['user']['login']
    cur_pw = (request.form.get('current_password') or '').strip()
    new_pw = (request.form.get('new_password') or '').strip()
    confirm = (request.form.get('confirm_password') or '').strip()

    if not new_pw:
        flash('Новий пароль не може бути порожнім', 'error')
        return redirect(url_for('auth.profile_get'))
    if new_pw != confirm:
        flash('Підтвердження пароля не співпадає', 'error')
        return redirect(url_for('auth.profile_get'))

    row = _exec_one("SELECT password FROM keys WHERE login=%s", (login,))
    if not row or row[0] != cur_pw:
        flash('Поточний пароль невірний', 'error')
        return redirect(url_for('auth.profile_get'))

    _exec_do("UPDATE keys SET password=%s WHERE login=%s", (new_pw, login))
    flash('Пароль змінено', 'ok')
    return redirect(url_for('auth.profile_get'))

@bp.get("/settings")
def settings_get():
    user = session.get("user")
    if not user:
        return redirect(url_for("auth.login_get"))
    login = user["login"]

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SET search_path TO app, public;")
        # шукаємо по user_login (параметризовано)
        cur.execute("""
            SELECT user_login, theme, density, per_page, default_filter
            FROM user_prefs
            WHERE user_login = %s
            LIMIT 1
        """, (login,))
        row = cur.fetchone()

        if not row:
            # якщо запису немає — створимо з дефолтами
            cur.execute("""
                INSERT INTO user_prefs(user_login)
                VALUES (%s)
                ON CONFLICT (user_login) DO NOTHING
            """, (login,))
            conn.commit()
            prefs = {"theme": "dark", "density": "normal", "per_page": 20, "default_filter": {}}
        else:
            prefs = {
                "theme": row[1] or "dark",
                "density": row[2] or "normal",
                "per_page": int(row[3] or 20),
                "default_filter": row[4] or {},
            }

    return render_template("auth/settings.html", prefs=prefs)

@bp.post("/settings")
def settings_post():
    user = session.get("user")
    if not user:
        return redirect(url_for("auth.login_get"))
    login = user["login"]

    theme = (request.form.get("theme") or "dark").strip()
    density = (request.form.get("density") or "normal").strip()
    try:
        per_page = int(request.form.get("per_page") or 20)
    except ValueError:
        per_page = 20

    # якщо є якісь дефолтні фільтри з форми — зібрати в dict
    default_filter = {}

    import json
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SET search_path TO app, public;")
        cur.execute("""
            INSERT INTO user_prefs (user_login, theme, density, per_page, default_filter, updated_at, updated_by)
            VALUES (%s, %s, %s, %s, %s::jsonb, now(), %s)
            ON CONFLICT (user_login) DO UPDATE
               SET theme = EXCLUDED.theme,
                   density = EXCLUDED.density,
                   per_page = EXCLUDED.per_page,
                   default_filter = EXCLUDED.default_filter,
                   updated_at = now(),
                   updated_by = EXCLUDED.updated_by
        """, (login, theme, density, per_page, json.dumps(default_filter), login))
        conn.commit()

    # одразу оновлюємо сесію для теми/щільності
    session["prefs"] = {
        "theme": theme,
        "density": density,
        "per_page": per_page,
        "default_filter": default_filter
    }

    flash("Налаштування збережено", "ok")
    return redirect(url_for("auth.settings_get"))
