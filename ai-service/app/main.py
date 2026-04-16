import json
import os
import re
from typing import Any, Dict, List

from fastapi import FastAPI
from fastapi import HTTPException
from pydantic import BaseModel

try:
    from openai import OpenAI
except Exception:  # pragma: no cover
    OpenAI = None

app = FastAPI(title="AI Testcase Service")


class GenerateRequest(BaseModel):
    sourceType: str = "requirements"
    content: str = ""
    testTechnique: str = "black-box"
    promptMode: str = "default"
    customPrompt: str = ""
    documents: List[Dict[str, str]] = []


class TestCase(BaseModel):
    id: str
    technique: str
    designMethod: str
    title: str
    precondition: str
    input: str
    steps: str
    expected: str
    priority: str


class TestArtifacts(BaseModel):
    inputVariables: List[str]
    equivalencePartitions: List[Dict[str, str]]
    boundaryValues: List[Dict[str, Any]]
    decisionTableRules: List[Dict[str, str]]
    missingItems: List[str]
    assumptions: List[str]


class GenerateResponse(BaseModel):
    model: str
    testTechnique: str
    promptVersion: str
    promptUsed: str
    llmRawOutput: str
    artifacts: TestArtifacts
    testcases: List[TestCase]


@app.get("/health")
def health():
    return {"status": "ok", "service": "ai-service"}


ALLOWED_METHODS = [
    "EP",
    "BVA",
    "Combinatorial",
    "StateTransition",
    "DecisionTable",
]

PROMPT_VERSION = "bb-v2.2-assignment1"
ENABLE_PARSE_FALLBACK = os.getenv("ENABLE_PARSE_FALLBACK", "false").strip().lower() == "true"


def _compose_content(content: str, documents: List[Dict[str, str]]) -> str:
    chunks: List[str] = []

    if str(content).strip():
        chunks.append(f"[manual-input]\n{str(content).strip()}")

    for index, item in enumerate(documents or [], start=1):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", f"file-{index}"))
        text = str(item.get("content", "")).strip()
        doc_type = str(item.get("type", ""))
        if not text:
            continue
        header = f"[file-{index}] name={name}"
        if doc_type:
            header += f" type={doc_type}"
        chunks.append(f"{header}\n{text}")

    return "\n\n".join(chunks)


def build_prompt(source_type: str, content: str, prompt_mode: str = "default", custom_prompt: str = "") -> str:
    if prompt_mode == "custom" and str(custom_prompt).strip():
        return (
            f"{str(custom_prompt).strip()}\n\n"
            "Output requirements (MUST follow):\n"
            "- Return JSON object only.\n"
            "- black-box only. Allowed methods: EP, BVA, Combinatorial, StateTransition, DecisionTable.\n"
            "- Include testcases with fields: id, technique, designMethod, title, precondition, input, steps, expected, priority.\n"
            f"sourceType: {source_type}\n"
            f"content:\n{content[:6000]}"
        )

    return (
        "You are an expert software testing assistant for dynamic black-box testing. "
        "You must follow Assignment1 requirements and generate submission-ready artifacts.\n"
        "Testing technique is strictly black-box only. Allowed methods: "
        "EP, BVA, Combinatorial, StateTransition, DecisionTable.\n"
        "Do NOT include static testing or white-box content.\n"
        "Return JSON object only with this exact schema:\n"
        "{\n"
        '  "inputVariables": ["..."],\n'
        '  "equivalencePartitions": [{"id":"EP1","description":"...","type":"valid|invalid","expected":"..."}],\n'
        '  "boundaryValues": [{"field":"...","values":["..."],"rationale":"..."}],\n'
        '  "decisionTableRules": [{"conditions":"...","actions":"...","expected":"..."}],\n'
        '  "testcases": [{"id":"TC-BB-001","technique":"black-box","designMethod":"EP|BVA|Combinatorial|StateTransition|DecisionTable","title":"...","precondition":"...","input":"...","steps":"...","expected":"...","priority":"high|medium|low"}],\n'
        '  "missingItems": ["unclear requirement ..."],\n'
        '  "assumptions": ["assumption ..."]\n'
        "}\n"
        "Constraints:\n"
        "1) Generate 8-12 testcases.\n"
        "2) Cover all five black-box methods, at least one testcase each.\n"
        "3) Prefer concrete API-level or behavior-level checks.\n"
        "4) Include edge cases and invalid inputs.\n"
        "5) IDs must be unique and stable.\n"
        f"sourceType: {source_type}\n"
        f"content:\n{content[:6000]}"
    )


def _extract_json_object(text: str):
    # Try direct JSON first, then fallback to extracting the first JSON object block.
    try:
        payload = json.loads(text)
        if isinstance(payload, dict):
            return payload
        return None
    except Exception:
        pass

    code_block = re.search(r"```json\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    if code_block:
        try:
            payload = json.loads(code_block.group(1))
            if isinstance(payload, dict):
                return payload
        except Exception:
            pass

    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        return None

    try:
        payload = json.loads(match.group(0))
        if isinstance(payload, dict):
            return payload
        return None
    except Exception:
        return None


def _extract_response_text(response: Any) -> str:
    # Preferred path for newer OpenAI SDK response shape.
    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    # Fallback path for chat.completions style responses.
    choices = getattr(response, "choices", None)
    if isinstance(choices, list) and choices:
        message = getattr(choices[0], "message", None)
        if message is not None:
            content = getattr(message, "content", "")
            if isinstance(content, str):
                return content.strip()

    return ""


def _call_llm(client: Any, model: str, prompt: str):
    # Newer SDK (responses API)
    if hasattr(client, "responses") and hasattr(client.responses, "create"):
        return client.responses.create(
            model=model,
            input=prompt,
            temperature=0.2,
        )

    # Older SDK / provider-compatible path (chat.completions API)
    if hasattr(client, "chat") and hasattr(client.chat, "completions") and hasattr(client.chat.completions, "create"):
        return client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a black-box software testing assistant."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
        )

    raise RuntimeError("Current OpenAI SDK does not support responses or chat.completions APIs")


def _normalize_cases(payload, source_type: str) -> List[TestCase]:
    normalized: List[TestCase] = []
    if not isinstance(payload, list):
        return normalized

    for i, item in enumerate(payload, start=1):
        if not isinstance(item, dict):
            continue

        method = str(item.get("designMethod", "EP")).strip()
        if method not in ALLOWED_METHODS:
            method = "EP"

        normalized.append(
            TestCase(
                id=str(item.get("id", f"TC-BB-{i:03d}")),
                technique="black-box",
                designMethod=method,
                title=str(item.get("title", f"黑盒测试用例 {i}")),
                precondition=str(item.get("precondition", "系统已启动并接口可访问")),
                input=str(item.get("input", f"sourceType={source_type}")),
                steps=str(item.get("steps", "提交请求并观察响应")),
                expected=str(item.get("expected", "系统行为符合规格说明")),
                priority=str(item.get("priority", "medium")),
            )
        )

    return normalized


def _normalize_artifacts(payload) -> TestArtifacts:
    if not isinstance(payload, dict):
        return TestArtifacts(
            inputVariables=[],
            equivalencePartitions=[],
            boundaryValues=[],
            decisionTableRules=[],
            missingItems=[],
            assumptions=[],
        )

    def _safe_list(name: str):
        value = payload.get(name, [])
        return value if isinstance(value, list) else []

    input_vars = [str(item) for item in _safe_list("inputVariables") if str(item).strip()]

    eq_partitions = []
    for item in _safe_list("equivalencePartitions"):
        if isinstance(item, dict):
            eq_partitions.append(
                {
                    "id": str(item.get("id", "EPX")),
                    "description": str(item.get("description", "")),
                    "type": str(item.get("type", "valid")),
                    "expected": str(item.get("expected", "")),
                }
            )

    bva_items = []
    for item in _safe_list("boundaryValues"):
        if isinstance(item, dict):
            values = item.get("values", [])
            bva_items.append(
                {
                    "field": str(item.get("field", "")),
                    "values": values if isinstance(values, list) else [str(values)],
                    "rationale": str(item.get("rationale", "")),
                }
            )

    dt_rules = []
    for item in _safe_list("decisionTableRules"):
        if isinstance(item, dict):
            dt_rules.append(
                {
                    "conditions": str(item.get("conditions", "")),
                    "actions": str(item.get("actions", "")),
                    "expected": str(item.get("expected", "")),
                }
            )

    missing_items = [str(item) for item in _safe_list("missingItems") if str(item).strip()]
    assumptions = [str(item) for item in _safe_list("assumptions") if str(item).strip()]

    return TestArtifacts(
        inputVariables=input_vars,
        equivalencePartitions=eq_partitions,
        boundaryValues=bva_items,
        decisionTableRules=dt_rules,
        missingItems=missing_items,
        assumptions=assumptions,
    )


def _mock_cases(source_type: str, content: str) -> List[TestCase]:
    head = content[:120] if content else "No content provided"
    is_fitness = "fitness" in content.lower() or "姿势" in content or "运动" in content

    if is_fitness:
        return [
            TestCase(
                id="TC-BB-001",
                technique="black-box",
                designMethod="EP",
                title="EP-有效运动类型输入",
                precondition="系统已加载运动分析模块",
                input="exerciseType=SQUAT 且 landmarks 数组完整",
                steps="提交姿势分析请求",
                expected="返回 count、score、feedback 等字段且状态码 200",
                priority="high",
            ),
            TestCase(
                id="TC-BB-002",
                technique="black-box",
                designMethod="BVA",
                title="BVA-关键点数量边界",
                precondition="接口可调用",
                input="landmarks 数量=0, 1, 32, 33, 34",
                steps="分别提交请求并记录响应",
                expected="33 个关键点正常，其余输入触发可解释错误",
                priority="high",
            ),
            TestCase(
                id="TC-BB-003",
                technique="black-box",
                designMethod="Combinatorial",
                title="组合输入-运动类型 x 训练模式",
                precondition="支持自由模式与计划模式",
                input="exerciseType∈{SQUAT,PUSHUP,PLANK,JUMPING_JACK}, mode∈{free,plan}",
                steps="覆盖关键组合并调用相关接口",
                expected="每种组合均返回一致的数据结构且无 5xx",
                priority="medium",
            ),
            TestCase(
                id="TC-BB-004",
                technique="black-box",
                designMethod="StateTransition",
                title="状态迁移-俯卧撑计数状态机",
                precondition="状态机初始为 UP",
                input="连续帧触发 UP→DESCENDING→DOWN→ASCENDING→UP",
                steps="按状态序列提交帧数据",
                expected="仅在完整动作循环后计数 +1，非法跃迁不计数",
                priority="high",
            ),
            TestCase(
                id="TC-BB-005",
                technique="black-box",
                designMethod="DecisionTable",
                title="决策表-记录过滤规则",
                precondition="记录保存接口可用",
                input="次数<3 与 时长<30 秒的四种组合",
                steps="按决策表逐条提交记录",
                expected="仅满足有效规则的记录入库，其余被过滤",
                priority="high",
            ),
        ]

    return [
        TestCase(
            id="TC-BB-001",
            technique="black-box",
            designMethod="EP",
            title="等价类划分-有效输入",
            precondition="系统在线且接口可访问",
            input=f"sourceType={source_type}; data={head}",
            steps="提交有效输入并调用生成接口",
            expected="系统成功处理并返回正确结果",
            priority="high",
        ),
        TestCase(
            id="TC-BB-002",
            technique="black-box",
            designMethod="BVA",
            title="边界值分析-空输入",
            precondition="请求体格式合法",
            input="空字符串或缺失字段",
            steps="提交 content 为空的请求",
            expected="系统返回参数错误提示",
            priority="high",
        ),
        TestCase(
            id="TC-BB-003",
            technique="black-box",
            designMethod="DecisionTable",
            title="决策表-来源类型与内容联合约束",
            precondition="sourceType 支持 requirements 和 codebase",
            input="sourceType=codebase, content=短模块描述",
            steps="提交 codebase 场景请求并检查返回字段完整性",
            expected="返回至少 1 条包含输入/预期结果的测试用例",
            priority="medium",
        ),
    ]


def _mock_artifacts(content: str) -> TestArtifacts:
    is_fitness = "fitness" in content.lower() or "姿势" in content or "运动" in content
    if is_fitness:
        return TestArtifacts(
            inputVariables=[
                "exerciseType",
                "trainingMode",
                "landmarksCount",
                "repCount",
                "durationSeconds",
            ],
            equivalencePartitions=[
                {
                    "id": "EP1",
                    "description": "exerciseType 属于支持集合",
                    "type": "valid",
                    "expected": "请求处理成功",
                },
                {
                    "id": "EP2",
                    "description": "exerciseType 非法值或空值",
                    "type": "invalid",
                    "expected": "返回参数错误",
                },
            ],
            boundaryValues=[
                {
                    "field": "landmarksCount",
                    "values": [0, 1, 32, 33, 34],
                    "rationale": "33 为关键点理论边界",
                },
                {
                    "field": "durationSeconds",
                    "values": [29, 30, 31],
                    "rationale": "过滤规则边界",
                },
            ],
            decisionTableRules=[
                {
                    "conditions": "count<3 且 duration<30",
                    "actions": "过滤该记录",
                    "expected": "不写入数据库",
                },
                {
                    "conditions": "count>=3 或 duration>=30",
                    "actions": "接收该记录",
                    "expected": "记录可入库",
                },
            ],
            missingItems=["未明确输入字段单位与取值范围"],
            assumptions=["landmarks 由上游姿势识别模块保证格式"],
        )

    return TestArtifacts(
        inputVariables=["sourceType", "contentLength"],
        equivalencePartitions=[
            {
                "id": "EP1",
                "description": "sourceType=requirements 且 content 非空",
                "type": "valid",
                "expected": "返回黑盒测试用例",
            },
            {
                "id": "EP2",
                "description": "content 为空",
                "type": "invalid",
                "expected": "返回参数错误",
            },
        ],
        boundaryValues=[
            {
                "field": "contentLength",
                "values": [0, 1, 500, 4000],
                "rationale": "覆盖空输入和截断边界",
            }
        ],
        decisionTableRules=[
            {
                "conditions": "sourceType 合法且 content 非空",
                "actions": "调用 LLM 生成",
                "expected": "返回结构化用例",
            }
        ],
        missingItems=[],
        assumptions=["输入文本可映射为可观察行为"],
    )


def _cases_to_markdown(cases: List[TestCase]) -> str:
    lines = [
        "# 黑盒测试用例 Markdown 预览",
        "",
        "| ID | 设计方法 | 标题 | 优先级 | 预期结果 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in cases:
        title = str(item.title).replace("|", "\\|")
        expected = str(item.expected).replace("|", "\\|")
        lines.append(f"| {item.id} | {item.designMethod} | {title} | {item.priority} | {expected} |")

    lines.extend(["", "## 详细步骤", ""])
    for item in cases:
        lines.append(f"### {item.id} {item.title}")
        lines.append(f"- 前置条件: {item.precondition}")
        lines.append(f"- 输入: {item.input}")
        lines.append(f"- 步骤: {item.steps}")
        lines.append(f"- 预期: {item.expected}")
        lines.append("")
    return "\n".join(lines)


@app.get("/prompt-template")
def prompt_template():
    return {
        "promptVersion": PROMPT_VERSION,
        "allowedMethods": ALLOWED_METHODS,
        "templatePreview": build_prompt("requirements", "<requirement_text_or_codebase_desc>"),
    }


@app.post("/generate-testcases", response_model=GenerateResponse)
def generate_testcases(req: GenerateRequest):
    merged_content = _compose_content(req.content, req.documents)

    if req.testTechnique != "black-box":
        return GenerateResponse(
            model="validator",
            testTechnique="black-box",
            promptVersion=PROMPT_VERSION,
            promptUsed="validator-bypass",
            llmRawOutput="",
            artifacts=_mock_artifacts(merged_content),
            testcases=[],
        )

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    model = os.getenv("OPENAI_MODEL", "deepseek-chat").strip()

    if not api_key or OpenAI is None:
        mock_cases = _mock_cases(req.sourceType, merged_content)
        return GenerateResponse(
            model="mock",
            testTechnique="black-box",
            promptVersion=PROMPT_VERSION,
            promptUsed="mock-fallback",
            llmRawOutput=_cases_to_markdown(mock_cases),
            artifacts=_mock_artifacts(merged_content),
            testcases=mock_cases,
        )

    base_url = os.getenv("OPENAI_BASE_URL", "").strip()
    if base_url:
        client = OpenAI(api_key=api_key, base_url=base_url)
    else:
        client = OpenAI(api_key=api_key)

    prompt = build_prompt(
        req.sourceType,
        merged_content,
        prompt_mode=str(req.promptMode or "default"),
        custom_prompt=str(req.customPrompt or ""),
    )

    try:
        response = _call_llm(client, model, prompt)
        text = _extract_response_text(response)
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"LLM request failed: {error}")

    if not text:
        raise HTTPException(status_code=502, detail="LLM returned empty content")

    payload = _extract_json_object(text)
    cases = _normalize_cases((payload or {}).get("testcases", []), req.sourceType)
    artifacts = _normalize_artifacts(payload)
    if not cases:
        if ENABLE_PARSE_FALLBACK:
            cases = _mock_cases(req.sourceType, merged_content)
        # When fallback is disabled, keep markdown output and return empty cases.
        # This avoids request failure caused by strict JSON parsing.
    if not artifacts.inputVariables:
        artifacts = _mock_artifacts(merged_content) if ENABLE_PARSE_FALLBACK else TestArtifacts(
            inputVariables=[],
            equivalencePartitions=[],
            boundaryValues=[],
            decisionTableRules=[],
            missingItems=[],
            assumptions=[],
        )

    rendered_raw = _cases_to_markdown(cases) if ENABLE_PARSE_FALLBACK and not _extract_json_object(text) else text

    return GenerateResponse(
        model=model,
        testTechnique="black-box",
        promptVersion=PROMPT_VERSION,
        promptUsed=prompt,
        llmRawOutput=rendered_raw,
        artifacts=artifacts,
        testcases=cases,
    )
