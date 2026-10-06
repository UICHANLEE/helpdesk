from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from incident import parse_incident, qwen_diagnosis, qwen_model_for, quick_response, rule_judgment


class QwenRoutingTest(unittest.TestCase):
    def test_medium_uses_fast_model_without_thinking_and_keeps_json_result(self) -> None:
        parsed = parse_incident("DB 저장 API가 HTTP 500입니다")
        judgment = rule_judgment(parsed)
        context = quick_response(parsed, judgment)
        context["related_incidents"] = [{"id": "INC-1", "verification": "unverified", "summary": "미해결 질문"}]
        with patch.dict("os.environ", {"QWEN_BASE_URL": "http://127.0.0.1:11434/v1"}), \
             patch("incident.qwen_model_available", return_value=True), \
             patch("incident.post_json", return_value={"message": {"content": json.dumps({
                 "diagnosis": "저장 API 확인 필요", "immediate_actions": ["API 로그 확인"],
                 "recommended_action": "API 로그 확인"}, ensure_ascii=False)}}) as post:
            answer = qwen_diagnosis(parsed, judgment, context)
        self.assertEqual(qwen_model_for(judgment), "qwen3:4b-instruct-2507-q4_K_M")
        self.assertEqual(post.call_args.args[1]["model"], "qwen3:4b-instruct-2507-q4_K_M")
        self.assertIs(post.call_args.args[1]["think"], False)
        self.assertEqual(post.call_args.args[1]["options"]["num_predict"], 320)
        self.assertEqual(answer["diagnosis"], "저장 API 확인 필요")
        self.assertIn("미해결 질문", post.call_args.args[1]["messages"][1]["content"])

    def test_deep_uses_14b_model(self) -> None:
        self.assertEqual(qwen_model_for({"depth": "DEEP"}), "qwen3:14b-q4_K_M")


if __name__ == "__main__":
    unittest.main()
