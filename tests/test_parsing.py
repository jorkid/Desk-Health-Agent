"""解析兜底测试：正常、垃圾、坏字段、夹杂文字、下一轮工作时长边界。"""
import unittest

from deskpal.agent.parsing import parse_json_safely, parse_reminder_decision


class TestParsing(unittest.TestCase):
    def test_valid_json(self):
        r = parse_reminder_decision(
            '{"condition":"久坐","suggestion":"起来走走","next_work_minutes":20}',
            1800,
        )
        self.assertEqual(r["condition"], "久坐")
        self.assertEqual(r["suggestion"], "起来走走")
        self.assertEqual(r["next_work_seconds"], 1200)  # 20 分钟

    def test_garbage_falls_back(self):
        r = parse_reminder_decision("随便聊聊天气", 1800)
        self.assertEqual(r["condition"], "疲劳")
        self.assertEqual(r["next_work_seconds"], 1800)  # 默认工作时长

    def test_bad_condition_and_durations(self):
        r = parse_reminder_decision(
            '{"condition":"睡觉","next_work_minutes":"abc"}', 1800,
        )
        self.assertEqual(r["condition"], "疲劳")
        self.assertEqual(r["next_work_seconds"], 1800)

    def test_json_embedded_in_text(self):
        r = parse_reminder_decision(
            '好的结果如下：{"condition":"正常","next_work_minutes":15}', 1800,
        )
        self.assertEqual(r["condition"], "正常")
        self.assertEqual(r["next_work_seconds"], 900)  # 15 分钟

    def test_next_work_minutes_negative_clamped(self):
        r = parse_reminder_decision('{"next_work_minutes":-5}', 1800)
        self.assertEqual(r["next_work_seconds"], 60)  # clamp 到最少 1 分钟

    def test_parse_json_safely_never_raises(self):
        self.assertEqual(parse_json_safely(None), {})
        self.assertEqual(parse_json_safely("not json"), {})
        self.assertEqual(parse_json_safely('{"a": 1}'), {"a": 1})


if __name__ == "__main__":
    unittest.main()
