import json
import os
import re
from typing import List

from fastapi import FastAPI
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


class GenerateResponse(BaseModel):
    model: str
    testTechnique: str
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


def _extract_json_array(text: str):
    # Try direct JSON first, then fallback to extracting the first JSON array block.
    try:
        return json.loads(text)
    except Exception:
        pass

    match = re.search(r"\[[\s\S]*\]", text)
    if not match:
        return None

    try:
        return json.loads(match.group(0))
    except Exception:
        return None


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


@app.post("/generate-testcases", response_model=GenerateResponse)
def generate_testcases(req: GenerateRequest):
    if req.testTechnique != "black-box":
        return GenerateResponse(model="validator", testTechnique="black-box", testcases=[])

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    if not api_key or OpenAI is None:
        return GenerateResponse(
            model="mock",
            testTechnique="black-box",
            testcases=_mock_cases(req.sourceType, req.content),
        )

    client = OpenAI(api_key=api_key)
    prompt = (
        "你是一名资深黑盒测试工程师。请根据输入内容生成 8-12 条高质量黑盒测试用例。"
        "允许的方法仅包括: EP, BVA, Combinatorial, StateTransition, DecisionTable。"
        "必须覆盖上述五种方法，每种至少 1 条。"
        "不得输出静态测试或白盒测试内容，不要输出解释文字。"
        "只输出 JSON 数组。每项字段: id, technique, designMethod, title, precondition, input, steps, expected, priority。"
        "priority 仅允许 high/medium/low，technique 固定为 black-box。"
        f"\nsourceType: {req.sourceType}\ncontent:\n{req.content[:4000]}"
    )

    response = client.responses.create(
        model=model,
        input=prompt,
        temperature=0.2,
    )

    text = response.output_text.strip()
    payload = _extract_json_array(text)
    cases = _normalize_cases(payload, req.sourceType)
    if not cases:
        cases = _mock_cases(req.sourceType, req.content)

    return GenerateResponse(model=model, testTechnique="black-box", testcases=cases)
