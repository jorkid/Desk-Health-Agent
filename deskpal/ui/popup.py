"""Windows 桌面弹窗组件：跨线程安全的弹窗队列 + 双选交互对话框。

设计要点：
1. tkinter 只能在主线程操作；监控线程要弹窗不能直接弹，
   而是把弹窗请求 put 进线程安全的 queue.Queue；
2. 主线程用 root.after() 周期轮询队列，取出请求再弹窗；
3. 休息提醒是"交互式"的：监控线程需要知道用户点了哪个按钮，
   因此 request_choices 返回一个 _PopupResult，监控线程 result.wait() 阻塞等待，
   主线程弹窗后 result.set(选择) 唤醒监控线程（threading.Event 跨线程同步）；
4. 这是"生产者-消费者 + UI 轮询 + Event 同步"模式，彻底避免跨线程操作 UI。
"""
import logging
import queue
import threading
import tkinter as tk
from tkinter import messagebox

logger = logging.getLogger(__name__)


class _PopupResult:
    """跨线程传递用户选择的结果持有者（一次性）。"""

    def __init__(self):
        self._event = threading.Event()
        self.choice = None  # 用户选择的按钮索引；None 表示直接关闭（点 X）

    def wait(self, timeout=None) -> bool:
        """阻塞等待用户选择；True=已有选择/关闭，False=超时未选择。"""
        return self._event.wait(timeout)

    def set(self, choice) -> None:
        """设置选择（幂等）：只接受第一次，避免"用户点按钮"与"超时自动关闭"互相覆盖。"""
        if self._event.is_set():
            return
        self.choice = choice
        self._event.set()


class PopupManager:
    def __init__(self, root, poll_ms: int = 200):
        self.root = root
        self.poll_ms = poll_ms
        self._queue = queue.Queue()

    def request(self, title: str, text: str) -> None:
        """任意线程调用：投递一个单按钮通知弹窗（线程安全）。"""
        self._queue.put(("info", title, text))

    def request_choices(self, title: str, text: str, choices, topmost: bool = False) -> _PopupResult:
        """任意线程调用：投递一个多选弹窗，返回 result 供调用方阻塞等待选择。

        topmost=True 时弹窗置顶（用于休息提醒等需要打断用户的关键弹窗）。
        """
        result = _PopupResult()
        self._queue.put(("choices", title, text, list(choices), result, topmost))
        return result

    def request_rest_countdown(self, title: str, rest_seconds: int) -> _PopupResult:
        """任意线程调用：投递一个休息倒计时弹窗，返回 result 供调用方阻塞等待。

        result.choice 复用为「用户实际休息的总秒数」（而非按钮索引）。
        """
        result = _PopupResult()
        self._queue.put(("rest", title, rest_seconds, result))
        return result

    def start_polling(self) -> None:
        """主线程调用：启动轮询循环。"""
        self._poll_once()

    def _poll_once(self) -> None:
        """轮询一次：非阻塞取空队列，有则弹窗，然后安排下一次轮询。"""
        try:
            while True:
                item = self._queue.get_nowait()
                kind = item[0]
                if kind == "info":
                    self._show_info(*item[1:])
                elif kind == "choices":
                    _, title, text, choices, result, topmost = item
                    self._show_choices(title, text, choices, result, topmost=topmost)
                elif kind == "rest":
                    _, title, rest_seconds, result = item
                    self._show_rest_countdown(title, rest_seconds, result)
        except queue.Empty:
            pass
        except Exception:
            # 弹窗异常绝不能中断轮询链：一旦轮询停止，后续弹窗永不显示、
            # 监控线程会在 result.wait 上永久阻塞，表现为"到时不提醒、窗口卡死"。
            logger.exception("弹窗轮询发生异常，跳过本次并继续轮询")
        self.root.after(self.poll_ms, self._poll_once)

    def _show_info(self, title: str, text: str) -> None:
        """单按钮通知（仅主线程调用）。"""
        messagebox.showinfo(title, text)

    def _show_choices(self, title: str, text: str, choices, result: _PopupResult,
                      timeout_ms: int = 60_000, topmost: bool = False) -> None:
        """双选对话框（仅主线程调用）。用户选择后 result.set(索引) 唤醒监控线程。

        防死机设计（关键）：
        1. 不设 -topmost、不 grab_set：弹窗只 lift 到主窗口前，绝不抢占系统焦点，
           用户随时能 Alt+Tab 切走、点任务栏、开任务管理器结束进程；
        2. 超时自动关闭（默认 60s）：避免 wait_window 永久阻塞拖垮主线程。
        """
        dialog = tk.Toplevel(self.root)
        dialog.title(title)
        dialog.transient(self.root)

        tk.Label(
            dialog, text=text, justify="left", wraplength=400, padx=24, pady=20,
            font=("Microsoft YaHei", 11),
        ).pack()

        btn_frame = tk.Frame(dialog)
        btn_frame.pack(pady=(0, 20))
        for idx, label in enumerate(choices):
            btn = tk.Button(
                btn_frame, text=label, width=16,
                command=lambda i=idx: self._choose(dialog, result, i),
            )
            btn.pack(side="left", padx=8)

        # 点 X 关闭 = 未明确选择，传 None（监控线程按"稍后再提醒"处理）
        dialog.protocol("WM_DELETE_WINDOW", lambda: self._choose(dialog, result, None))
        # 强制渲染并显示：在 after 回调里新建的 Toplevel 若不先 update，
        # 可能未 map 就进入 wait_window，导致窗口不可见。
        dialog.update_idletasks()
        dialog.deiconify()
        dialog.lift()
        if topmost:
            # 关键提醒（如休息提醒）置顶，确保盖过其它应用；不 grab_set，仍可 Alt+Tab 切走
            dialog.attributes("-topmost", True)
        # 超时兜底：无人响应则自动关闭（幂等，见 _PopupResult.set），绝不让主线程卡死
        dialog.after(timeout_ms, lambda: self._choose(dialog, result, None))
        dialog.wait_window()   # 主线程局部事件循环，等窗口关闭

    def _show_rest_countdown(self, title: str, rest_seconds: int,
                             result: _PopupResult) -> None:
        """休息倒计时弹窗（仅主线程调用）。

        交互流程：
        - 倒计时进行中：显示剩余时间 + [我已休息结束]（提前结束）；
        - 倒计时归零：显示"时间到" + [延续休息 | 休息完毕]，延续不限次数；
        - 点 X 关闭 = 提前结束。

        最终 result.set(实际休息总秒数) 唤醒监控线程。
        防死机：不设 -topmost、不 grab_set；倒计时由 after 驱动，不阻塞主线程。
        """
        dialog = tk.Toplevel(self.root)
        dialog.title(title)
        dialog.transient(self.root)

        label = tk.Label(
            dialog, text="", justify="center", padx=24, pady=20,
            font=("Microsoft YaHei", 18),
        )
        label.pack()
        btn_frame = tk.Frame(dialog)
        btn_frame.pack(pady=(0, 20))

        state = {"remaining": rest_seconds, "rested": 0}

        def clear_buttons():
            for w in btn_frame.winfo_children():
                w.destroy()

        def show_time():
            m, s = divmod(state["remaining"], 60)
            label.configure(text=f"休息中，剩余 {m:02d}:{s:02d}")

        def finish():
            # 累计的已休息秒数在归零/提前结束时已加好，这里只负责唤醒监控线程
            try:
                dialog.destroy()
            except tk.TclError:
                pass
            result.set(state["rested"])

        def end_early():
            # 提前结束：累计本轮已休息的时长
            state["rested"] += rest_seconds - state["remaining"]
            finish()

        def continue_rest():
            # 延续休息：重新倒计时一轮（上一轮完整时长已在归零时累计）
            state["remaining"] = rest_seconds
            render_counting()
            show_time()
            dialog.after(1000, tick)

        def render_counting():
            clear_buttons()
            tk.Button(btn_frame, text="我已休息结束", width=16,
                      command=end_early).pack()

        def render_expired():
            clear_buttons()
            label.configure(text="休息时间到！")
            tk.Button(btn_frame, text="延续休息", width=16,
                      command=continue_rest).pack(side="left", padx=8)
            tk.Button(btn_frame, text="休息完毕", width=16,
                      command=finish).pack(side="left", padx=8)

        def tick():
            if not dialog.winfo_exists():
                return  # 窗口已销毁（提前结束/休息完毕），停止倒计时
            if state["remaining"] > 0:
                state["remaining"] -= 1
                show_time()
                dialog.after(1000, tick)
            else:
                # 倒计时归零：本轮完整休息完成，累计时长，切换为「延续/完毕」
                state["rested"] += rest_seconds
                render_expired()

        dialog.protocol("WM_DELETE_WINDOW", end_early)  # 点 X = 提前结束
        render_counting()
        show_time()
        dialog.update_idletasks()
        dialog.deiconify()
        dialog.lift()
        dialog.after(1000, tick)
        dialog.wait_window()

    def _choose(self, dialog, result: _PopupResult, choice) -> None:
        try:
            dialog.destroy()
        except tk.TclError:
            pass  # 窗口已销毁（超时与点击竞态）时忽略
        result.set(choice)


def ask_choice_sync(root, title: str, text: str, choices, timeout_ms: int = 60_000):
    """主线程同步弹多选对话框，返回用户选中的标签；点 X 关闭返回 None。

    与 PopupManager 的队列式异步弹窗不同，此函数直接阻塞（wait_window）等待选择，
    用于启动时的状态收集等需要同步拿结果的场景；mainloop 之前也能调用。

    防死机：不设 -topmost、不 grab_set，超时自动返回 None，绝不无限阻塞。
    """
    dialog = tk.Toplevel(root)
    dialog.title(title)
    dialog.transient(root)

    tk.Label(
        dialog, text=text, justify="left", wraplength=400, padx=24, pady=20,
        font=("Microsoft YaHei", 11),
    ).pack()

    result = {"choice": None}

    def choose(label):
        if "done" in result:
            return  # 幂等：避免"用户点击"与"超时关闭"重复销毁
        result["done"] = True
        result["choice"] = label
        try:
            dialog.destroy()
        except tk.TclError:
            pass

    btn_frame = tk.Frame(dialog)
    btn_frame.pack(pady=(0, 20))
    for label in choices:
        btn = tk.Button(btn_frame, text=label, width=16, command=lambda l=label: choose(l))
        btn.pack(side="left", padx=8)

    dialog.protocol("WM_DELETE_WINDOW", lambda: choose(None))
    dialog.update_idletasks()
    dialog.deiconify()
    dialog.lift()
    dialog.after(timeout_ms, lambda: choose(None))  # 超时兜底
    dialog.wait_window()
    return result["choice"]
