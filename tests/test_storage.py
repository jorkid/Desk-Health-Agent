"""存储层测试：日汇总、明细、设置、并发读写。"""
import os
import tempfile
import threading
import unittest
from datetime import datetime

from deskpal.storage import Database, init_schema, DailyHealthRepo, WorkBreakRepo, SettingsRepo


class TestStorage(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.db = Database(self.db_path)
        init_schema(self.db)
        self.daily = DailyHealthRepo(self.db)
        self.records = WorkBreakRepo(self.db)
        self.settings = SettingsRepo(self.db)

    def tearDown(self):
        for f in (self.db_path, self.db_path + "-wal", self.db_path + "-shm"):
            if os.path.exists(f):
                os.remove(f)

    def test_daily_upsert_and_get_today(self):
        today = datetime.now().date().isoformat()
        self.daily.upsert(today, 3600, 2, 1, 3.5, 7.0, ["多休息"], {"mouse_dist": 100})
        self.assertEqual(
            self.daily.get_today(),
            {"work_seconds": 3600, "short_breaks": 2, "long_breaks": 1},
        )

    def test_weekly_contains_today(self):
        today = datetime.now().date().isoformat()
        self.daily.upsert(today, 3600, 2, 1, 3.5, 7.0, [], {})
        self.assertTrue(any(r["date"] == today for r in self.daily.get_weekly()))

    def test_settings_get_set(self):
        self.settings.set("work_duration", 2400)
        self.assertEqual(self.settings.get("work_duration", 1800), "2400")
        self.assertEqual(self.settings.get("missing", "default"), "default")

    def test_concurrent_read_write(self):
        errors = []

        def writer():
            try:
                for _ in range(100):
                    self.records.add_record("work", duration_seconds=30)
            except Exception as e:
                errors.append(repr(e))

        def reader():
            try:
                for _ in range(100):
                    self.daily.get_weekly()
            except Exception as e:
                errors.append(repr(e))

        threads = [threading.Thread(target=writer), threading.Thread(target=reader)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
