# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""فحص بسيط للأسرار في مجلد: مفاتيح وكلمات سر مكتوبة داخل الملفات.

    uv run secrets_scan.py ohda_seeded

يقرأ الملفات النصية (py, txt, md, json, env, html, js, toml, yml) ولا يرسل شيئًا إلى أي مكان.
هو فحص تدريبي: لا يغني عن فحص الجهة المعتمد (مثل gitleaks يشغّله الميسِّر، أو فحص المنصة).
"""
import re
import sys
from pathlib import Path

KINDS = {".py", ".txt", ".md", ".json", ".env", ".html", ".js", ".toml", ".yml", ".yaml", ".ini", ".cfg"}
RULES = [
    ("قيمة مكتوبة لاسم يدل على سر",
     re.compile(r"(?i)\b\w*(key|secret|token|password|passwd|pwd)\w*\s*[:=]\s*[\"']([^\"'\s]{8,})[\"']")),
    ("كلمة سر مكتوبة في ملاحظة",
     re.compile(r"(?i)(كلمة\s+(?:ال)?سر|كلمة\s+المرور|password|passcode)[^:\n]{0,40}:\s*(\S{6,})")),
    ("سلسلة طويلة تشبه مفتاحًا",
     re.compile(r"[\"']()([A-Za-z0-9_\-]*[0-9a-f]{32,}[A-Za-z0-9_\-]*)[\"']")),
]


def mask(value):
    return value[:4] + "…" + f"({len(value)} حرفًا)"


def scan(folder):
    found = []
    for path in sorted(Path(folder).rglob("*")):
        if not path.is_file() or path.suffix.lower() not in KINDS or path.name == "secrets_scan.py":
            continue
        for n, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
            for reason, rule in RULES:
                m = rule.search(line)
                if m:
                    found.append((path.relative_to(folder).as_posix(), n, reason, mask(m.group(2))))
                    break
    return found


def main():
    if len(sys.argv) != 2 or not Path(sys.argv[1]).is_dir():
        print("الاستخدام: uv run secrets_scan.py <المجلد>")
        return 2
    found = scan(sys.argv[1])
    for name, n, reason, value in found:
        print(f"{name}:{n}: {reason}: {value}")
    print(f"عدد ما وُجد: {len(found)}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
