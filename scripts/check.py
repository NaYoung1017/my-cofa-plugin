#!/usr/bin/env python3
"""제출 전 점검 — 표준 라이브러리만 사용.

사용: python3 .cofa/tools/check.py [작업 폴더, 기본 .]
      python3 check.py --snapshot <작업 폴더>   (설치 때 원본 파일 지문을 찍는다)
검사: 원본 파일 변경, 문제 정의, 확인 필요 항목, 계획 승인, 요구 상태, 검증 기록, 제출물, 결정 기록, 비밀키, 커밋된 민감 파일.
문제 항목은 개수와 상관없이 전부 출력한다.
exit 0 정상(경고는 있을 수 있음) / 1 실패 항목 있음 / 2 실제로 검사한 항목이 0개 — 통과로 읽지 말 것
"""
import hashlib
import os
import re
import subprocess
import sys

SKIP_DIRS = {".git", "node_modules", ".cofa", ".venv", "venv", "__pycache__", "dist", "build", ".next", ".agents", ".codex", "cofa-notes"}
# 바뀌면 실패로 보는 원본: 데이터·문서·형식 파일. 그 밖(제공 코드 등)은 경고.
DOC_DATA_EXT = {".csv", ".tsv", ".json", ".jsonl", ".xlsx", ".xls", ".xml", ".txt", ".md", ".pdf", ".docx", ".parquet", ".yaml", ".yml", ".sql", ".db", ".sqlite"}
SNAPSHOT = os.path.join(".cofa", "originals.sha256")
ALLOW = os.path.join(".cofa", "allow-edit.txt")
SECRET_PATTERNS = [
    ("OpenAI 형식 키", re.compile(r"sk-[A-Za-z0-9_-]{20,}")),
    ("AWS 액세스 키", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("GitHub 토큰", re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}")),
    ("개인 키", re.compile(r"-----BEGIN (RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")),
    ("하드코딩된 비밀값", re.compile(r"(?i)(api[_-]?key|secret|password|passwd|token)\s*[:=]\s*['\"][^'\"\s]{8,}['\"]")),
]
results = []  # (상태, 항목, 설명)


def add(status, item, detail=""):
    results.append((status, item, detail))


def read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except (OSError, UnicodeDecodeError):
        return None


def walk_files(root):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            yield os.path.join(dirpath, fn)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def snapshot(root):
    os.makedirs(os.path.join(root, ".cofa"), exist_ok=True)
    lines = []
    for p in walk_files(root):
        rel = os.path.relpath(p, root).replace(os.sep, "/")
        try:
            lines.append(f"{sha256(p)}  {rel}")
        except OSError:
            continue
    with open(os.path.join(root, SNAPSHOT), "w", encoding="utf-8") as f:
        f.write("\n".join(sorted(lines, key=lambda l: l[66:])) + ("\n" if lines else ""))
    print(f"- 원본 지문: 파일 {len(lines)}개 기록 → {SNAPSHOT}")


def check_originals(root):
    snap = read(os.path.join(root, SNAPSHOT))
    if snap is None:
        add("SKIP", "원본 파일", "지문 없음 — 설치 때 찍지 못함, 원본 변경을 점검하지 못함")
        return
    allowed = set()
    allow_text = read(os.path.join(root, ALLOW))
    if allow_text:
        allowed = {l.strip().replace(os.sep, "/") for l in allow_text.splitlines() if l.strip()}
    entries = [l.split("  ", 1) for l in snap.splitlines() if "  " in l]
    if not entries:
        add("SKIP", "원본 파일", "지문에 기록된 파일 0개")
        return
    bad, warn, ok_allowed = [], [], []
    for digest, rel in entries:
        p = os.path.join(root, rel)
        if not os.path.exists(p):
            state = "삭제·이동됨"
        else:
            try:
                state = None if sha256(p) == digest else "내용 바뀜"
            except OSError:
                state = "읽기 실패"
        if state is None:
            continue
        if rel in allowed:
            ok_allowed.append(f"{rel} ({state}, 허락됨)")
        elif os.path.splitext(rel)[1].lower() in DOC_DATA_EXT or "readme" in rel.lower():
            bad.append(f"{rel} ({state})")
        else:
            warn.append(f"{rel} ({state})")
    if bad:
        add("FAIL", "원본 파일", f"데이터·문서·형식 원본 {len(bad)}개 변경: " + "; ".join(bad))
    if warn:
        add("WARN", "원본 파일", f"제공 코드 등 {len(warn)}개 변경 — 사용자가 허락했는지 확인: " + "; ".join(warn))
    if ok_allowed:
        add("WARN", "원본 파일", "허락된 변경: " + "; ".join(ok_allowed))
    if not (bad or warn or ok_allowed):
        add("PASS", "원본 파일", f"{len(entries)}개 그대로")


def strip_comments(text):
    return re.sub(r"<!--.*?-->", "", text, flags=re.S)


def table_rows(text, prefix):
    rows = []
    for line in strip_comments(text).splitlines():
        line = line.strip()
        if line.startswith("|") and re.match(rf"\|\s*{prefix}-\d+", line):
            rows.append([c.strip() for c in line.strip("|").split("|")])
    return rows


def unresolved(rows, label):
    """영향도·처리 열이 맨 끝 두 칸인 표(U-n, I-n)에서 처리 안 된 것을 찾는다."""
    high, mid = [], []
    rows = [r for r in rows if len(r) >= 3 and any(c for c in r[1:-2])]  # 비어 있는 양식 행 제외
    if not rows:
        add("WARN", label, "기록된 항목 0개 — 정말 없는지 확인")
        return
    for r in rows:
        level, handling = r[-2], r[-1]
        # "질문"만 적고 Q-n이 없으면 아직 보내지 않은 것 → 미처리
        asked_not_sent = handling.startswith("질문") and not re.search(r"Q-\d+", handling)
        if handling in ("", "확인 필요", "미정", "-") or asked_not_sent:
            (high if "높" in level or not level else mid).append(f"{r[0]} {r[1][:40]}")
    if high:
        add("FAIL", label, f"영향도 높음 미처리 {len(high)}개: " + "; ".join(high))
    if mid:
        add("WARN", label, f"미처리 {len(mid)}개: " + "; ".join(mid))
    if not (high or mid):
        add("PASS", label, f"{len(rows)}개 모두 처리됨")


def check_notes(root):
    notes = os.path.join(root, "cofa-notes")
    if not os.path.isdir(notes):
        add("SKIP", "cofa-notes", "폴더 없음 — 기록 점검을 하지 못함")
        return
    brief = read(os.path.join(notes, "BRIEF.md"))
    if brief is None:
        add("FAIL", "문제 정의", "BRIEF.md 없음")
    else:
        m = re.search(r"## 문제 정의[^\n]*\n(?:[ \t]*\n)*>[ \t]*(.+)", brief)
        if m and "___" not in m.group(1):
            add("PASS", "문제 정의", m.group(1).strip()[:80])
        else:
            add("FAIL", "문제 정의", "사용자가 쓴 문장이 비어 있음")
        unresolved(table_rows(brief, "U"), "모르는 것")
        unresolved(table_rows(brief, "I"), "데이터 이슈")
        reqs = table_rows(brief, "R")
        if not reqs:
            add("FAIL", "요구사항", "R-n 행 0개")
        else:
            open_reqs = [r[0] for r in reqs if len(r) >= 4 and r[3].lower() not in ("done", "verified", "dropped")]
            if open_reqs:
                add("WARN", "요구사항", f"{len(reqs)}개 중 미완료 {len(open_reqs)}개: {', '.join(open_reqs)}")
            else:
                add("PASS", "요구사항", f"{len(reqs)}개 모두 done/verified/dropped")
    plan = read(os.path.join(notes, "PLAN.md"))
    if plan is None:
        add("WARN", "계획", "PLAN.md 없음")
    elif re.search(r"상태:\s*APPROVED", plan):
        add("PASS", "계획", "APPROVED")
    else:
        add("WARN", "계획", "사용자 승인(APPROVED) 표시 없음")
    verify = read(os.path.join(notes, "VERIFY.md"))
    if verify is None:
        add("FAIL", "검증", "VERIFY.md 없음")
    else:
        rows = table_rows(verify, "V")
        verdicts = [(r[0], r[6].upper() if len(r) > 6 else "") for r in rows]
        passed = [v for v, d in verdicts if "PASS" in d]
        failed = [v for v, d in verdicts if "FAIL" in d]
        not_run = [v for v, d in verdicts if "NOT_RUN" in d or not d]
        detail = f"PASS {len(passed)}, FAIL {len(failed)} {failed if failed else ''}, NOT_RUN {len(not_run)} {not_run if not_run else ''}".strip()
        if not rows:
            add("FAIL", "검증", "V-n 행 0개 — 검증하지 않은 것은 통과가 아님")
        elif not passed or failed:
            add("FAIL", "검증", detail)
        elif not_run:
            add("WARN", "검증", detail)
        else:
            add("PASS", "검증", f"PASS {len(passed)}")
        subs = [r for r in table_rows(verify, "S") if len(r) >= 4 and (r[1] or r[2])]
        if not subs:
            add("WARN", "제출물", "확인한 제출물 0개 — BRIEF '제출 요구'와 대조했는지 확인")
        else:
            not_ok = [f"{r[0]} {r[1][:30]} ({r[3] or '빈칸'})" for r in subs if r[3].strip().upper() != "OK"]
            if not_ok:
                add("FAIL", "제출물", f"{len(subs)}개 중 OK 아님 {len(not_ok)}개: " + "; ".join(not_ok))
            else:
                add("PASS", "제출물", f"{len(subs)}개 모두 OK")
    dec = read(os.path.join(notes, "DECISIONS.md"))
    if dec is None:
        add("WARN", "결정 기록", "DECISIONS.md 없음")
    else:
        body = strip_comments(dec)
        heads = re.findall(r"^## (D-?\d+[^\n]*)", body, flags=re.M)
        if not heads:
            add("WARN", "결정 기록", "결정 0개")
        else:
            todo, unsure = [], []
            for block in re.split(r"^(?=## D-?\d+)", body, flags=re.M):
                h = re.match(r"## (D-?\d+)", block)
                if not h:
                    continue
                if re.search(r"코드:\s*(예정)?\s*$", block, flags=re.M):
                    todo.append(h.group(1))
                if "미확정" in block:
                    unsure.append(h.group(1))
            msg = f"{len(heads)}개"
            if todo:
                msg += f", 코드 위치 미기재 {todo}"
            if unsure:
                msg += f", 미확정 {unsure}"
            add("WARN" if (todo or unsure) else "PASS", "결정 기록", msg)


def check_secrets(root):
    scanned, hits = 0, []
    for p in walk_files(root):
        try:
            if os.path.getsize(p) > 1_000_000:
                continue
            with open(p, "rb") as f:
                raw = f.read()
        except OSError:
            continue
        if b"\x00" in raw[:4096]:
            continue
        scanned += 1
        text = raw.decode("utf-8", errors="ignore")
        for no, line in enumerate(text.splitlines(), 1):
            for label, pat in SECRET_PATTERNS:
                if pat.search(line):
                    hits.append(f"{os.path.relpath(p, root)}:{no} ({label})")
    if scanned == 0:
        add("SKIP", "비밀키 스캔", "검사한 파일 0개 — 안전하다는 뜻이 아님")
    elif hits:
        add("FAIL", "비밀키 스캔", f"{scanned}개 파일 중 의심 {len(hits)}건: " + "; ".join(hits))
    else:
        add("PASS", "비밀키 스캔", f"{scanned}개 파일, 의심 0건")


def check_git(root):
    try:
        out = subprocess.run(["git", "-C", root, "ls-files"], capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        add("SKIP", "커밋된 민감 파일", "git 실행 불가")
        return
    if out.returncode != 0:
        add("SKIP", "커밋된 민감 파일", "git 저장소 아님")
        return
    risky = [f for f in out.stdout.splitlines()
             if re.search(r"(^|/)\.env($|\.)|\.(sqlite3?|db|pem|key)$", f) and not f.endswith(".env.example")]
    if risky:
        add("WARN", "커밋된 민감 파일", ", ".join(risky))
    else:
        add("PASS", "커밋된 민감 파일", "없음")


def main():
    if hasattr(sys.stdout, "reconfigure"):  # 한글 출력이 콘솔 인코딩(cp949 등) 때문에 깨지거나 죽지 않게
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = sys.argv[1:]
    if args and args[0] == "--snapshot":
        snapshot(args[1] if len(args) > 1 else ".")
        return
    root = args[0] if args else "."
    check_originals(root)
    check_notes(root)
    check_secrets(root)
    check_git(root)
    print("# 제출 전 점검")
    order = {"FAIL": 0, "WARN": 1, "SKIP": 2, "PASS": 3}
    for status, item, detail in sorted(results, key=lambda r: order[r[0]]):
        print(f"[{status:4}] {item}: {detail}")
    counted = [s for s, _, _ in results if s in ("PASS", "WARN", "FAIL")]
    fails = sum(1 for s in counted if s == "FAIL")
    print(f"\n합계: 검사 {len(counted)}개 (FAIL {fails}, WARN {sum(1 for s in counted if s == 'WARN')}), SKIP {len(results) - len(counted)}개")
    if not counted:
        print("검사한 항목이 0개 — 이 결과를 통과로 읽지 말 것 (exit 2)")
        sys.exit(2)
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
