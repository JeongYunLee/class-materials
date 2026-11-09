"""채점 엑셀(csv/*.xlsx) → csv/*.csv 변환

출력 CSV 열 규칙 (index.html 표시 방식):
- 이름, 학번 다음 첫 열 = 대표 점수 (큰 숫자 + boxplot)
- '#'으로 시작하는 열 = 요약 정보 (대표 점수 옆 작은 칩)
- 그 밖의 열 = 세부 점수 표의 행, 제목 끝 '(n)'은 만점
- '(n) 감점 사유' 열 = 바로 앞 항목의 감점 사유, '감점 사유' 열 = 전체 감점 사유

사용법 (openpyxl 필요: pip install openpyxl):
    python3 convert_xlsx.py     # csv/ 폴더의 채점 엑셀을 찾아 CSV로 변환
    python3 build.py            # CSV → scores.js

- csv/assignment1_최종채점*.xlsx → csv/1_assignment1.csv
- csv/midterm_최종채점*.xlsx     → csv/2_midterm.csv
"""

import csv
import fnmatch
import os
import sys
import unicodedata

import openpyxl

HERE = os.path.dirname(os.path.abspath(__file__))
CSV_DIR = os.path.join(HERE, "csv")


def fmt(v):
    if v is None:
        return ""
    if isinstance(v, float):
        v = round(v, 2)
        if v.is_integer():
            v = int(v)
    return " ".join(str(v).split())  # 줄바꿈 등 공백 정리


def read_sheet(path, sheet):
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb[sheet] if sheet else wb.worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
    header = [fmt(h) for h in rows[0]]
    body = [r for r in rows[1:] if fmt(r[0]) and fmt(r[1]) and fmt(r[0]) not in ("평균", "배점")]
    return header, body


def col(header, prefix):
    return next(i for i, h in enumerate(header) if h.startswith(prefix))


def assignment1(path):
    h, rows = read_sheet(path, None)
    c = {k: col(h, k) for k in ["이름", "학번", "원점수", "지각", "최종점수", "감점 사유(학생"]}
    out = [["이름", "학번", "최종 점수 (30)", "#원점수", "#지각", "감점 사유"]]
    for r in rows:
        reason = fmt(r[c["감점 사유(학생"]])
        out.append([
            fmt(r[c["이름"]]), fmt(r[c["학번"]]),
            fmt(r[c["최종점수"]]), fmt(r[c["원점수"]]),
            "있음 (원점수 × 0.9)" if fmt(r[c["지각"]]) else "없음",
            "" if reason in ("", "-") else reason,
        ])
    return out


def midterm(path):
    h, rows = read_sheet(path, "최종 채점")
    # 항목 열: "(n) ..." 형식이고 바로 다음 열이 '근거'
    items = [i for i, x in enumerate(h) if x.startswith("(") and h[i + 1] == "근거"]
    c = {k: col(h, k) for k in ["이름", "학번", "과제 점수", "가산점", "퀴즈", "최종 점수"]}
    header = ["이름", "학번", "최종 점수 (32)", "#과제 점수", "#상한 점수", "#가산점"]
    for i in items:
        header += [h[i], f"{h[i].split(')')[0]}) 감점 사유"]
    out = [header]
    for r in rows:
        name = fmt(r[c["이름"]])
        # '퀴즈' 열 = 상한 점수(30 / 24 / 15). 비어 있으면 미정
        task, bonus, cap = r[c["과제 점수"]], r[c["가산점"]] or 0, r[c["퀴즈"]]
        if isinstance(cap, (int, float)):
            # 최종 = min(과제 점수, 상한) + 가산점 → 엑셀 '최종 점수'와 대조
            final = min(task, cap) + bonus
            xl = r[c["최종 점수"]]
            if not isinstance(xl, (int, float)) or abs(final - xl) > 1e-9:
                sys.exit(f"{name}: 계산한 최종 점수 {final} ≠ 엑셀 최종 점수 {xl}")
            final, cap = fmt(final), fmt(cap)
        else:
            final, cap = "", ""
        row = [name, fmt(r[c["학번"]]), final, fmt(task), cap, fmt(bonus)]
        for i in items:
            row += [fmt(r[i]), fmt(r[i + 1])]
        out.append(row)
    return out


JOBS = [
    ("assignment1_최종채점*.xlsx", assignment1, "1_assignment1.csv"),
    ("midterm_최종채점*.xlsx", midterm, "2_midterm.csv"),
]


def main():
    for pattern, fn, dst in JOBS:
        # macOS 한글 파일명(NFD)도 찾도록 NFC로 맞춰 비교
        found = sorted(
            os.path.join(CSV_DIR, f) for f in os.listdir(CSV_DIR)
            if fnmatch.fnmatch(unicodedata.normalize("NFC", f), pattern)
        )
        if not found:
            print(f"  (건너뜀) csv/{pattern} 없음", file=sys.stderr)
            continue
        rows = fn(found[-1])
        with open(os.path.join(CSV_DIR, dst), "w", encoding="utf-8", newline="") as f:
            csv.writer(f).writerows(rows)
        print(f"  {os.path.basename(found[-1])} → csv/{dst} ({len(rows) - 1}명)")


if __name__ == "__main__":
    main()
