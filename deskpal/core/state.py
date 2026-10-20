"""共享运行时状态容器：跨链路（监控/对话）共享，线程安全。

监控链路读取当前工作时长、对话链路通过工具修改工作时长，两者并发访问，
因此所有读写都要加锁。安全边界 clamp 统一放在这里，保证任何入口
（工具、LLM 建议值）改工作时长时都经过同一道安全网。
"""
import threading


class AppState:
    def __init__(self, work_duration_seconds: int = 1800,
                 work_duration_min: int = 600, work_duration_max: int = 7200,
                 fatigue: int = 3, sleep_hours: int = 7):
        self._lock = threading.RLock()
        self._work_duration = work_duration_seconds
        self._revision = 0  # 工作时长变更版本号：监控线程据此感知"时长变了，重新计时"
        self.work_duration_min = work_duration_min
        self.work_duration_max = work_duration_max
        # 用户自评健康基线（低频更新，暂不加锁；未来可由对话工具修改）
        self.fatigue = fatigue
        self.sleep_hours = sleep_hours
        # 最近一次空闲询问时用户自报的状态：'工作学习' / '放松' / None（未询问过）
        # 仅监控线程内部读写，无并发，故不加锁
        self.idle_activity_label = None
        # 每日状态收集（启动时一次）：心情 + 前夜睡眠质量，未收集时为 None
        # 由启动流程写入、监控线程读取，写入先于监控线程启动，无并发
        self.mood = None
        self.sleep_quality = None
        # 上层注入的数据访问对象（M7 组装时设置为 dict，含 'daily' 等 Repo）
        self.repos = None

    @property
    def work_duration(self) -> int:
        """当前工作时长（秒）：工作多久后提醒休息。"""
        with self._lock:
            return self._work_duration

    def get_revision(self) -> int:
        """返回当前版本号，供监控线程判断时长是否在其睡眠期间被修改。"""
        with self._lock:
            return self._revision

    def update_work_duration(self, value: int) -> int:
        """按安全边界 clamp 后更新工作时长，返回实际生效值。"""
        clamped = max(self.work_duration_min, min(self.work_duration_max, int(value)))
        with self._lock:
            self._work_duration = clamped
            self._revision += 1  # 每次变更自增，唤醒正在睡眠的监控线程重新计时
        return clamped
