#!/usr/bin/env bash
# my-cofa-plugin 설치: 작업 폴더에 스킬·규칙·기록 양식·도구를 복사만 한다.
# 과제 원본 파일(데이터·README·형식 파일·과제 AGENTS.md)은 수정하지 않는다.
# ~/.codex, Codex 설정, 네트워크, git 커밋은 건드리지 않는다.
# 사용: bash /tmp/kit/install.sh [작업 폴더, 기본 현재 폴더]
set -euo pipefail

KIT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="$(cd "${1:-.}" && pwd)"
MARK="<!-- my-cofa-plugin:begin -->"
PY="$(command -v python3 || command -v python || true)"

if [ "$KIT" = "$DEST" ]; then
  echo "키트 폴더 자체에는 설치하지 않습니다. 과제 작업 폴더에서 실행하세요." >&2
  exit 1
fi

echo "== my-cofa-plugin 설치 → $DEST"
mkdir -p "$DEST/.cofa/tools"
printf '*\n' > "$DEST/.cofa/.gitignore"

# 0) 원본 파일 지문 — 아무것도 복사하기 전에, 처음 설치할 때만 찍는다
if [ -f "$DEST/.cofa/originals.sha256" ]; then
  echo "- 원본 지문: 이미 있음 (유지)"
elif [ -n "$PY" ]; then
  "$PY" "$KIT/scripts/check.py" --snapshot "$DEST"
else
  echo "- ⚠ python 없음: 원본 지문을 찍지 못함 (원본 변경 자동 점검 불가)"
fi

# 1) 스킬 (Codex 저장소 스킬 경로)
mkdir -p "$DEST/.agents/skills"
for d in "$KIT"/.agents/skills/cofa-*; do
  name="$(basename "$d")"
  rm -rf "$DEST/.agents/skills/$name"
  cp -R "$d" "$DEST/.agents/skills/$name"
done
echo "- 스킬 $(ls -d "$KIT"/.agents/skills/cofa-* | wc -l | tr -d ' ')개 → .agents/skills/"

# 2) 서브에이전트 정의 (프로젝트 범위, cofa-data / cofa-builder 두 개뿐)
mkdir -p "$DEST/.codex/agents"
cp "$KIT"/.codex/agents/cofa-*.toml "$DEST/.codex/agents/"
echo "- 서브에이전트 정의 2개 → .codex/agents/"

# 3) 규칙 — 과제의 AGENTS.md는 고치지 않는다
cp "$KIT/AGENTS.md" "$DEST/.cofa/RULES.md"
RULES_LOADED=1
if [ ! -f "$DEST/AGENTS.md" ] && [ ! -f "$DEST/AGENTS.override.md" ]; then
  cp "$KIT/AGENTS.md" "$DEST/AGENTS.md"
  echo "- AGENTS.md: 과제에 없어서 새로 만듦"
elif [ -f "$DEST/AGENTS.md" ] && grep -qF "$MARK" "$DEST/AGENTS.md"; then
  # 이전 설치 때 키트가 만든 AGENTS.md (과제 원본 아님) → 최신 규칙으로 교체
  cp "$KIT/AGENTS.md" "$DEST/AGENTS.md"
  echo "- AGENTS.md: 키트가 만든 파일이라 최신 규칙으로 교체"
elif [ -f "$DEST/AGENTS.override.md" ] && ! grep -qF "$MARK" "$DEST/AGENTS.override.md"; then
  # 과제가 준 override가 있으면 그대로 둔다
  RULES_LOADED=0
  echo "- ⚠ 과제의 AGENTS.override.md가 있어 건드리지 않음 → 규칙 자동 적용 안 됨"
else
  # 과제 AGENTS.md가 있으면: 원본은 두고, 원본 내용 + 키트 규칙으로 AGENTS.override.md를 만든다
  # (Codex는 같은 폴더에서 AGENTS.override.md를 AGENTS.md보다 우선 읽는다)
  {
    echo "<!-- 이 파일은 my-cofa-plugin이 만들었다. 과제 원본 AGENTS.md는 수정하지 않았다. -->"
    echo "<!-- 아래 1부는 과제 원본 AGENTS.md 내용 그대로이며 2부(키트 규칙)보다 우선한다. -->"
    echo
    echo "# 1부. 과제 원본 AGENTS.md"
    echo
    cat "$DEST/AGENTS.md"
    echo
    echo
    echo "# 2부. 키트 규칙"
    echo
    cat "$KIT/AGENTS.md"
  } > "$DEST/AGENTS.override.md.tmp"
  mv "$DEST/AGENTS.override.md.tmp" "$DEST/AGENTS.override.md"
  echo "- 과제 AGENTS.md는 그대로 두고, 원본 내용 + 키트 규칙으로 AGENTS.override.md 생성"
fi

# 4) 기록 양식: 없는 파일만 만든다
mkdir -p "$DEST/cofa-notes/data"
for t in "$KIT"/templates/*.md; do
  f="$DEST/cofa-notes/$(basename "$t")"
  [ -f "$f" ] || cp "$t" "$f"
done
echo "- 기록 양식 → cofa-notes/ (기존 파일은 유지)"

# 5) 도구
cp "$KIT"/scripts/*.py "$DEST/.cofa/tools/"
echo "- 도구 → .cofa/tools/ (profile.py, check.py, 커밋 제외)"

# 6) 실행 환경 요약
echo
echo "== 실행 환경"
if [ -n "$PY" ]; then echo "- $("$PY" --version 2>&1)"; else echo "- ⚠ python 없음: 도구 대신 Codex에게 직접 요약을 요청"; fi
command -v node >/dev/null 2>&1 && echo "- node $(node --version)" || echo "- node 없음"
command -v git  >/dev/null 2>&1 && echo "- $(git --version)" || echo "- git 없음"

echo
echo "== 다음"
echo "1. Codex를 껐다 켜고 /skills 에서 cofa-* 스킬이 보이는지 확인"
if [ "$RULES_LOADED" = 0 ]; then
  echo "   규칙이 자동 적용되지 않으니 첫 요청에: '.cofa/RULES.md 를 읽고 이 세션 규칙으로 따라 줘'"
fi
echo "2. \$cofa-start 로 시작"
echo "   (스킬이 안 보이면: '.agents/skills/cofa-start/SKILL.md 읽고 그대로 따라 해')"
