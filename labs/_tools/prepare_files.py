# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Writes the Ohda kit of the course: the synthetic data and every state of the prototype.

Run from anywhere:  uv run labs/_tools/prepare_files.py
Same bytes on every run. Nothing here is real: the centre, the staff and the numbers are invented.

States written under labs/files/kit/ (a folder and a zip of the same name each):
  ohda_step1 .. ohda_step4   the reference prototype after each build step (step 4 is the reference)
  ohda_step3_broken          step 3 as a careless change left it: the overlap rule is gone
  ohda_seeded                step 4 with ten planted faults (labs 2.1 to 2.3)
"""
import csv
import io
import zipfile
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
KIT = TOOLS.parent / "files" / "kit"
TODAY = "2027-03-07"

STAFF = [
    # staff_no, username, name, role, sign_in_code, mobile (seeded only), id_number (seeded only)
    ("S-101", "alanoud", "العنود الجدعان", "approver", "4821", "0500000101", "1000000101"),
    ("S-102", "maher", "ماهر الطريف", "admin", "7306", "0500000102", "1000000102"),
    ("S-103", "yasmin", "ياسمين الأحمري", "requester", "2954", "0500000103", "1000000103"),
    ("S-104", "naif", "نايف الحميدي", "requester", "6178", "0500000104", "1000000104"),
    ("S-105", "rashid", "رشيد البحيري", "requester", "3462", "0500000105", "1000000105"),
    ("S-106", "bodour", "بدور الخويطر", "requester", "8590", "0500000106", "1000000106"),
    ("S-107", "tarek", "طارق المشعان", "requester", "1743", "0500000107", "1000000107"),
    ("S-108", "jamal", "جمال الزومان", "requester", "9025", "0500000108", "1000000108"),
    ("S-109", "hilal", "هلال النصبان", "approver", "5617", "0500000109", "1000000109"),
]

EQUIPMENT = [
    ("كاميرات", ["كاميرا ميدانية W-200", "كاميرا ميدانية W-200", "كاميرا استوديو W-500",
                 "كاميرا محمولة صغيرة", "كاميرا جوية مسيّرة"]),
    ("عدسات", ["عدسة واسعة 16-35", "عدسة متوسطة 24-70", "عدسة مقرّبة 70-200", "عدسة ثابتة 50"]),
    ("صوت", ["ميكروفون لاسلكي", "ميكروفون لاسلكي", "ميكروفون اتجاهي", "مسجّل صوت ميداني",
             "سماعات مراقبة"]),
    ("إضاءة", ["طقم إضاءة LED", "طقم إضاءة LED", "إضاءة محمولة صغيرة", "عاكس ضوء قابل للطي"]),
    ("حوامل", ["حامل ثلاثي ثقيل", "حامل ثلاثي خفيف", "مثبّت كاميرا يدوي"]),
    ("حواسيب", ["حاسوب مونتاج محمول", "حاسوب مونتاج محمول", "أسطوانة تخزين خارجية"]),
]

LOANS = [
    # id, equipment, requester, start, end, status, returned_on, purpose
    (1, "EQ-001", "yasmin", "2027-02-15", "2027-02-18", "returned", "2027-02-18", "تصوير تقرير سوق الحرفيين"),
    (2, "EQ-006", "naif", "2027-02-16", "2027-02-20", "returned", "2027-02-23", "لقطات واسعة لبرنامج المدن"),
    (3, "EQ-010", "rashid", "2027-02-21", "2027-02-22", "returned", "2027-02-21", "مقابلة في مقر المركز"),
    (4, "EQ-015", "bodour", "2027-02-22", "2027-02-28", "returned", "2027-03-02", "تصوير حلقات الاستوديو الخارجي"),
    (5, "EQ-019", "tarek", "2027-02-24", "2027-02-26", "returned", "2027-02-26", "تغطية معرض الكتاب"),
    (6, "EQ-002", "jamal", "2027-03-01", "2027-03-05", "out", "", "تصوير وثائقي المزارع"),
    (7, "EQ-011", "yasmin", "2027-03-04", "2027-03-08", "out", "", "مقابلات برنامج الصباح"),
    (8, "EQ-016", "naif", "2027-03-06", "2027-03-12", "out", "", "تصوير ليلي لبرنامج المدن"),
    (9, "EQ-003", "rashid", "2027-03-08", "2027-03-10", "approved", "", "تسجيل ندوة في القاعة الكبرى"),
    (10, "EQ-007", "bodour", "2027-03-09", "2027-03-15", "approved", "", "تصوير سلسلة الطهاة"),
    (11, "EQ-001", "tarek", "2027-03-10", "2027-03-12", "pending", "", "تغطية افتتاح المتحف"),
    (12, "EQ-020", "alanoud", "2027-03-10", "2027-03-11", "pending", "", "تجربة تصوير لتدريب الفريق"),
    (13, "EQ-012", "jamal", "2027-03-09", "2027-03-10", "rejected", "", "تسجيل صوتي خارج نطاق الوحدة"),
    (14, "EQ-022", "yasmin", "2027-03-12", "2027-03-14", "pending", "", "مونتاج في موقع التصوير"),
]

SEEDED_NOTES = """ملاحظات التشغيل (نسخة ماهر)
- لتشغيل الأداة: uv run app.py
- كلمة سر إعادة الضبط للمدير: Wameedh#Store2027
- رابط التصدير الذي أرسلته إلى الإدارة يعمل دون دخول: /export.csv
"""


def csv_bytes(header, rows):
    buf = io.StringIO(newline="")
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    w.writerows(rows)
    return buf.getvalue().encode("utf-8")


def render(master, step, seeded=False, broken=False):
    """Keeps the lines whose #@if conditions hold for this state and drops the markers."""
    env = {"step": step, "seeded": seeded, "broken": broken}
    out, stack = [], []
    for line in master.splitlines():
        s = line.strip()
        if s.startswith("#@if "):
            stack.append(bool(eval(s[5:], {}, env)))
        elif s == "#@else":
            stack[-1] = not stack[-1]
        elif s == "#@endif":
            stack.pop()
        elif all(stack):
            out.append(line)
    assert not stack, "unbalanced markers"
    text = "\n".join(out) + "\n"
    while "\n\n\n\n" in text:
        text = text.replace("\n\n\n\n", "\n\n\n")
    compile(text, "app.py", "exec")
    return text.encode("utf-8")


def state_files(master, step, seeded=False, broken=False):
    equipment = []
    for category, names in EQUIPMENT:
        for name in names:
            equipment.append((f"EQ-{len(equipment) + 1:03d}", name, category))
    assert len(equipment) == 24
    if seeded:
        staff = csv_bytes(["staff_no", "username", "name", "role", "sign_in_code", "mobile", "id_number"], STAFF)
    else:
        staff = csv_bytes(["staff_no", "username", "name", "role", "sign_in_code"], [r[:5] for r in STAFF])
    loans = [(i, eq, who, a, b, purpose, status, back) for i, eq, who, a, b, status, back, purpose in LOANS]
    files = {
        "app.py": render(master, step, seeded, broken),
        "equipment.csv": csv_bytes(["code", "name", "category"], equipment),
        "staff.csv": staff,
        "loans_seed.csv": csv_bytes(
            ["id", "equipment_code", "requester", "start_date", "end_date", "purpose", "status", "returned_on"], loans),
        "today.txt": (TODAY + "\n").encode("utf-8"),
    }
    if seeded:
        files["notes.txt"] = SEEDED_NOTES.encode("utf-8")
    return files


def write_state(name, files):
    folder = KIT / name
    folder.mkdir(parents=True, exist_ok=True)
    for fname, data in files.items():
        (folder / fname).write_bytes(data)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for fname in sorted(files):
            info = zipfile.ZipInfo(f"{name}/{fname}", date_time=(2027, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, files[fname])
    (KIT / f"{name}.zip").write_bytes(buf.getvalue())
    return len(files)


def main():
    master = (TOOLS / "ohda_master.py").read_text(encoding="utf-8")
    KIT.mkdir(parents=True, exist_ok=True)
    states = {
        "ohda_step1": dict(step=1),
        "ohda_step2": dict(step=2),
        "ohda_step3": dict(step=3),
        "ohda_step3_broken": dict(step=3, broken=True),
        "ohda_step4": dict(step=4),
        "ohda_seeded": dict(step=4, seeded=True),
    }
    for name, opts in states.items():
        n = write_state(name, state_files(master, **opts))
        print(f"{name}: {n} files, app.py {len((KIT / name / 'app.py').read_bytes())} bytes")


if __name__ == "__main__":
    main()
