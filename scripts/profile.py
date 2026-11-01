#!/usr/bin/env python3
"""데이터 첫 점검 — 표준 라이브러리만 사용.

사용: python3 .cofa/tools/profile.py <파일> [<파일> ...] [--top 5]
지원: CSV / TSV / TXT(구분자 자동) / JSON(객체 배열). XLSX는 openpyxl이 있을 때만.
개인정보로 보이는 열은 값을 가리고 개수·형식만 보인다.
exit 0 정상 / 1 읽기 실패 있음 / 2 읽은 행이 0건
"""
import argparse
import csv
import io
import json
import os
import re
import statistics
import sys
from collections import Counter

MISSING = {"", "na", "n/a", "nan", "null", "none", "-", "nil", "#n/a"}
PII_NAME = re.compile(
    r"(name|이름|성명|phone|tel|mobile|전화|휴대|연락처|e-?mail|메일|address|addr|주소|"
    r"birth|생년|생일|주민|ssn|resident|account|계좌|card|카드|passport|여권)",
    re.I,
)
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
PHONE = re.compile(r"^(\+?\d{1,3}[- ]?)?0?\d{1,2}[- ]?\d{3,4}[- ]?\d{4}$")
DATE = re.compile(r"^\d{4}[-/.]\d{1,2}[-/.]\d{1,2}([ T]\d{1,2}:\d{2}(:\d{2})?)?")
TIME = re.compile(r"^\d{1,2}:\d{2}(:\d{2})?$")
INT = re.compile(r"^[+-]?\d+$")
FLOAT = re.compile(r"^[+-]?(\d+\.\d*|\.\d+|\d+)([eE][+-]?\d+)?$")
KEYISH = re.compile(r"(id|key|code|no|num|코드|번호|아이디)$", re.I)


def read_text(path):
    raw = open(path, "rb").read()
    for enc in ("utf-8-sig", "utf-8", "cp949", "euc-kr"):
        try:
            return raw.decode(enc), enc
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace"), "utf-8(깨진 문자 대체)"


def load_table(path):
    """(columns, rows, note) 반환. rows는 문자열 리스트의 리스트."""
    ext = os.path.splitext(path)[1].lower()
    if ext in (".xlsx", ".xlsm"):
        try:
            import openpyxl  # 있을 때만
        except ImportError:
            raise RuntimeError("XLSX는 openpyxl이 없어 읽지 못함 → CSV로 변환하거나 pandas/openpyxl 사용 가능 여부 확인")
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        ws = wb.worksheets[0]
        it = ws.iter_rows(values_only=True)
        header = [str(c) if c is not None else "" for c in next(it)]
        rows = [["" if c is None else str(c) for c in r] for r in it]
        note = f"시트 {len(wb.worksheets)}개 중 첫 시트 '{ws.title}'만 읽음"
        return header, rows, note
    text, enc = read_text(path)
    if ext == ".json":
        data = json.loads(text)
        if isinstance(data, dict):
            lists = [(k, v) for k, v in data.items() if isinstance(v, list)]
            if not lists:
                raise RuntimeError("JSON 최상위에 레코드 배열이 없음")
            key, data = max(lists, key=lambda kv: len(kv[1]))
            note = f"인코딩 {enc}, 최상위 키 '{key}'의 배열을 읽음"
        else:
            note = f"인코딩 {enc}"
        cols = []
        for rec in data:
            if isinstance(rec, dict):
                for k in rec:
                    if k not in cols:
                        cols.append(k)
        rows = []
        for rec in data:
            rec = rec if isinstance(rec, dict) else {}
            rows.append(["" if rec.get(c) is None else (json.dumps(rec[c], ensure_ascii=False) if isinstance(rec[c], (dict, list)) else str(rec[c])) for c in cols])
        return cols, rows, note
    sample = text[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
        delim = dialect.delimiter
    except csv.Error:
        delim = "\t" if ext == ".tsv" else ","
    reader = csv.reader(io.StringIO(text), delimiter=delim)
    rows = [r for r in reader if any(cell.strip() for cell in r)]
    if not rows:
        return [], [], f"인코딩 {enc}"
    header = rows[0]
    body = rows[1:]
    ragged = sum(1 for r in body if len(r) != len(header))
    note = f"인코딩 {enc}, 구분자 {repr(delim)}"
    if ragged:
        note += f", 열 개수가 헤더와 다른 행 {ragged}개"
    return header, body, note


def kind(v):
    if INT.match(v):
        return "int"
    if FLOAT.match(v):
        return "float"
    if DATE.match(v):
        return "date"
    if TIME.match(v):
        return "time"
    if v.lower() in ("true", "false", "y", "n", "yes", "no"):
        return "bool"
    return "text"


def is_pii(col, values):
    if PII_NAME.search(col):
        return True
    sample = [v for v in values[:200] if v]
    if sample and sum(1 for v in sample if EMAIL.match(v) or PHONE.match(v)) >= len(sample) * 0.5:
        return True
    return False


def mask(v):
    return f"<{len(v)}자>"


def profile_column(col, values, top):
    n = len(values)
    present = [v.strip() for v in values if v.strip().lower() not in MISSING]
    missing = n - len(present)
    kinds = Counter(kind(v) for v in present)
    uniq = len(set(present))
    pii = is_pii(col, present)
    out = {
        "col": col, "n": n, "missing": missing, "unique": uniq,
        "kinds": dict(kinds), "pii": pii, "present": present,
    }
    nums = []
    # 절반 이상이 숫자면 숫자 열로 보고, 숫자가 아닌 값은 따로 센다
    if kinds and (kinds.get("int", 0) + kinds.get("float", 0)) >= len(present) * 0.5:
        for v in present:
            try:
                nums.append(float(v))
            except ValueError:
                pass
    if len(nums) >= 2:
        nums_sorted = sorted(nums)
        q1 = nums_sorted[len(nums) // 4]
        q3 = nums_sorted[(len(nums) * 3) // 4]
        iqr = q3 - q1
        lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        out["num"] = {
            "min": nums_sorted[0], "max": nums_sorted[-1],
            "mean": statistics.fmean(nums), "median": statistics.median(nums),
            "outliers": sum(1 for x in nums if x < lo or x > hi) if iqr > 0 else 0,
            "negatives": sum(1 for x in nums if x < 0),
            "zeros": sum(1 for x in nums if x == 0),
            "non_numeric": len(present) - len(nums),
        }
    else:
        lens = [len(v) for v in present]
        if lens:
            out["len"] = (min(lens), max(lens))
    if not pii:
        out["top"] = Counter(present).most_common(top)
    return out


def fmt_num(x):
    return f"{x:.4g}" if isinstance(x, float) and not x.is_integer() else f"{int(x)}" if isinstance(x, float) else str(x)


def report(path, top):
    cols, rows, note = load_table(path)
    print(f"\n## {path}")
    print(f"- {note}")
    print(f"- 행 {len(rows)}개 × 열 {len(cols)}개")
    if not rows:
        return cols, rows, []
    dup = len(rows) - len(set(tuple(r) for r in rows))
    if dup:
        print(f"- 완전히 같은 행 {dup}개")
    profiles = []
    for i, c in enumerate(cols):
        vals = [r[i] if i < len(r) else "" for r in rows]
        profiles.append(profile_column(c, vals, top))
    keys = [p["col"] for p in profiles if p["missing"] == 0 and p["unique"] == p["n"] and p["n"] > 0]
    print(f"- 키 후보(빈 값 없고 모두 다름): {', '.join(keys) if keys else '없음'}")
    pii_cols = [p["col"] for p in profiles if p["pii"]]
    if pii_cols:
        print(f"- 개인정보 의심 열(값 가림): {', '.join(pii_cols)}")
    print("\n| 열 | 빈 값 | 고유값 | 형식 | 범위 / 길이 | 상위 값 |")
    print("|---|---|---|---|---|---|")
    for p in profiles:
        kinds = ", ".join(f"{k} {v}" for k, v in sorted(p["kinds"].items(), key=lambda kv: -kv[1])) or "-"
        if len(p["kinds"]) > 1:
            kinds = "⚠ 섞임: " + kinds
        if "num" in p:
            s = p["num"]
            rng = f"{fmt_num(s['min'])}~{fmt_num(s['max'])} (평균 {s['mean']:.4g}, 중앙 {fmt_num(float(s['median']))})"
            extra = []
            if s["outliers"]:
                extra.append(f"IQR 밖 {s['outliers']}")
            if s["negatives"]:
                extra.append(f"음수 {s['negatives']}")
            if s["non_numeric"]:
                extra.append(f"숫자 아님 {s['non_numeric']}")
            if extra:
                rng += " ⚠ " + ", ".join(extra)
        elif "len" in p:
            rng = f"{p['len'][0]}~{p['len'][1]}자"
        else:
            rng = "-"
        if p["pii"]:
            topv = "(가림)"
        else:
            topv = ", ".join(f"{v[:20]}({c})" for v, c in p.get("top", []))
        miss = f"{p['missing']} ({p['missing'] * 100 / p['n']:.0f}%)" if p["missing"] else "0"
        print(f"| {p['col']} | {miss} | {p['unique']} | {kinds} | {rng} | {topv} |")
    return cols, rows, profiles


def cross_check(tables):
    """여러 파일에 같은 이름의 열이 있으면 값 겹침을 본다."""
    names = {}
    for path, profiles in tables:
        for p in profiles:
            names.setdefault(p["col"], []).append((path, set(p["present"]), p))
    shared = {c: v for c, v in names.items() if len(v) > 1}
    if not shared:
        return
    print("\n## 파일 간 같은 이름의 열")
    print("| 열 | 파일 A | 파일 B | A 값 중 B에 있음 | B 값 중 A에 있음 |")
    print("|---|---|---|---|---|")
    for c, items in shared.items():
        # 측정값(숫자) 열은 겹침이 의미 없으므로, 키처럼 보이는 이름이 아니면 건너뛴다
        if not KEYISH.search(c) and any("num" in p for _, _, p in items):
            continue
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                (pa, sa, _), (pb, sb, _) = items[i], items[j]
                if not sa or not sb:
                    continue
                inter = len(sa & sb)
                print(f"| {c} | {os.path.basename(pa)} | {os.path.basename(pb)} | {inter}/{len(sa)} ({inter * 100 / len(sa):.0f}%) | {inter}/{len(sb)} ({inter * 100 / len(sb):.0f}%) |")


def main():
    if hasattr(sys.stdout, "reconfigure"):  # 한글 출력이 콘솔 인코딩(cp949 등) 때문에 깨지거나 죽지 않게
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="데이터 첫 점검 (표준 라이브러리)")
    ap.add_argument("files", nargs="+")
    ap.add_argument("--top", type=int, default=5)
    a = ap.parse_args()
    tables, failed, total_rows = [], 0, 0
    print("# 데이터 첫 점검")
    print("> 숫자는 이 스크립트가 실제로 센 값. 원인과 처리 방법은 담당자 확인 또는 사용자 결정 대상.")
    for f in a.files:
        try:
            _, rows, profiles = report(f, a.top)
            total_rows += len(rows)
            tables.append((f, profiles))
        except Exception as e:  # 파일 하나가 실패해도 나머지는 계속
            failed += 1
            print(f"\n## {f}\n- ⚠ 읽기 실패: {e}")
    if len(tables) > 1:
        cross_check(tables)
    print("\n## 다음")
    print("- ⚠ 표시(형식 섞임, IQR 밖, 음수), 빈 값, 중복을 BRIEF '데이터 이슈'로 옮기고 지시서의 숫자 조건과 대조한다.")
    if total_rows == 0:
        print("\n⚠ 읽은 행이 0건 — 이 결과를 '문제 없음'으로 읽지 말 것 (exit 2)")
        sys.exit(2)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
