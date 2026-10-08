import unittest
from unittest.mock import patch

from incident import parse_incident, qwen_diagnosis, rule_judgment, quick_response


class QwenPracticeTest(unittest.TestCase):
    def test_local_practice_disables_thinking_and_accepts_single_action(self) -> None:
        parsed = parse_incident("Save API 500, DB write failed")
        judgment = rule_judgment(parsed)
        context = quick_response(parsed, judgment)
        context.update(practice=True, tool_results=[], related_incidents=[])
        with patch("incident.post_json", return_value={"message": {"content":
             '{"diagnosis":"DB 쓰기 경로 오류 가능성","immediate_actions":"Save API 로그 확인"}'}}) as post:
            answer = qwen_diagnosis(parsed, judgment, context)
        self.assertEqual(answer["diagnosis"], "DB 쓰기 경로 오류 가능성")
        self.assertEqual(answer["immediate_actions"], ["Save API 로그 확인"])
        self.assertEqual(answer["recommended_action"], "Save API 로그 확인")
        self.assertFalse(post.call_args.args[1]["think"])

    def test_docker_host_uses_the_same_fast_local_ollama_path(self) -> None:
        parsed = parse_incident("Save API 500, DB write failed")
        judgment = rule_judgment(parsed)
        context = quick_response(parsed, judgment)
        context.update(practice=True, tool_results=[], related_incidents=[])
        with patch("incident.qwen_base_url", return_value="http://host.docker.internal:11434/v1"), \
             patch("incident.post_json", return_value={"message": {"content":
                 '{"diagnosis":"DB 쓰기 경로 확인 필요","immediate_actions":["Save API 로그 확인"]}'}}) as post:
            self.assertIsNotNone(qwen_diagnosis(parsed, judgment, context))
        self.assertEqual(post.call_args.args[0], "http://host.docker.internal:11434/api/chat")
        self.assertFalse(post.call_args.args[1]["think"])


if __name__ == "__main__":
    unittest.main()
