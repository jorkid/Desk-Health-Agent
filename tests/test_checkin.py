"""每日状态收集（checkin）的去重 + 持久化测试。"""
import os
import shutil
import tempfile
import unittest
from datetime import datetime
from unittest import mock

from deskpal.core import AppState
from deskpal.core.checkin import (
    collect_daily_checkin,
    LAST_CHECKIN_KEY,
    MOOD_KEY,
    SLEEP_KEY,
)
from deskpal.storage import Database, init_schema, SettingsRepo


class TestDailyCheckin(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db = Database(os.path.join(self.tmpdir, "test.db"))
        init_schema(self.db)
        self.settings = SettingsRepo(self.db)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _app_state(self):
        state = AppState()
        state.repos = {"settings": self.settings}
        return state

    def test_first_checkin_collects_and_persists(self):
        state = self._app_state()
        with mock.patch(
            "deskpal.core.checkin.ask_choice_sync",
            side_effect=["很好", "一般"],
        ) as ask:
            collect_daily_checkin(state, root=None)

        self.assertEqual(state.mood, "很好")
        self.assertEqual(state.sleep_quality, "一般")
        self.assertEqual(ask.call_count, 2)  # 心情 + 睡眠各弹一次
        self.assertEqual(self.settings.get(LAST_CHECKIN_KEY), datetime.now().date().isoformat())
        self.assertEqual(self.settings.get(MOOD_KEY), "很好")
        self.assertEqual(self.settings.get(SLEEP_KEY), "一般")

    def test_same_day_restart_skips_collection(self):
        # 首次收集
        with mock.patch(
            "deskpal.core.checkin.ask_choice_sync",
            side_effect=["不错", "较差"],
        ):
            collect_daily_checkin(self._app_state(), root=None)

        # 模拟同一天重启：新 AppState（mood/sleep 初始为 None），应跳过弹窗并恢复
        fresh = self._app_state()
        with mock.patch(
            "deskpal.core.checkin.ask_choice_sync",
            side_effect=AssertionError("同一天不应再次弹窗"),
        ) as ask:
            collect_daily_checkin(fresh, root=None)

        self.assertEqual(ask.call_count, 0)
        self.assertEqual(fresh.mood, "不错")
        self.assertEqual(fresh.sleep_quality, "较差")

    def test_no_prior_data_restores_none(self):
        # 从未收集过：应正常弹窗收集（不会从 settings 读到脏数据）
        with mock.patch(
            "deskpal.core.checkin.ask_choice_sync",
            side_effect=["一般", "很好"],
        ):
            collect_daily_checkin(self._app_state(), root=None)
        self.assertEqual(self.settings.get(MOOD_KEY), "一般")
        self.assertEqual(self.settings.get(SLEEP_KEY), "很好")


if __name__ == "__main__":
    unittest.main()
