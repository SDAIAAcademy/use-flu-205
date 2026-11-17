# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Runs the solution of every lab of the course and prints PASS or the first difference.

    uv run labs/solutions/run_all.py          every lab
    uv run labs/solutions/run_all.py 1.4      one lab

No model is called. Where a lab has the participant direct a coding agent, a scripted stand-in
plays the agent: its "replies" are the committed states of the prototype under labs/files/kit/,
applied in the order of the lab, and the tests of the specification decide whether each is kept.
"""
import json
import re
import sys
import urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import check_ohda as C  # noqa: E402

FILES = HERE.parent / "files"
KIT = FILES / "kit"
KEY = json.loads((HERE / "key.json").read_text(encoding="utf-8"))


def need(cond, what):
    if not cond:
        raise AssertionError(what)


def table_rows(text, heading):
    """Rows of the first Markdown table after a heading that contains the given words."""
    part = text.split(heading, 1)[1]
    rows = []
    for line in part.splitlines()[1:]:
        if line.startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if not set(cells[0]) <= set("-: "):
                rows.append(cells)
        elif rows:
            break
    return rows[1:]


def lab_1_1():
    text = (FILES / "start" / "tool_requests.md").read_text(encoding="utf-8")
    rows = table_rows(text, "صنّف كل طلب")
    need(len(rows) == 8, f"eight requests expected, found {len(rows)}")
    bins = KEY["lab_1_1"]["bins"]
    need(sorted(bins) == [str(i) for i in range(1, 9)], "the key covers requests 1 to 8")
    count = {b: sum(1 for v in bins.values() if v == b) for b in ("build", "it_review", "hand_over")}
    need(count == {"build": 3, "it_review": 2, "hand_over": 3}, f"bins {count}")
    notes = (FILES / "start" / "need_notes.md").read_text(encoding="utf-8")
    for extra in ("رسالة نصية", "أرقام الهويات", "للضيوف", "الموارد البشرية"):
        need(extra in notes, f"the interview notes should tempt with: {extra}")
    return f"8 requests; key: build {count['build']}, IT review {count['it_review']}, hand over {count['hand_over']}; pass mark {KEY['lab_1_1']['pass']} of 8"


def lab_1_2():
    spec = (FILES / "start" / "spec_reference.md").read_text(encoding="utf-8")
    for n in range(1, 8):
        need(f"## {n}." in spec, f"section {n} of the specification is missing")
    tests = [r for r in table_rows(spec, "## 6.") if r[0].startswith("AT")]
    need(len(tests) == 11, f"11 acceptance tests expected, found {len(tests)}")
    need({r[0] for r in tests} == {t for t in C.TESTS if t.startswith("AT")}, "the tests of the specification and of check_ohda.py differ")
    for r in tests:
        need(all(r[1:4]), f"{r[0]} lacks a role, an action or an expected result")
        need(int(r[4]) == C.TESTS[r[0]][0], f"{r[0]} names another build step than check_ohda.py")
    access = table_rows(spec, "## 5.")
    need(len(access) == 8 and all(len(r) == 5 for r in access), "the access table has 8 actions and 4 columns of roles")
    need(all(r[4] == "لا" for r in access), "nothing is allowed without sign-in")
    template = (FILES / "start" / "spec_template.md").read_text(encoding="utf-8")
    need("AT1" not in template and "## 7." in template, "the template gives no answers away")
    return f"reference specification: 7 sections, {len(access)} actions by 4 roles, {len(tests)} acceptance tests (the outcome asks for 5)"


def lab_1_3():
    ref = (FILES / "start" / "AGENTS_reference.md").read_text(encoding="utf-8")
    heads = re.findall(r"^## (.+)$", ref, flags=re.M)
    need(len(heads) == 8, f"8 sections expected in the instruction file, found {len(heads)}")
    tpl = re.findall(r"^## (.+)$", (FILES / "start" / "AGENTS_template.md").read_text(encoding="utf-8"), flags=re.M)
    need(heads == tpl, "the template and the reference have the same sections")
    res, ok = C.check(KIT / "ohda_step1", "step1", quiet=True)
    need(ok, f"step 1 should pass its tests: {res}")
    passed = sorted(t for t, v in res.items() if v)
    return f"instruction file: 8 sections; stand-in step 1 passes {', '.join(passed)}"


def lab_1_4():
    """The stand-in agent's session: each reply is tested; a failing reply is rolled back."""
    session = [("2", "ohda_step2", "step2"), ("3", "ohda_step3_broken", "step3"), ("3", "ohda_step3", "step3")]
    kept, log = "ohda_step1", []
    for step, state, level in session:
        res, _ = C.check(KIT / state, level, quiet=True)
        failed = sorted(t for t, v in res.items() if not v)
        if failed:
            log.append(f"step {step}: {state} fails {', '.join(failed)} -> rolled back to {kept}")
        else:
            kept = state
            log.append(f"step {step}: {state} passes {len(res)} of {len(res)} -> kept")
    need(log == KEY["lab_1_4"]["log"], "the change log differs:\n  " + "\n  ".join(log))
    res, ok = C.check(KIT / "ohda_step4", "step4", quiet=True)
    need(ok, "the stretch state (step 4) should pass every test")
    return "; ".join(log) + f"; stretch: ohda_step4 passes {len(res)} of {len(res)}"


def admin_numbers(folder):
    with C.serve(folder) as (base, _):
        b = C.Browser(base)
        b.login("maher")
        page = b.call("/admin")[2]
        late = {}
        for m in re.finditer(r"<tr><td>(\d+)</td>.*?</tr>", page):
            cells = re.findall(r"<td>(.*?)</td>", m.group(0))
            if cells[6] == "مُعاد":
                late[m.group(1)] = int(cells[7])
        total = int(re.search(r"<b>(\d+)</b>مجموع أيام التأخير", page).group(1))
        out_now = re.search(r"<b>(\d+ من \d+)</b>قطع معارة الآن", page).group(1)
        overdue = int(re.search(r"<b>(\d+)</b>إعارات متأخرة الآن", page).group(1))
        back6 = b.call("/admin/return", {"id": "6"})[1].rsplit("back", 1)[1]
        y = C.Browser(base)
        y.login("yasmin")
        edge = {}
        cases = {"a": ("EQ-008", "2027-03-12", "2027-03-10"), "b": ("EQ-008", "2027-03-05", "2027-03-06"),
                 "c": ("EQ-009", "2027-03-10", "2027-03-16"), "d": ("EQ-008", "2027-03-10", "2027-03-17"),
                 "e": ("EQ-001", "2027-03-12", "2027-03-13"), "f": ("EQ-013", "2027-03-09", "2027-03-09")}
        for k, (eq, a, z) in cases.items():
            s = y.call("/new", {"eq": eq, "start": a, "end": z, "purpose": "حالة طرفية"})[0]
            edge[k] = "accepted" if s == 200 else "refused"
        hits = int(re.search(r"عدد النتائج: (\d+)", y.call("/?q=" + urllib.parse.quote("اضاءه"))[2]).group(1))
        rtl = 'dir="rtl"' in y.call("/request?id=1")[2][:200]
    return {"late": late, "total": total, "out_now": out_now, "overdue": overdue, "return_6": int(back6),
            "edge": edge, "search_hits": hits, "receipt_rtl": rtl}


def lab_2_1():
    seeded, ref = admin_numbers(KIT / "ohda_seeded"), admin_numbers(KIT / "ohda_step4")
    need(ref == KEY["lab_2_1"]["reference"], f"reference numbers differ: {ref}")
    need(seeded == KEY["lab_2_1"]["seeded"], f"seeded numbers differ: {seeded}")
    return (f"by hand and reference: late days {list(ref['late'].values())}, total {ref['total']}, return of loan 6 = {ref['return_6']}; "
            f"seeded shows {list(seeded['late'].values())}, total {seeded['total']}, return of loan 6 = {seeded['return_6']}; "
            f"edge cases seeded {seeded['edge']}; search hits {seeded['search_hits']} against {ref['search_hits']}; receipt right to left: {seeded['receipt_rtl']} against {ref['receipt_rtl']}")


def role_matrix(folder):
    """What each role gets for the eight actions of the access table: 'yes' or 'no'."""
    out = {}
    with C.serve(folder) as (base, _):
        for who in ("yasmin", "alanoud", "maher", None):
            b = C.Browser(base)
            if who:
                b.login(who)
            r = {}
            r["list"] = "yes" if "<h2>المعدات</h2>" in b.call("/")[2] else "no"
            s, _, page, _ = b.call("/request?id=2")
            r["others_request"] = "yes" if s == 200 and "إيصال الطلب" in page else "no"
            s, _, page, _ = b.call("/pending")
            r["pending_list"] = "yes" if s == 200 and "بانتظار الاعتماد</h2>" in page else "no"
            s, _, page, _ = b.call("/admin")
            r["admin_page"] = "yes" if s == 200 and "لوحة المدير</h2>" in page else "no"
            for path in ("/admin/export.csv", "/export.csv"):
                s, _, page, ctype = b.call(path)
                if "csv" in ctype:
                    r["export"] = "yes"
            r.setdefault("export", "no")
            out[who or "anonymous"] = r
        a, h = C.Browser(base), C.Browser(base)
        a.login("alanoud"); h.login("hilal")
        a.call("/decide", {"id": "12", "what": "approved"})
        out["alanoud"]["approve_own"] = "no" if "<td>12</td>" in h.call("/pending")[2] else "yes"
        y = C.Browser(base)
        y.login("yasmin")
        y.call("/admin/toggle", {"code": "EQ-024"})
        m = C.Browser(base)
        m.login("maher")
        row = re.search(r"EQ-024</span></td><td>.*?</td><td>(.*?)</td>", m.call("/admin")[2]).group(1)
        out["yasmin"]["retire_item"] = "yes" if row == "لا" else "no"
    return out


def lab_2_2():
    seeded, ref = role_matrix(KIT / "ohda_seeded"), role_matrix(KIT / "ohda_step4")
    need(ref == KEY["lab_2_2"]["reference"], f"reference matrix differs: {ref}")
    need(seeded == KEY["lab_2_2"]["seeded"], f"seeded matrix differs: {seeded}")
    diff = sorted(f"{who}.{act}" for who in ref for act in ref[who] if ref[who][act] != seeded[who][act])
    return f"reference matrix as the specification; seeded differs in {len(diff)} cells: {', '.join(diff)}"


def lab_2_3():
    import importlib.util
    spec = importlib.util.spec_from_file_location("secrets_scan", KIT / "secrets_scan.py")
    scan = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(scan)
    found = [(n, line) for n, line, _, _ in scan.scan(KIT / "ohda_seeded")]
    need(found == [tuple(x) for x in KEY["lab_2_3"]["secrets"]], f"scan of the seeded copy: {found}")
    need(scan.scan(KIT / "ohda_step4") == [], "the reference has no secret")
    with C.serve(KIT / "ohda_seeded") as (base, work):
        anon, y = C.Browser(base), C.Browser(base)
        s, _, body, ctype = anon.call("/export.csv")
        need(s == 200 and "csv" in ctype, "the seeded export opens without sign-in")
        head = body.splitlines()[0]
        need("الجوال" in head and "رقم الهوية" in head and len(body.splitlines()) == 15, "export: header and 14 loans")
        y.login("yasmin")
        mobiles = len(re.findall(r"05000001\d\d", y.call("/")[2]))
        need(mobiles == 3, f"three mobiles on the equipment page of a requester, found {mobiles}")
    res, ok = C.check(KIT / "ohda_seeded", "seeded", quiet=True)
    need(ok, "the seeded copy fails exactly the planted tests")
    fixed, ok2 = C.check(KIT / "ohda_step4", "step4", quiet=True)
    need(ok2, "the repaired state passes every test")
    failed = sorted(t for t, v in res.items() if not v)
    need(len(KEY["faults"]) == 10, "ten planted faults in the key")
    return (f"scan: {len(found)} findings in the seeded copy, 0 in the reference; export without sign-in: 14 loans with mobiles and ID numbers; "
            f"3 mobiles shown to a requester; seeded fails {', '.join(failed)}; the repaired state passes {len(fixed)} of {len(fixed)}")


def lab_2_4():
    note = (HERE / "reference" / "handover_note.md").read_text(encoding="utf-8")
    tpl = (FILES / "start" / "handover_template.md").read_text(encoding="utf-8")
    heads = re.findall(r"^## (\d)\. ", note, flags=re.M)
    need(heads == list("1234567") and re.findall(r"^## (\d)\. ", tpl, flags=re.M) == heads, "seven sections in the note and the template")
    for word in ("العنود الجدعان", "ماهر الطريف", "حسام المساعد", "اصطناعية", "2027-03-07"):
        need(word in note, f"the reference note should name: {word}")
    log = (HERE / "reference" / "change_log.md").read_text(encoding="utf-8")
    rows = [r for r in table_rows(log, "# سجل التغييرات") if r[0].isdigit()]
    need(len(rows) == 6 and all(r[4] for r in rows), "six logged changes, each with a test result")
    need(sum("تراجعت" in r[5] for r in rows) == 1, "one rollback in the reference log")
    res, ok = C.check(KIT / "ohda_step4", "step4", quiet=True)
    need(ok, "the fallback prototype passes every test")
    return f"hand-over note: 7 sections; change log: {len(rows)} changes, 1 rollback; fallback prototype passes {len(res)} of {len(res)}"


LABS = {"1.1": lab_1_1, "1.2": lab_1_2, "1.3": lab_1_3, "1.4": lab_1_4,
        "2.1": lab_2_1, "2.2": lab_2_2, "2.3": lab_2_3, "2.4": lab_2_4}


def main():
    wanted = sys.argv[1:] or list(LABS)
    bad = 0
    for lab in wanted:
        try:
            print(f"lab {lab}: PASS  {LABS[lab]()}")
        except AssertionError as e:
            bad += 1
            print(f"lab {lab}: FAIL  {e}")
    print(f"{len(wanted) - bad} of {len(wanted)} labs pass")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
