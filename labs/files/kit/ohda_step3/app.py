# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""عُهدة: متتبع إعارة المعدات في وحدة دعم الإنتاج الميداني بمركز وميض (جهة افتراضية).

نموذج أولي للتدريب، على بيانات اصطناعية فقط. يعمل على جهازك وحده:
    uv run app.py
ثم افتح في المتصفح العنوان الذي يطبعه البرنامج.
"""
import csv
import hashlib
import html
import io
import os
import secrets
import sqlite3
from datetime import date
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

HERE = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("OHDA_DB", HERE / "ohda.db"))
PORT = int(os.environ.get("OHDA_PORT", "8205"))
MAX_DAYS = 7
SESSIONS = {}

ROLE_NAMES = {"requester": "مقدّم طلب", "approver": "معتمِد", "admin": "مدير الأداة"}
STATUS_NAMES = {
    "pending": "بانتظار الاعتماد",
    "approved": "معتمد",
    "rejected": "مرفوض",
    "out": "مُسلَّم",
    "returned": "مُعاد",
}


def today():
    """تاريخ اليوم في النموذج: من الملف today.txt إن وُجد، وإلا تاريخ الجهاز."""
    f = HERE / "today.txt"
    if f.exists():
        return date.fromisoformat(f.read_text(encoding="utf-8").strip())
    return date.today()


def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def hash_code(code, salt):
    return hashlib.pbkdf2_hmac("sha256", code.encode(), bytes.fromhex(salt), 50_000).hex()


def late_days(end, returned_on):
    """أيام التأخير: عدد الأيام بعد تاريخ نهاية الإعارة، ولا تقل عن صفر."""
    return max(0, (returned_on - end).days)


def loan_days(start, end):
    """مدة الإعارة بالأيام، ويُحسب يوم البداية ويوم النهاية كلاهما."""
    return (end - start).days + 1


def fold(text):
    """توحيد الكتابة العربية للبحث: الهمزات والتاء المربوطة والألف المقصورة والتشكيل."""
    out = []
    for ch in text.strip().lower():
        if ch in "أإآٱ":
            ch = "ا"
        elif ch == "ة":
            ch = "ه"
        elif ch == "ى":
            ch = "ي"
        elif ch == "ـ" or "ً" <= ch <= "ْ":
            continue
        out.append(ch)
    return "".join(out)


def init_db():
    if DB_PATH.exists():
        return
    con = db()
    con.executescript(
        """
        CREATE TABLE staff (id INTEGER PRIMARY KEY, staff_no TEXT, username TEXT UNIQUE,
            name TEXT, role TEXT, salt TEXT, code_hash TEXT);
        CREATE TABLE equipment (code TEXT PRIMARY KEY, name TEXT, category TEXT,
            active INTEGER DEFAULT 1);
        CREATE TABLE loans (id INTEGER PRIMARY KEY, equipment_code TEXT, requester_id INTEGER,
            start_date TEXT, end_date TEXT, purpose TEXT, status TEXT, decided_by INTEGER,
            returned_on TEXT, late_days INTEGER);
        """
    )
    with open(HERE / "staff.csv", encoding="utf-8-sig", newline="") as f:
        for i, r in enumerate(csv.DictReader(f), start=1):
            salt = hashlib.sha256(("ohda" + r["username"]).encode()).hexdigest()[:16]
            con.execute(
                "INSERT INTO staff VALUES (?,?,?,?,?,?,?)",
                (i, r["staff_no"], r["username"], r["name"], r["role"], salt,
                 hash_code(r["sign_in_code"], salt)),
            )
    with open(HERE / "equipment.csv", encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            con.execute("INSERT INTO equipment VALUES (?,?,?,1)", (r["code"], r["name"], r["category"]))
    with open(HERE / "loans_seed.csv", encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            who = con.execute("SELECT id FROM staff WHERE username=?", (r["requester"],)).fetchone()["id"]
            late = None
            if r["returned_on"]:
                late = late_days(date.fromisoformat(r["end_date"]), date.fromisoformat(r["returned_on"]))
            con.execute(
                "INSERT INTO loans VALUES (?,?,?,?,?,?,?,?,?,?)",
                (int(r["id"]), r["equipment_code"], who, r["start_date"], r["end_date"],
                 r["purpose"], r["status"], None, r["returned_on"] or None, late),
            )
    con.commit()
    con.close()


CSS = """
body{font-family:Tahoma,'Segoe UI',sans-serif;margin:0;background:#f4f5f7;color:#1c2333;line-height:1.7}
header{background:#12284b;color:#fff;padding:10px 18px;display:flex;gap:16px;align-items:center;flex-wrap:wrap}
header b{font-size:20px} header a{color:#bfe9e4;text-decoration:none} header .sp{flex:1}
main{max-width:980px;margin:18px auto;padding:0 14px}
table{border-collapse:collapse;width:100%;background:#fff} th,td{border:1px solid #d5d9e0;padding:6px 10px;text-align:start}
th{background:#e9edf3} .ok{color:#0a6b4f} .bad{color:#a12626;font-weight:bold}
.box{background:#fff;border:1px solid #d5d9e0;border-radius:8px;padding:12px 16px;margin:12px 0}
.msg{background:#fdecea;border:1px solid #e0a39c;border-radius:8px;padding:10px 14px;margin:12px 0}
.done{background:#e6f5ef;border-color:#8fcab4}
input,select,button{font:inherit;padding:5px 8px} button{cursor:pointer}
.ltr{direction:ltr;unicode-bidi:isolate;display:inline-block} .stats{display:flex;gap:12px;flex-wrap:wrap}
.stats div{background:#fff;border:1px solid #d5d9e0;border-radius:8px;padding:10px 16px} .stats b{font-size:26px;display:block}
"""


def page(title, body, user=None, rtl=True):
    nav = ""
    if user:
        links = ['<a href="/">المعدات</a>', '<a href="/my">طلباتي</a>']
        if user["role"] in ("approver", "admin"):
            links.append('<a href="/pending">بانتظار الاعتماد</a>')
        nav = " · ".join(links) + (
            f'<span class="sp"></span><span>{html.escape(user["name"])} ({ROLE_NAMES[user["role"]]})</span>'
            ' <a href="/logout">خروج</a>'
        )
    head = '<html lang="ar" dir="rtl">' if rtl else '<html lang="en">'
    return (
        f"<!doctype html>{head}<head><meta charset='utf-8'>"
        f"<meta name='viewport' content='width=device-width,initial-scale=1'><title>{html.escape(title)} · عُهدة</title>"
        f"<style>{CSS}</style></head><body><header><b>عُهدة</b>{nav}</header><main>"
        f"<p>تاريخ اليوم في النموذج: <span class='ltr'>{today().isoformat()}</span> · بيانات اصطناعية للتدريب</p>"
        f"{body}</main></body></html>"
    )


def msg(text, ok=False):
    return f'<div class="msg{" done" if ok else ""}">{html.escape(text)}</div>'


def check_request(con, eq_code, start_s, end_s, purpose):
    """قواعد الطلب. تعيد نص سبب الرفض، أو None إن كان الطلب مقبولًا."""
    try:
        start, end = date.fromisoformat(start_s), date.fromisoformat(end_s)
    except ValueError:
        return "اكتب تاريخ البداية وتاريخ النهاية."
    eq = con.execute("SELECT * FROM equipment WHERE code=?", (eq_code,)).fetchone()
    if eq is None or not eq["active"]:
        return "هذه القطعة غير متاحة للإعارة."
    if not purpose.strip() or len(purpose) > 200:
        return "اكتب الغرض من الإعارة في 200 حرف على الأكثر."
    if end < start:
        return "تاريخ النهاية قبل تاريخ البداية."
    if start < today():
        return "تاريخ البداية قبل تاريخ اليوم."
    if loan_days(start, end) > MAX_DAYS:
        return f"مدة الإعارة تزيد على {MAX_DAYS} أيام."
    clash = con.execute(
        "SELECT id FROM loans WHERE equipment_code=? AND status IN ('pending','approved','out')"
        " AND start_date<=? AND end_date>=?",
        (eq_code, end_s, start_s),
    ).fetchone()
    if clash:
        return f"القطعة محجوزة في هذه المدة (الطلب رقم {clash['id']})."
    return None


class Handler(BaseHTTPRequestHandler):
    server_version = "Ohda/1"

    def log_message(self, *args):
        pass

    # ---------- أدوات مساعدة ----------
    def user(self):
        jar = cookies.SimpleCookie(self.headers.get("Cookie", ""))
        sid = jar["ohda_sid"].value if "ohda_sid" in jar else None
        uid = SESSIONS.get(sid)
        if uid is None:
            return None
        con = db()
        row = con.execute("SELECT * FROM staff WHERE id=?", (uid,)).fetchone()
        con.close()
        return row

    def send(self, body, status=200, ctype="text/html; charset=utf-8", headers=()):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        for k, v in headers:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def redirect(self, where, headers=()):
        self.send_response(303)
        self.send_header("Location", where)
        self.send_header("Content-Length", "0")
        for k, v in headers:
            self.send_header(k, v)
        self.end_headers()

    def forbidden(self, user):
        self.send(page("غير مسموح", msg("غير مسموح: هذه الصفحة ليست من صلاحيات دورك."), user), 403)

    def form(self):
        n = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(n).decode("utf-8")
        return {k: v[0] for k, v in parse_qs(raw, keep_blank_values=True).items()}

    # ---------- GET ----------
    def do_GET(self):
        url = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        user = self.user()
        path = url.path
        if path == "/login" or user is None:
            if path not in ("/", "/login"):
                return self.redirect("/login")
            return self.send(self.login_page(q.get("e")))
        if path == "/logout":
            jar = cookies.SimpleCookie(self.headers.get("Cookie", ""))
            if "ohda_sid" in jar:
                SESSIONS.pop(jar["ohda_sid"].value, None)
            return self.redirect("/login", [("Set-Cookie", "ohda_sid=; Max-Age=0; Path=/")])
        if path == "/":
            return self.send(self.equipment_page(user, q.get("q", ""), q.get("m")))
        if path == "/new":
            return self.send(self.new_page(user, q.get("eq", ""), None, {}))
        if path == "/my":
            return self.send(self.my_page(user))
        if path == "/request":
            return self.request_page(user, q.get("id", ""))
        if path == "/pending":
            if user["role"] not in ("approver", "admin"):
                return self.forbidden(user)
            return self.send(self.pending_page(user, q.get("m")))
        self.send(page("غير موجودة", msg("الصفحة غير موجودة."), user), 404)

    # ---------- POST ----------
    def do_POST(self):
        url = urlparse(self.path)
        f = self.form()
        if url.path == "/login":
            return self.do_login(f)
        user = self.user()
        if user is None:
            return self.redirect("/login")
        if url.path == "/new":
            return self.do_new(user, f)
        if url.path == "/decide":
            return self.do_decide(user, f)
        self.send(page("غير موجودة", msg("الصفحة غير موجودة."), user), 404)

    # ---------- الدخول ----------
    def login_page(self, error=None):
        body = "<h2>الدخول</h2>"
        if error:
            body += msg("اسم المستخدم أو رمز الدخول غير صحيح.")
        body += (
            '<form method="post" action="/login" class="box">'
            '<p><label>اسم المستخدم <input name="username" dir="ltr" required></label></p>'
            '<p><label>رمز الدخول <input name="code" type="password" dir="ltr" required></label></p>'
            "<button>دخول</button></form>"
            "<p>الحسابات كلها تجريبية، ورموزها في صفحة المختبر.</p>"
        )
        return page("الدخول", body)

    def do_login(self, f):
        con = db()
        row = con.execute("SELECT * FROM staff WHERE username=?", (f.get("username", "").strip().lower(),)).fetchone()
        con.close()
        if row is None or hash_code(f.get("code", ""), row["salt"]) != row["code_hash"]:
            return self.redirect("/login?e=1")
        sid = secrets.token_urlsafe(24)
        SESSIONS[sid] = row["id"]
        self.redirect("/", [("Set-Cookie", f"ohda_sid={sid}; HttpOnly; SameSite=Lax; Path=/")])

    # ---------- المعدات ----------
    def equipment_page(self, user, query, m=None):
        con = db()
        rows = con.execute("SELECT * FROM equipment ORDER BY code").fetchall()
        out_now = {
            r["equipment_code"]: r
            for r in con.execute(
                "SELECT l.*, s.name AS who FROM loans l JOIN staff s ON s.id=l.requester_id"
                " WHERE l.status='out'"
            )
        }
        con.close()
        if query:
            key = fold(query)
            rows = [r for r in rows if key in fold(r["name"]) or key in fold(r["category"]) or key in r["code"].lower()]
        body = "<h2>المعدات</h2>"
        if m == "sent":
            body += msg("سُجّل طلبك، وهو بانتظار الاعتماد.", ok=True)
        body += (
            f'<form method="get" action="/" class="box"><label>بحث <input name="q" value="{html.escape(query)}"></label> '
            f"<button>ابحث</button> <span>عدد النتائج: {len(rows)}</span></form>"
            "<table><tr><th>الرمز</th><th>القطعة</th><th>الفئة</th><th>الحالة اليوم</th><th></th></tr>"
        )
        for r in rows:
            if not r["active"]:
                state = '<span class="bad">خارج الخدمة</span>'
            elif r["code"] in out_now:
                o = out_now[r["code"]]
                state = f'مُعارة حتى <span class="ltr">{o["end_date"]}</span>'
                if user["role"] in ("approver", "admin"):
                    state += f' · عند {html.escape(o["who"])}'
            else:
                state = '<span class="ok">في المستودع</span>'
            ask = f'<a href="/new?eq={quote(r["code"])}">اطلب</a>' if r["active"] else ""
            body += (
                f'<tr><td><span class="ltr">{r["code"]}</span></td><td>{html.escape(r["name"])}</td>'
                f'<td>{html.escape(r["category"])}</td><td>{state}</td><td>{ask}</td></tr>'
            )
        body += "</table>"
        return page("المعدات", body, user)

    # ---------- طلب جديد ----------
    def new_page(self, user, eq_code, error, f):
        con = db()
        rows = con.execute("SELECT * FROM equipment WHERE active=1 ORDER BY code").fetchall()
        con.close()
        opts = "".join(
            f'<option value="{r["code"]}"{" selected" if r["code"] == eq_code else ""}>'
            f'{r["code"]} · {html.escape(r["name"])}</option>'
            for r in rows
        )
        body = "<h2>طلب إعارة جديد</h2>"
        if error:
            body += msg("لم يُسجَّل الطلب: " + error)
        body += (
            '<form method="post" action="/new" class="box">'
            f'<p><label>القطعة <select name="eq">{opts}</select></label></p>'
            f'<p><label>من تاريخ <input type="date" name="start" value="{html.escape(f.get("start", ""))}" required></label> '
            f'<label>إلى تاريخ <input type="date" name="end" value="{html.escape(f.get("end", ""))}" required></label></p>'
            f'<p><label>الغرض <input name="purpose" size="50" maxlength="200" value="{html.escape(f.get("purpose", ""))}" required></label></p>'
            "<button>أرسل الطلب</button></form>"
            f"<p>القواعد: المدة {MAX_DAYS} أيام على الأكثر بحساب يومي البداية والنهاية، ولا تُحجز قطعة في مدة محجوزة.</p>"
        )
        return page("طلب جديد", body, user)

    def do_new(self, user, f):
        con = db()
        error = check_request(con, f.get("eq", ""), f.get("start", ""), f.get("end", ""), f.get("purpose", ""))
        if error:
            con.close()
            return self.send(self.new_page(user, f.get("eq", ""), error, f), 400)
        con.execute(
            "INSERT INTO loans (equipment_code, requester_id, start_date, end_date, purpose, status)"
            " VALUES (?,?,?,?,?, 'pending')",
            (f["eq"], user["id"], f["start"], f["end"], f["purpose"].strip()),
        )
        con.commit()
        con.close()
        self.redirect("/?m=sent")

    # ---------- طلباتي والطلب الواحد ----------
    LOAN_SQL = (
        "SELECT l.*, e.name AS eq_name, s.name AS who FROM loans l"
        " JOIN equipment e ON e.code=l.equipment_code JOIN staff s ON s.id=l.requester_id "
    )

    def loans_table(self, rows, with_who=False, action=None):
        head = "<th>رقم</th><th>القطعة</th>" + ("<th>مقدّم الطلب</th>" if with_who else "")
        head += "<th>من</th><th>إلى</th><th>المدة بالأيام</th><th>الحالة</th><th>أيام التأخير</th><th></th>"
        out = f"<table><tr>{head}</tr>"
        for r in rows:
            d = loan_days(date.fromisoformat(r["start_date"]), date.fromisoformat(r["end_date"]))
            late = "" if r["late_days"] is None else str(r["late_days"])
            who = f"<td>{html.escape(r['who'])}</td>" if with_who else ""
            extra = action(r) if action else f'<a href="/request?id={r["id"]}">الإيصال</a>'
            out += (
                f'<tr><td>{r["id"]}</td><td><span class="ltr">{r["equipment_code"]}</span> {html.escape(r["eq_name"])}</td>{who}'
                f'<td><span class="ltr">{r["start_date"]}</span></td><td><span class="ltr">{r["end_date"]}</span></td>'
                f'<td>{d}</td><td>{STATUS_NAMES[r["status"]]}</td><td>{late}</td><td>{extra}</td></tr>'
            )
        return out + "</table>"

    def my_page(self, user):
        con = db()
        rows = con.execute(self.LOAN_SQL + "WHERE l.requester_id=? ORDER BY l.id DESC", (user["id"],)).fetchall()
        con.close()
        body = "<h2>طلباتي</h2>" + (self.loans_table(rows) if rows else "<p>لا طلبات لك بعد.</p>")
        return page("طلباتي", body, user)

    def request_page(self, user, rid):
        con = db()
        r = con.execute(self.LOAN_SQL + "WHERE l.id=?", (rid,)).fetchone()
        con.close()
        if r is None:
            return self.send(page("غير موجود", msg("لا طلب بهذا الرقم."), user), 404)
        if r["requester_id"] != user["id"] and user["role"] not in ("approver", "admin"):
            return self.forbidden(user)
        body = (
            f"<h2>إيصال الطلب رقم {r['id']}</h2><div class='box'>"
            f"<p>القطعة: <span class='ltr'>{r['equipment_code']}</span> {html.escape(r['eq_name'])}</p>"
            f"<p>مقدّم الطلب: {html.escape(r['who'])}</p>"
            f"<p>من <span class='ltr'>{r['start_date']}</span> إلى <span class='ltr'>{r['end_date']}</span></p>"
            f"<p>الغرض: {html.escape(r['purpose'])}</p><p>الحالة: {STATUS_NAMES[r['status']]}</p></div>"
        )
        return self.send(page("الإيصال", body, user))

    # ---------- الاعتماد ----------
    def pending_page(self, user, m=None):
        con = db()
        rows = con.execute(self.LOAN_SQL + "WHERE l.status='pending' ORDER BY l.id").fetchall()
        con.close()

        def action(r):
            if r["requester_id"] == user["id"]:
                return "طلبك أنت: يعتمده غيرك"
            return (
                f'<form method="post" action="/decide" style="display:inline"><input type="hidden" name="id" value="{r["id"]}">'
                '<button name="what" value="approved">اعتمد</button> <button name="what" value="rejected">ارفض</button></form>'
            )

        notes = {"own": "لا تعتمد طلبك أنت: يعتمده معتمِد آخر.", "done": "سُجّل القرار.",
                 "gone": "هذا الطلب لم يعد بانتظار الاعتماد."}
        body = "<h2>طلبات بانتظار الاعتماد</h2>"
        if m in notes:
            body += msg(notes[m], ok=(m == "done"))
        body += self.loans_table(rows, with_who=True, action=action) if rows else "<p>لا طلبات بانتظار الاعتماد.</p>"
        return page("بانتظار الاعتماد", body, user)

    def do_decide(self, user, f):
        if user["role"] not in ("approver", "admin"):
            return self.forbidden(user)
        what = f.get("what")
        con = db()
        r = con.execute("SELECT * FROM loans WHERE id=?", (f.get("id", ""),)).fetchone()
        if r is None or r["status"] != "pending" or what not in ("approved", "rejected"):
            con.close()
            return self.redirect("/pending?m=gone")
        if r["requester_id"] == user["id"]:
            con.close()
            return self.redirect("/pending?m=own")
        con.execute("UPDATE loans SET status=?, decided_by=? WHERE id=?", (what, user["id"], r["id"]))
        con.commit()
        con.close()
        self.redirect("/pending?m=done")


def main():
    init_db()
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Ohda is running. Open http://127.0.0.1:{PORT}/ in your browser. Stop with Ctrl+C.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
