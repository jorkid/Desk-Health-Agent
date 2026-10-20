"""记忆系统测试：短期记忆窗口治理（滑动窗口 + 滚动概况压缩）。"""
import unittest

from langchain_core.messages import HumanMessage, AIMessage

from deskpal.agent.memory import compress_window


class _FakeLLM:
    """返回固定概况的假 LLM，用于统计调用次数。"""

    def __init__(self, reply="压缩后的概况"):
        self.reply = reply
        self.calls = 0

    def invoke(self, messages):
        self.calls += 1
        return type("R", (), {"content": self.reply})()


class _FailingLLM:
    def invoke(self, messages):
        raise RuntimeError("boom")


class TestCompressWindow(unittest.TestCase):
    def test_under_window_unchanged(self):
        msgs = [HumanMessage(content=f"m{i}") for i in range(5)]
        llm = _FakeLLM()
        keep, summary = compress_window(msgs, "", llm, window_size=10)
        self.assertEqual(keep, msgs)          # 未超窗，原样返回
        self.assertEqual(summary, "")
        self.assertEqual(llm.calls, 0)        # 不调 LLM

    def test_overflow_compresses_oldest(self):
        msgs = [HumanMessage(content=f"m{i}") for i in range(15)]
        llm = _FakeLLM("概况A")
        keep, summary = compress_window(msgs, "", llm, window_size=10)
        self.assertEqual(len(keep), 10)        # 保留最近 10 条
        self.assertEqual(keep[0].content, "m5")
        self.assertEqual(keep[-1].content, "m14")
        self.assertEqual(summary, "概况A")     # 最老 5 条被压缩
        self.assertEqual(llm.calls, 1)

    def test_rolling_summary_merges_prev(self):
        msgs = [HumanMessage(content=f"m{i}") for i in range(15)]
        llm = _FakeLLM("概况B")
        keep, summary = compress_window(msgs, "旧概况", llm, window_size=10)
        self.assertEqual(len(keep), 10)
        self.assertEqual(summary, "概况B")
        self.assertEqual(llm.calls, 1)        # 旧概况作为合并输入传给 LLM

    def test_summarize_failure_falls_back(self):
        msgs = [HumanMessage(content=f"m{i}") for i in range(15)]
        llm = _FailingLLM()
        keep, summary = compress_window(msgs, "旧概况", llm, window_size=10)
        self.assertEqual(len(keep), 10)       # 仍收缩窗口
        self.assertEqual(summary, "旧概况")    # 失败退回已有概况，不崩溃


if __name__ == "__main__":
    unittest.main()
