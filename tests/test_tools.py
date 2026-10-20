"""工具系统测试：副作用落地、参数校验、安全边界（工作时长单位：分钟）。"""
import unittest

from deskpal.core import AppState
from deskpal.agent import make_tools


def call(tool, *args):
    """兼容不同版本 LangChain 工具调用方式的辅助函数。"""
    if hasattr(tool, "func"):
        return tool.func(*args)
    return tool.invoke(*args)


class TestTools(unittest.TestCase):
    def setUp(self):
        self.app_state = AppState(
            work_duration_seconds=1800, work_duration_min=600, work_duration_max=7200,
        )
        self.app_state.repos = {"daily": type("D", (), {"get_weekly": lambda self: []})()}
        _, self.update_tool, _ = make_tools(self.app_state)

    def test_update_work_duration_side_effect(self):
        call(self.update_tool, 15)  # 15 分钟 = 900 秒
        self.assertEqual(self.app_state.work_duration, 900)

    def test_invalid_input_returns_error(self):
        result = call(self.update_tool, "abc")
        self.assertIn("error", result)
        self.assertEqual(self.app_state.work_duration, 1800)  # 状态未被污染

    def test_negative_input_returns_error(self):
        result = call(self.update_tool, -5)
        self.assertIn("error", result)

    def test_clamp_to_max(self):
        call(self.update_tool, 99999)  # 远超上界，被 clamp 到 7200 秒
        self.assertEqual(self.app_state.work_duration, 7200)

    def test_clamp_to_min(self):
        call(self.update_tool, 1)  # 1 分钟 = 60 秒，被 clamp 到 600 秒
        self.assertEqual(self.app_state.work_duration, 600)


if __name__ == "__main__":
    unittest.main()
