"""csv/*.csv → scores.js (학생별 암호화)

사용법:
    python3 build.py

csv/ 폴더에 평가 항목별로 CSV를 하나씩 둡니다. 파일 하나 = 화면의 섹션 하나.
    csv/1_assignment1.csv  → "assignment1" 섹션
    csv/2_midterm.csv      → "midterm" 섹션
- 섹션은 파일명 순서로 표시되고, 앞의 "숫자_" 접두어는 표시할 때 제거됩니다.

각 CSV 형식 (UTF-8, 첫 줄은 헤더):
    이름,학번,점수,코멘트
    홍길동,20261234,92.5,잘했습니다
- '이름', '학번' 열은 필수이고, 나머지 열은 파일마다 자유롭게 정할 수 있습니다.
- 학생의 점수는 PBKDF2(이름|학번)로 만든 키로 AES-GCM 암호화되어,
  정확한 이름과 학번을 아는 사람만 복호화할 수 있습니다.
- csv/ 폴더는 .gitignore에 등록되어 있어 커밋되지 않습니다.
- 반 전체 통계(평균·중앙값·사분위·최소·최대)는 집계값이라 암호화하지 않고 함께 저장합니다.
"""

import base64
import csv
import glob
import json
import os
import re
import statistics
import sys
import unicodedata
from hashlib import pbkdf2_hmac

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ITERATIONS = 300_000
HERE = os.path.dirname(os.path.abspath(__file__))


def normalize(name: str, sid: str) -> str:
    # index.html의 normalize()와 반드시 동일해야 함
    name = "".join(unicodedata.normalize("NFC", name).split())
    sid = "".join(sid.split())
    return f"{name}|{sid}"


def b64(b: bytes) -> str:
    return base64.b64encode(b).decode()


def column_stats(rows):
    """숫자 열(요약 '#' 열·감점 사유 제외)마다 평균·중앙값·사분위·최소·최대"""
    out = {}
    for k in rows[0].keys():
        if k in ("이름", "학번") or k.startswith("#") or k.endswith("감점 사유"):
            continue
        try:
            vals = sorted(float(r[k]) for r in rows if (r.get(k) or "").strip())
        except ValueError:
            continue
        if len(vals) < 2:
            continue
        q1, med, q3 = statistics.quantiles(vals, n=4, method="inclusive")
        out[k] = {
            "n": len(vals), "mean": round(statistics.mean(vals), 2),
            "median": round(med, 2), "q1": round(q1, 2), "q3": round(q3, 2),
            "min": vals[0], "max": vals[-1],
        }
    return out


def main():
    files = sorted(glob.glob(os.path.join(HERE, "csv", "*.csv")))
    if not files:
        sys.exit("csv/ 폴더에 CSV 파일이 없습니다.")

    students = {}  # secret -> {"이름": ..., "sections": [...]}
    stats = {}  # 섹션 -> 열 -> 반 전체 통계 (개인 식별 불가한 집계값만, 암호화하지 않음)
    for path in files:
        title = re.sub(r"^\d+_", "", os.path.splitext(os.path.basename(path))[0])
        with open(path, encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
        seen = set()
        for row in rows:
            name, sid = (row.get("이름") or "").strip(), (row.get("학번") or "").strip()
            if not name or not sid:
                continue
            secret = normalize(name, sid)
            if secret in seen:
                sys.exit(f"{os.path.basename(path)}: 중복된 학생 {name} {sid}")
            seen.add(secret)
            items = {k: (v or "").strip() for k, v in row.items() if k and k not in ("이름", "학번")}
            s = students.setdefault(secret, {"이름": name, "sections": []})
            s["sections"].append({"title": title, "items": items})
        stats[title] = column_stats(rows)
        print(f"  {os.path.basename(path)} → '{title}' ({len(seen)}명)")

    salt = os.urandom(16)
    records = {}
    for secret, data in students.items():
        dk = pbkdf2_hmac("sha256", secret.encode(), salt, ITERATIONS, dklen=48)
        iv = os.urandom(12)
        ct = AESGCM(dk[16:]).encrypt(iv, json.dumps(data, ensure_ascii=False).encode(), None)
        records[dk[:16].hex()] = {"iv": b64(iv), "ct": b64(ct)}

    out = {"salt": b64(salt), "iterations": ITERATIONS, "stats": stats, "records": records}
    # fetch 대신 <script>로 읽어서 file:// 로 열어도 동작하도록 JS로 출력
    with open(os.path.join(HERE, "scores.js"), "w", encoding="utf-8") as f:
        f.write("window.SCORES = " + json.dumps(out) + ";\n")
    print(f"{len(records)}명 → scores.js 생성 완료")


if __name__ == "__main__":
    main()
