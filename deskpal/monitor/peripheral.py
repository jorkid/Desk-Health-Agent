"""外设监控采集层：监听键鼠，累计活跃度指标。

基于旧 gwjkgj.py 的 PeripheralMonitor 重构增强，改进点：
1. 保存 Listener 引用，防止被 GC 回收导致监听悄悄停止；
2. 提供显式 start()/stop() 生命周期，配合 M7 优雅退出；
3. 新增 move_events（移动事件次数），比绝对像素距离更稳定、跨 DPI 可比；
4. 明确 get_stats 只读、reset 显式清零的语义边界；
5. 本层不依赖 config，构造参数由上层注入（依赖注入）。

线程模型：回调运行在 pynput 内部线程，主线程读数据，
所有共享状态用 _lock 保护，回调内保持轻量（只做计数）。
"""
import threading
import time

from pynput import mouse, keyboard


class PeripheralMonitor:
    def __init__(self, idle_timeout_seconds: float = 180.0):
        self.idle_timeout = idle_timeout_seconds
        self._lock = threading.Lock()
        self._listeners = []  # 保存引用，防 GC
        self._reset_internal()

    def _reset_internal(self):
        """在锁内清零所有累计状态（供 __init__ / reset 调用）。"""
        self.mouse_dist = 0.0
        self.key_count = 0
        self.scroll_count = 0
        self.move_events = 0
        self.last_activity = time.time()
        self.last_pos = None

    # ---- 生命周期 ----
    def start(self) -> None:
        """启动键鼠监听（幂等）。"""
        if self._listeners:
            return
        ml = mouse.Listener(on_move=self._on_move, on_scroll=self._on_scroll)
        kl = keyboard.Listener(on_press=self._on_press)
        ml.start()
        kl.start()
        self._listeners = [ml, kl]

    def stop(self) -> None:
        """停止键鼠监听。"""
        for listener in self._listeners:
            listener.stop()
        self._listeners = []

    @property
    def running(self) -> bool:
        return bool(self._listeners)

    # ---- 回调（运行在 pynput 内部线程，加锁且保持轻量）----
    def _on_move(self, x, y):
        with self._lock:
            if self.last_pos is not None:
                dx = x - self.last_pos[0]
                dy = y - self.last_pos[1]
                self.mouse_dist += (dx * dx + dy * dy) ** 0.5
            self.last_pos = (x, y)
            self.move_events += 1
            self.last_activity = time.time()

    def _on_scroll(self, x, y, dx, dy):
        with self._lock:
            self.scroll_count += abs(dy)
            self.last_activity = time.time()

    def _on_press(self, key):
        with self._lock:
            self.key_count += 1
            self.last_activity = time.time()

    # ---- 数据读取（只读，不重置）----
    def get_stats(self) -> dict:
        with self._lock:
            idle_seconds = time.time() - self.last_activity
            return {
                "mouse_dist": round(self.mouse_dist, 2),
                "key_count": self.key_count,
                "scroll_count": self.scroll_count,
                "move_events": self.move_events,
                "idle_seconds": round(idle_seconds, 1),
                "is_idle": idle_seconds > self.idle_timeout,
            }

    def mark_activity(self) -> None:
        """标记一次活动：仅刷新 last_activity，不清零累计指标。

        用途：空闲询问后用户确认"仍在工位"但未产生键鼠事件，
        若不刷新 idle 计时，会立即再次触发空闲询问，造成重复弹窗。
        """
        with self._lock:
            self.last_activity = time.time()

    def reset(self) -> None:
        """清零累计，开始下一个采集窗口。"""
        with self._lock:
            self._reset_internal()
