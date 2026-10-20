"""主窗口 + 聊天面板。

设计要点：
1. 聊天面板替代旧代码的 input() 命令行交互；
2. 发送动作通过 on_send 回调交给上层（M6 注入对话链路处理），
   本层只负责 UI 展示，不关心对话逻辑。
"""
import tkinter as tk

from deskpal.ui.popup import PopupManager


class ChatApp:
    def __init__(self, on_send=None, popup_poll_ms: int = 200):
        self.root = tk.Tk()
        self.root.title("工位健康管家")
        self.on_send = on_send
        self.popup = PopupManager(self.root, popup_poll_ms)
        self._build_ui()

    def _build_ui(self) -> None:
        self.text = tk.Text(self.root, height=20, width=60, state="disabled", wrap="word")
        self.text.pack(padx=10, pady=10)

        bottom = tk.Frame(self.root)
        bottom.pack(fill="x", padx=10, pady=(0, 10))
        self.entry = tk.Entry(bottom)
        self.entry.pack(side="left", fill="x", expand=True)
        self.entry.bind("<Return>", lambda e: self._on_send_clicked())
        send_btn = tk.Button(bottom, text="发送", command=self._on_send_clicked)
        send_btn.pack(side="right", padx=(5, 0))

    def _on_send_clicked(self) -> None:
        text = self.entry.get().strip()
        if not text:
            return
        self.entry.delete(0, "end")
        self.display_message("你", text)
        if self.on_send:
            self.on_send(text)

    def display_message(self, role: str, content: str) -> None:
        """在聊天区追加一条消息。"""
        self.text.configure(state="normal")
        self.text.insert("end", f"{role}: {content}\n")
        self.text.see("end")
        self.text.configure(state="disabled")

    def run(self) -> None:
        self.popup.start_polling()
        self.root.mainloop()
