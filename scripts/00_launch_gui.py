
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import subprocess, os, threading, time, queue

I18N = {
  "zh": {
    "title": "MLS 本地化流水线",
    "file": "文件",
    "open_excel": "选择 Excel…",
    "open_gloss": "选择术语表…",
    "run": "运行",
    "dry_run": "仅预览",
    "override": "覆盖已有译文（重译）",
    "row_range": "行号范围（如 1800-2100，可空）",
    "speaker_filter": "Speaker 过滤（支持 *，可空）",
    "target_lang": "目标语言",
    "log": "运行日志",
    "open_output": "打开输出",
    "config": "配置",
    "provider": "提供商",
    "help": "帮助",
  },
  "en": {
    "title": "MLS Localization Pipeline",
    "file": "File",
    "open_excel": "Pick Excel…",
    "open_gloss": "Pick Glossary…",
    "run": "Run",
    "dry_run": "Dry run",
    "override": "Override translated (re-translate)",
    "row_range": "Row Range (e.g. 1800-2100, optional)",
    "speaker_filter": "Speaker filter (supports *, optional)",
    "target_lang": "Target language",
    "log": "Logs",
    "open_output": "Open Output",
    "config": "Config",
    "provider": "Provider",
    "help": "Help",
  }
}

class App:
    def __init__(self, root):
        self.root = root
        self.lang = "zh"
        t = I18N[self.lang]
        root.title(t["title"])
        root.geometry("980x640")

        self.excel = tk.StringVar(value="data/MLS Chinese.xlsx")
        self.gloss = tk.StringVar(value="data/name_map.json")
        self.target = tk.StringVar(value="zh-CN")
        self.row_range = tk.StringVar(value="")
        self.spk_filter = tk.StringVar(value="")
        self.override = tk.BooleanVar(value=False)
        self.dry_run = tk.BooleanVar(value=False)

        self._build_menu()
        self._build_body()
        self._apply_i18n()

        self.proc = None
        self.q = queue.Queue()
        self._poll_log()

    def _build_menu(self):
        self.mbar = tk.Menu(self.root)
        self.root.config(menu=self.mbar)
        self.m_file = tk.Menu(self.mbar, tearoff=0)
        self.m_file.add_command(label="EN/中文", command=self.toggle_lang)
        self.mbar.add_cascade(label="文件", menu=self.m_file)

    def _apply_i18n(self):
        t = I18N[self.lang]
        self.root.title(t["title"])
        # Inputs
        self.lbl_excel.config(text=t["open_excel"])
        self.lbl_gloss.config(text=t["open_gloss"])
        self.lbl_target.config(text=t["target_lang"])
        self.lbl_row.config(text=t["row_range"])
        self.lbl_spk.config(text=t["speaker_filter"])
        self.chk_override.config(text=t["override"])
        self.chk_dry.config(text=t["dry_run"])
        self.btn_run.config(text=t["run"])
        self.btn_open.config(text=t["open_output"])
        self.lbl_log.config(text=t["log"])

    def toggle_lang(self):
        self.lang = "en" if self.lang == "zh" else "zh"
        self._apply_i18n()

    def _build_body(self):
        frm = ttk.Frame(self.root); frm.pack(fill="both", expand=True, padx=8, pady=8)
        # inputs
        grid = ttk.Frame(frm); grid.pack(fill="x")
        self.lbl_excel = ttk.Label(grid, text="选择 Excel…"); self.lbl_excel.grid(row=0, column=0, sticky="w")
        ttk.Entry(grid, textvariable=self.excel, width=60).grid(row=0, column=1, sticky="we", padx=6)
        ttk.Button(grid, text="…", command=self.pick_excel, width=3).grid(row=0, column=2)
        self.lbl_gloss = ttk.Label(grid, text="选择术语表…"); self.lbl_gloss.grid(row=1, column=0, sticky="w")
        ttk.Entry(grid, textvariable=self.gloss, width=60).grid(row=1, column=1, sticky="we", padx=6)
        ttk.Button(grid, text="…", command=self.pick_gloss, width=3).grid(row=1, column=2)
        self.lbl_target = ttk.Label(grid, text="目标语言"); self.lbl_target.grid(row=2, column=0, sticky="w")
        ttk.Entry(grid, textvariable=self.target, width=20).grid(row=2, column=1, sticky="w", padx=6)
        self.lbl_row = ttk.Label(grid, text="行号范围"); self.lbl_row.grid(row=3, column=0, sticky="w")
        ttk.Entry(grid, textvariable=self.row_range, width=20).grid(row=3, column=1, sticky="w", padx=6)
        self.lbl_spk = ttk.Label(grid, text="Speaker 过滤"); self.lbl_spk.grid(row=4, column=0, sticky="w")
        ttk.Entry(grid, textvariable=self.spk_filter, width=20).grid(row=4, column=1, sticky="w", padx=6)

        self.chk_override = ttk.Checkbutton(grid, text="覆盖已有译文（重译）", variable=self.override)
        self.chk_override.grid(row=5, column=1, sticky="w", pady=4)
        self.chk_dry = ttk.Checkbutton(grid, text="仅预览", variable=self.dry_run)
        self.chk_dry.grid(row=5, column=1, sticky="e", pady=4)

        # buttons
        btns = ttk.Frame(frm); btns.pack(fill="x", pady=6)
        self.btn_run = ttk.Button(btns, text="运行", command=self.on_run, width=12); self.btn_run.pack(side="left")
        self.btn_open = ttk.Button(btns, text="打开输出", command=self.open_output, width=12, state=tk.DISABLED); self.btn_open.pack(side="left", padx=6)

        # log
        self.lbl_log = ttk.Label(frm, text="运行日志"); self.lbl_log.pack(anchor="w")
        self.txt = tk.Text(frm, height=20, wrap="word")
        self.txt.pack(fill="both", expand=True)
        self.txt.tag_config("INFO", foreground="#c0e5ff")
        self.txt.tag_config("OK", foreground="#a7f3d0")
        self.txt.tag_config("ERR", foreground="#fda4af")

        # progress
        self.pb = ttk.Progressbar(frm, mode="indeterminate")
        self.pb.pack(fill="x", pady=4)

    def pick_excel(self):
        p = filedialog.askopenfilename(filetypes=[("Excel","*.xlsx")])
        if p:
            self.excel.set(p)

    def pick_gloss(self):
        p = filedialog.askopenfilename(filetypes=[("JSON","*.json")])
        if p:
            self.gloss.set(p)

    def append_log(self, line, tag="INFO"):
        self.txt.insert("end", line + "\n", tag)
        self.txt.see("end")

    def run_cmd(self, cmd: list):
        self.append_log(" ".join(cmd), "INFO")
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for line in p.stdout:
            self.append_log(line.rstrip(), "INFO")
        rc = p.wait()
        if rc != 0:
            self.append_log(f"[ERROR] step failed: rc={rc}", "ERR")
        else:
            self.append_log("[OK] 步骤完成。", "OK")
        return rc

    def on_run(self):
        if self.proc is not None:
            messagebox.showwarning("Busy", "Pipeline is running.")
            return
        self.pb.start(10)
        t = threading.Thread(target=self._run_pipeline, daemon=True)
        t.start()

    def _run_pipeline(self):
        try:
            self.append_log("[INFO] 开始运行流水线…", "INFO")
            # 05
            rc = self.run_cmd(["python", "-u", "-m", "scripts.05_segment_context", "--excel", self.excel.get(), "--sheet-index", "0"])
            if rc != 0: return
            # 20
            rc = self.run_cmd(["python", "-u", "-m", "scripts.20_enforce_terms", "--excel", self.excel.get(), "--sheet", "0", "--glossary", self.gloss.get(), "--overwrite"])
            if rc != 0: return
            # 12
            cmd12 = ["python", "-u", "-m", "scripts.12_llm_translate", "--excel", self.excel.get(), "--sheet-index", "0",
                     "--target-lang", self.target.get(), "--glossary", self.gloss.get()]
            if self.row_range.get().strip():
                cmd12 += ["--row-range", self.row_range.get().strip()]
            if self.spk_filter.get().strip():
                cmd12 += ["--speaker-filter", self.spk_filter.get().strip()]
            if self.override.get():
                cmd12 += ["--override"]
            if self.dry_run.get():
                cmd12 += ["--dry-run"]
            rc = self.run_cmd(cmd12)
            if rc != 0: return
            # 21
            rc = self.run_cmd(["python", "-u", "-m", "scripts.21_enforce_terms_again", "--excel", self.excel.get(), "--sheet", "0", "--glossary", self.gloss.get()])
            if rc != 0: return

            self.append_log("[OK] 全部完成。", "OK")
            self.btn_open.config(state=tk.NORMAL)
        finally:
            self.pb.stop()

    def open_output(self):
        # open the .llm.xlsx if exists
        outp = self.excel.get().replace(".xlsx", f".{self.target.get()}.llm.xlsx")
        if os.path.exists(outp):
            if os.name == "nt":
                os.startfile(outp)
            else:
                subprocess.call(["open", outp])
        else:
            messagebox.showinfo("提示", f"未找到：{outp}")

def main():
    root = tk.Tk()
    App(root)
    root.mainloop()

if __name__ == "__main__":
    main()
