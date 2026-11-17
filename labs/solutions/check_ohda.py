# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Runs the acceptance tests of the reference specification against one state of Ohda.

    uv run labs/solutions/check_ohda.py labs/files/kit/ohda_step4
    uv run labs/solutions/check_ohda.py labs/files/kit/ohda_seeded --expect seeded

It copies the folder to a temporary place, starts the app there on a free port, plays the three
roles over HTTP as a browser would, and prints one line per test. With --expect it also compares
the results with the expected ones of that state and exits 1 on a difference. Nothing is written
into the course folder. The trainer can aim it at a participant's folder when the participant
built on the reference design (same addresses and field names); otherwise test by hand.
"""
import contextlib
import http.cookiejar
import importlib.util
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
CODES = {"alanoud": "4821", "maher": "7306", "yasmin": "2954", "naif": "6178", "tarek": "1743", "hilal": "5617"}

# test id -> (first build step that has it, short name)
TESTS = {
    "AT1": (1, "requester signs in, sends a request, sees it pending"),
    "AT2": (1, "wrong sign-in code refused; no page without sign-in"),
    "AT3": (2, "end date before start date refused with a reason"),
    "AT4": (2, "8 days refused, 7 days accepted (both days counted)"),
    "AT5": (2, "overlap on the same item refused; the day after accepted"),
    "AT6": (3, "approver approves another person's request; requester sees it"),
    "AT7": (3, "approver cannot decide own request; requester cannot open the pending list"),
    "AT8": (4, "return on the due date = 0 late days; two days after = 2; total of returned = 5"),
    "AT9": (4, "requester cannot open admin pages or the export; no export without sign-in"),
    "AT10": (1, "a requester cannot open another person's request by its number"),
    "AT11": (1, "Arabic search ignores hamza and ta marbuta; the receipt page is right to left"),
    "D1": (4, "no personal contact data shown to a requester"),
    "D2": (4, "the data store holds only the fields of the specification"),
    "D3": (4, "no secret written in the files (secrets_scan.py)"),
}
EXPECT_FAIL = {
    "step1": set(), "step2": set(), "step3": set(), "step4": set(),
    "step3_broken": {"AT5"},
    "seeded": {"AT4", "AT7", "AT8", "AT9", "AT10", "AT11", "D1", "D2", "D3"},
}
STEP_OF = {"step1": 1, "step2": 2, "step3": 3, "step3_broken": 3, "step4": 4, "seeded": 4}


class Browser:
    def __init__(self, base):
        self.base = base
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def call(self, path, data=None):
        body = urllib.parse.urlencode(data).encode() if data is not None else None
        try:
            r = self.opener.open(self.base + path, body, timeout=10)
            return r.status, r.geturl(), r.read().decode("utf-8-sig", "replace"), r.headers.get("Content-Type", "")
        except urllib.error.HTTPError as e:
            return e.code, e.geturl(), e.read().decode("utf-8", "replace"), e.headers.get("Content-Type", "")

    def login(self, who, code=None):
        return self.call("/login", {"username": who, "code": code or CODES[who]})


def run_tests(base, folder, db_path, step):
    res = {}

    def new(b, eq, start, end):
        return b.call("/new", {"eq": eq, "start": start, "end": end, "purpose": "اختبار قبول"})

    yasmin, naif, anon = Browser(base), Browser(base), Browser(base)
    yasmin.login("yasmin")
    naif.login("naif")

    # AT1
    new(yasmin, "EQ-005", "2027-03-09", "2027-03-10")
    mine = yasmin.call("/my")[2]
    res["AT1"] = "EQ-005" in mine and "بانتظار الاعتماد" in mine
    # AT2
    wrong = Browser(base)
    res["AT2"] = "غير صحيح" in wrong.login("yasmin", "0000")[2] and 'name="code"' in anon.call("/my")[2]
    # AT10
    res["AT10"] = naif.call("/request?id=1")[0] == 403 and yasmin.call("/request?id=1")[0] == 200
    # AT11
    found = yasmin.call("/?q=" + urllib.parse.quote("اضاءه"))[2]
    receipt = yasmin.call("/request?id=1")[2]
    res["AT11"] = "عدد النتائج: 4" in found and 'dir="rtl"' in receipt[:200]
    if step >= 2:
        s, _, page, _ = new(yasmin, "EQ-008", "2027-03-12", "2027-03-10")
        res["AT3"] = s == 400 and "قبل تاريخ البداية" in page
        eight = new(yasmin, "EQ-008", "2027-03-10", "2027-03-17")
        seven = new(yasmin, "EQ-009", "2027-03-10", "2027-03-16")
        res["AT4"] = eight[0] == 400 and "تزيد على 7" in eight[2] and seven[0] == 200
        clash = new(naif, "EQ-001", "2027-03-12", "2027-03-13")
        after = new(naif, "EQ-001", "2027-03-13", "2027-03-14")
        res["AT5"] = clash[0] == 400 and "محجوزة" in clash[2] and after[0] == 200
    if step >= 3:
        alanoud, hilal, tarek = Browser(base), Browser(base), Browser(base)
        alanoud.login("alanoud"); hilal.login("hilal"); tarek.login("tarek")
        listed = alanoud.call("/pending")
        alanoud.call("/decide", {"id": "11", "what": "approved"})
        res["AT6"] = listed[0] == 200 and "<td>11</td>" in listed[2] and "معتمد" in tarek.call("/my")[2]
        alanoud.call("/decide", {"id": "12", "what": "approved"})
        res["AT7"] = "<td>12</td>" in hilal.call("/pending")[2] and yasmin.call("/pending")[0] == 403
    if step >= 4:
        maher = Browser(base)
        maher.login("maher")
        before = maher.call("/admin")[2]
        on_time = maher.call("/admin/return", {"id": "7"})[1]
        late = maher.call("/admin/return", {"id": "6"})[1]
        res["AT8"] = ("<b>5</b>مجموع أيام التأخير" in before and on_time.endswith("m=back0") and late.endswith("m=back2"))
        a = yasmin.call("/admin")[0]
        e = yasmin.call("/admin/export.csv")[0]
        open1 = anon.call("/admin/export.csv")
        open2 = anon.call("/export.csv")
        res["AT9"] = a == 403 and e == 403 and "csv" not in open1[3] and "csv" not in open2[3]
        res["D1"] = "05000001" not in yasmin.call("/")[2]
        con = sqlite3.connect(db_path)
        cols = {r[1] for r in con.execute("PRAGMA table_info(staff)")}
        con.close()
        res["D2"] = cols == {"id", "staff_no", "username", "name", "role", "salt", "code_hash"}
        spec = importlib.util.spec_from_file_location("secrets_scan", HERE.parent / "files" / "kit" / "secrets_scan.py")
        scan = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(scan)
        res["D3"] = len(scan.scan(folder)) == 0
    return res


@contextlib.contextmanager
def serve(folder):
    """Copies the folder to a temporary place, starts its app and yields (base address, copy)."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        work = Path(tmp) / "ohda"
        shutil.copytree(folder, work, ignore=shutil.ignore_patterns("ohda.db", "__pycache__"))
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        env = dict(os.environ, OHDA_PORT=str(port), OHDA_DB=str(work / "ohda.db"), PYTHONDONTWRITEBYTECODE="1")
        proc = subprocess.Popen([sys.executable, str(work / "app.py")], env=env, cwd=work,
                                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        try:
            base = f"http://127.0.0.1:{port}"
            for _ in range(100):
                try:
                    urllib.request.urlopen(base + "/login", timeout=1).read()
                    break
                except OSError:
                    if proc.poll() is not None:
                        raise SystemExit("the app stopped: " + proc.stderr.read().decode("utf-8", "replace"))
                    time.sleep(0.1)
            yield base, work
        finally:
            proc.terminate()
            proc.wait(timeout=10)
            time.sleep(0.3)  # Windows releases the folder a moment after the process ends
            proc.stderr.close()


def check(folder, expect=None, quiet=False):
    """Returns (results, ok). ok is None without an expectation."""
    step = STEP_OF.get(expect, 4)
    with serve(folder) as (base, work):
        res = run_tests(base, work, work / "ohda.db", step)
    ok = None
    if expect:
        want_fail = EXPECT_FAIL[expect]
        ok = all((not passed) == (t in want_fail) for t, passed in res.items())
    if not quiet:
        for t, (since, name) in TESTS.items():
            if t in res:
                print(f"  {t:<5}{'PASS' if res[t] else 'FAIL'}  {name}")
            else:
                print(f"  {t:<5}--    not built before step {since}")
        if expect:
            print(f"  {'as expected for ' + expect if ok else 'DIFFERENT from what ' + expect + ' should give'}")
    return res, ok


def main():
    args = sys.argv[1:]
    expect = None
    if "--expect" in args:
        i = args.index("--expect")
        expect = args[i + 1]
        del args[i:i + 2]
    if len(args) != 1 or (expect and expect not in EXPECT_FAIL):
        print(__doc__)
        return 2
    print(f"{args[0]}")
    _, ok = check(Path(args[0]), expect)
    return 0 if ok in (True, None) else 1


if __name__ == "__main__":
    sys.exit(main())
