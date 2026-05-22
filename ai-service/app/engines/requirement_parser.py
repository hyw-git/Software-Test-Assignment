import csv
import io
import re
from typing import Any, Dict, List, Tuple


CSV_HEADERS = {"id", "feature", "input", "condition", "expected"}


def _parse_csv_line(line: str) -> List[str]:
    reader = csv.reader(io.StringIO(line))
    row = next(reader, [])
    return [cell.strip() for cell in row]


def parse_csv_requirements(text: str) -> List[Dict[str, Any]]:
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    if len(lines) < 2:
        return []

    headers = [h.lower() for h in _parse_csv_line(lines[0])]
    if not headers:
        return []

    structured: List[Dict[str, Any]] = []
    for index, line in enumerate(lines[1:], start=1):
        values = _parse_csv_line(line)
        row_map = {headers[i]: values[i] if i < len(values) else "" for i in range(len(headers))}
        req_id = row_map.get("id") or f"REQ-CSV-{index:03d}"
        feature = row_map.get("feature") or "未命名特性"
        input_fields = [part.strip() for part in re.split(r"[+;,]", row_map.get("input", "")) if part.strip()]
        conditions = [row_map.get("condition", "")] if row_map.get("condition") else []
        structured.append(
            {
                "id": req_id,
                "feature": feature,
                "inputFields": input_fields or ["input"],
                "ranges": _infer_ranges(row_map.get("input", ""), row_map.get("condition", "")),
                "conditions": [c for c in conditions if c],
                "expectedAction": row_map.get("expected", ""),
                "source": "rule-csv-parser",
            }
        )
    return structured


def _infer_ranges(input_text: str, condition_text: str) -> Dict[str, Any]:
    ranges: Dict[str, Any] = {}
    combined = f"{input_text} {condition_text}".lower()

    length_match = re.search(r"(\w+)\.?\s*length\s*[=:]?\s*(\d+)", combined)
    if length_match:
        ranges[f"{length_match.group(1)}.length"] = int(length_match.group(2))

    if "landmark" in combined or "关键点" in combined:
        ranges["landmarks.length"] = {"min": 32, "nominal": 33, "max": 34}

    # 提取数值边界：存为整数，供 generate_bva_cases 三点法使用
    # 支持格式：count < 3, count>=3, count=3, count boundary = 3
    count_match = re.search(r"count\s*(?:<|>=?|=|boundary\s*=)\s*(\d+)", combined)
    duration_match = re.search(r"duration\w*\s*(?:<|>=?|=|boundary\s*=)\s*(\d+)", combined)
    if count_match or duration_match:
        ranges["count"] = int(count_match.group(1)) if count_match else 3
        ranges["durationSeconds"] = int(duration_match.group(1)) if duration_match else 30

    enum_match = re.findall(r"([A-Z_]{3,})", input_text)
    if enum_match:
        ranges["enum"] = sorted(set(enum_match))

    return ranges



def parse_numbered_requirements(text: str) -> List[Dict[str, Any]]:
    structured: List[Dict[str, Any]] = []
    patterns = [
        re.compile(r"^(REQ-[A-Z0-9-]+)\s*[:：]\s*(.+)$", re.I),
        re.compile(r"^(\d+)[.)]\s*(.+)$"),
    ]

    for line in str(text or "").splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#"):
            continue

        for pattern in patterns:
            match = pattern.match(raw)
            if not match:
                continue
            groups = match.groups()
            req_id = groups[0] if groups[0].upper().startswith("REQ") else f"REQ-TXT-{groups[0]}"
            body = groups[1] if groups[0].upper().startswith("REQ") else groups[1]
            structured.append(
                {
                    "id": req_id.upper() if req_id.upper().startswith("REQ") else req_id,
                    "feature": _extract_feature(body),
                    "inputFields": _extract_fields(body),
                    "ranges": _infer_ranges(body, body),
                    "conditions": _extract_conditions(body),
                    "expectedAction": _extract_expected(body),
                    "source": "rule-text-parser",
                }
            )
            break

    return structured


def _extract_feature(body: str) -> str:
    for keyword, label in [
        ("姿态", "姿态分析"),
        ("pose", "姿态分析"),
        ("状态机", "状态机计数"),
        ("state", "状态机计数"),
        ("过滤", "记录过滤"),
        ("filter", "记录过滤"),
        ("计划", "训练计划"),
        ("plan", "训练计划"),
        ("仪表盘", "仪表盘统计"),
        ("dashboard", "仪表盘统计"),
        ("卡路里", "仪表盘统计"),
    ]:
        if keyword.lower() in body.lower():
            return label
    return "通用功能"


def _extract_fields(body: str) -> List[str]:
    fields = re.findall(r"\b([a-z][a-zA-Z0-9]*)\b", body)
    keywords = {"exerciseType", "landmarks", "count", "durationSeconds", "difficulty", "skipRest", "weight"}
    found = [f for f in fields if f in keywords]
    return found or ["input"]


def _extract_conditions(body: str) -> List[str]:
    conditions = []
    if re.search(r"count\s*<\s*\d+", body, re.I):
        conditions.append(re.search(r"count\s*<\s*\d+", body, re.I).group(0))
    if "状态" in body or "state" in body.lower():
        conditions.append("状态迁移约束")
    if "合法" in body or "valid" in body.lower():
        conditions.append("输入合法性")
    return conditions


def _extract_expected(body: str) -> str:
    parts = re.split(r"应|应该|expected|then", body, flags=re.I)
    if len(parts) > 1:
        return parts[-1].strip(" ：:，,。")
    return body.strip()


def parse_content_blocks(content: str) -> Tuple[List[Dict[str, Any]], str]:
    """Parse merged content from manual/CSV/file channels."""
    all_reqs: List[Dict[str, Any]] = []
    seen_ids = set()

    csv_blocks = re.findall(r"\[CSV requirements\]\s*\n([\s\S]*?)(?=\n\[|\Z)", content, re.I)
    csv_blocks += re.findall(r"\[csv requirements\]\s*\n([\s\S]*?)(?=\n\[|\Z)", content, re.I)
    for block in csv_blocks:
        for item in parse_csv_requirements(block):
            if item["id"] not in seen_ids:
                seen_ids.add(item["id"])
                all_reqs.append(item)

    inline_csv = re.search(r"^id,feature,input,condition,expected", content, re.I | re.M)
    if inline_csv:
        start = inline_csv.start()
        tail = content[start:]
        section_break = re.search(r"\n\[", tail)
        csv_text = tail[:section_break.start()] if section_break else tail
        for item in parse_csv_requirements(csv_text):
            if item["id"] not in seen_ids:
                seen_ids.add(item["id"])
                all_reqs.append(item)

    for item in parse_numbered_requirements(content):
        if item["id"] not in seen_ids:
            seen_ids.add(item["id"])
            all_reqs.append(item)

    if not all_reqs and ("fitness" in content.lower() or "健身" in content or "姿态" in content):
        all_reqs = _default_fitness_requirements()

    source_channel = "csv+text" if len(seen_ids) > 1 else ("csv" if csv_blocks or inline_csv else "text")
    return all_reqs, source_channel


def _default_fitness_requirements() -> List[Dict[str, Any]]:
    return [
        {
            "id": "REQ-POSE-001",
            "feature": "姿态分析",
            "inputFields": ["exerciseType", "landmarks"],
            "ranges": {"landmarks.length": {"min": 32, "nominal": 33, "max": 34}, "enum": ["SQUAT", "PUSHUP", "PLANK", "JUMPING_JACK"]},
            "conditions": ["exerciseType in supported set", "landmarks.length == 33"],
            "expectedAction": "返回 count、score、feedback、state、angle",
            "source": "rule-default-fitness",
        },
        {
            "id": "REQ-POSE-002",
            "feature": "状态机计数",
            "inputFields": ["frameSequence", "exerciseType"],
            "ranges": {},
            "conditions": ["完整 UP-DESCENDING-DOWN-ASCENDING-UP 循环", "非法短循环"],
            "expectedAction": "仅完整循环计数+1",
            "source": "rule-default-fitness",
        },
        {
            "id": "REQ-REC-001",
            "feature": "记录过滤",
            "inputFields": ["count", "durationSeconds"],
            "ranges": {"count": "<3", "durationSeconds": "<30"},
            "conditions": ["count < 3 AND durationSeconds < 30"],
            "expectedAction": "记录不入库",
            "source": "rule-default-fitness",
        },
    ]
