import unittest
from io import BytesIO

from openpyxl import load_workbook

from app.export_xlsx import build_xlsx_bytes
from app.engines.blackbox_engine import generate_blackbox_artifacts, _pairwise_combinations
from app.engines.pipeline import run_deterministic_pipeline
from app.engines.risk_engine import compute_risk_score, score_requirements
from app.engines.schema_validator import validate_llm_payload
from app.engines.whitebox_engine import parse_custom_state_model


class EngineTests(unittest.TestCase):
    def test_risk_score_formula(self):
        self.assertEqual(compute_risk_score(5, 4), 20)

    def test_csv_pipeline(self):
        content = """[CSV requirements]
id,feature,input,condition,expected
REQ-REC-001,记录过滤,count+duration,count<3 and duration<30,filtered
"""
        result = run_deterministic_pipeline(content, whitebox_description="UP -> DOWN -> UP")
        self.assertGreaterEqual(len(result["requirementsStructured"]), 1)
        self.assertGreaterEqual(len(result["testcases"]), 5)
        methods = {c["designMethod"] for c in result["testcases"]}
        self.assertTrue({"EP", "BVA", "DecisionTable"}.issubset(methods))

    def test_whitebox_custom_model(self):
        model = parse_custom_state_model('{"states":["A","B"],"transitions":[{"from":"A","to":"B"}]}')
        self.assertEqual(model["states"], ["A", "B"])

    def test_schema_validator(self):
        payload = {
            "requirementsStructured": [{"id": "R1"}],
            "riskItems": [{"reqId": "R1", "impact": 2, "likelihood": 2, "riskScore": 4}],
            "testcases": [
                {"id": "1", "designMethod": "EP"},
                {"id": "2", "designMethod": "BVA"},
                {"id": "3", "designMethod": "DecisionTable"},
            ],
        }
        ok, issues = validate_llm_payload(payload)
        self.assertTrue(ok)
        self.assertEqual(issues, [])

    def test_pairwise(self):
        rows = _pairwise_combinations([["A", "B"], ["X", "Y"]], ["f1", "f2"], max_rows=4)
        self.assertGreaterEqual(len(rows), 2)

    def test_export_xlsx_field_aliases(self):
        artifacts = {
            "requirementsStructured": [
                {
                    "id": "REQ-1",
                    "description": "姿态分析",
                    "inputs": ["exerciseType"],
                    "condition": "valid",
                    "expected": "返回 ok",
                }
            ],
            "riskItems": [
                {"id": "REQ-1", "impact": 5, "likelihood": 4, "risk_score": 20, "priority": "high"}
            ],
            "testStrategies": [
                {
                    "strategyId": "S1",
                    "technique": "EP",
                    "title": "EP strategy",
                    "standard": "ISO 29119-4",
                    "testcases": ["TC-1"],
                }
            ],
        }
        cases = [
            {
                "testCaseId": "TC-1",
                "method": "EP",
                "name": "valid partition",
                "severity": "high",
                "expected_result": "ok",
                "steps": ["step1", "step2"],
            }
        ]
        workbook = load_workbook(BytesIO(build_xlsx_bytes(artifacts, cases)), read_only=True)
        req = workbook["Requirements"]
        risk = workbook["Risks"]
        case = workbook["TestCases"]
        self.assertEqual(req.cell(2, 1).value, "REQ-1")
        self.assertEqual(req.cell(2, 2).value, "姿态分析")
        self.assertEqual(req.cell(2, 3).value, "exerciseType")
        self.assertEqual(risk.cell(2, 1).value, "REQ-1")
        self.assertEqual(risk.cell(2, 4).value, 20)
        self.assertEqual(case.cell(2, 1).value, "TC-1")
        self.assertEqual(case.cell(2, 2).value, "EP")
        self.assertEqual(case.cell(2, 6).value, "ok")


if __name__ == "__main__":
    unittest.main()
