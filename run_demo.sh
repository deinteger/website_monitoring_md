#!/bin/sh
# 데모 실행 (Linux/macOS): Python 3.8 이상을 찾아 scripts/demo.py 를 실행한다. 인자는 demo.py 로 전달된다 (예: --serve).
cd "$(dirname "$0")" || exit 1
for py in python3 python; do
  if command -v "$py" >/dev/null 2>&1 && "$py" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' 2>/dev/null; then
    exec "$py" scripts/demo.py "$@"
  fi
done
echo "[안내] Python 3.8 이상이 필요합니다. 설치 후 다시 실행하세요 (외부 패키지는 필요 없습니다)."
echo "       Python 설치가 어려운 환경이면 docs/대회제출/10_구동안내서_초안.md 의 'Python이 없는 경우'를 참고하세요."
exit 1
