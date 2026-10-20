"""SQLite 线程安全封装层。

设计要点（对应 M1 思考点）：
1. 每操作短连接：每次 execute/query 新建连接、用完即关，避免跨线程复用同一连接
   （SQLite 默认 check_same_thread=True 会在跨线程复用时抛异常）。
2. WAL 模式：读写不互斥，适配"监控线程写明细 + 交互线程读周报"的并发场景。
3. busy_timeout：并发写冲突时等待而非立刻抛 database is locked。
4. 全局写锁：串行化所有写操作保证确定性；读操作走 WAL 快照，不加锁。
"""
import sqlite3
import threading


class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._write_lock = threading.RLock()
        self._enable_wal()

    def _connect(self) -> sqlite3.Connection:
        """新建连接并应用连接级 PRAGMA。"""
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        conn.execute("PRAGMA busy_timeout = 5000")
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _enable_wal(self) -> None:
        """开启 WAL 模式（数据库级持久设置，仅需初始化一次）。"""
        conn = self._connect()
        try:
            conn.execute("PRAGMA journal_mode = WAL")
        finally:
            conn.close()

    def execute(self, sql: str, params=()) -> int:
        """执行写操作，返回 lastrowid。失败回滚并向上抛异常。"""
        with self._write_lock:
            conn = self._connect()
            try:
                cur = conn.execute(sql, params)
                conn.commit()
                return cur.lastrowid
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

    def query(self, sql: str, params=()):
        """执行读操作，返回 rows（list[tuple]）。"""
        conn = self._connect()
        try:
            cur = conn.execute(sql, params)
            return cur.fetchall()
        finally:
            conn.close()
