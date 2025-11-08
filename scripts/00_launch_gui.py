
import os
import sys
import json
import queue
import threading
import subprocess
import time
import re
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

APP_TITLE = "MLS Optimizer - Pipeline GUI"
DEFAULT_EXCEL = "data/MLS Chinese.xlsx"
DEFAULT_GLOSSARY = "data/name_map.json"
PYTHON_EXE = sys.executable or "python"

LANG_CHOICES = [
    "zh-CN","zh-TW","en","ja","ko","fr","de","es","ru","pt-BR","it","tr","vi","th","id",
    "ar","he","hi","pl","uk","cs","ro","hu","el","nl","sv","fi","no","da"
]

def which(path):
    return str(Path(path))

class ProcRunner:
    """Run a sequence of commands, streaming stdout to a callback (append-only)."""
    def __init__(self, log_cb, on_line_cb=None, on_done=None):
        self._log_cb = log_cb
        self._on_line_cb = on_line_cb
        self._on_done = on_done
        self._thr = None
        self._proc = None
        self._stop_flag = threading.Event()

    def running(self):
        return (self._thr is not None) and self._thr.is_alive()

    def stop(self):
        self._stop_flag.set()
        p = self._proc
        if p and (p.poll() is None):
            try:
                p.terminate()
            except Exception:
                pass

    def run(self, commands):
        if self.running():
            return False
        self._stop_flag.clear()
        self._thr = threading.Thread(target=self._worker, args=(commands,), daemon=True)
        self._thr.start()
        return True

    def _worker(self, commands):
        rc_final = 0
        for (title, cmd, cwd) in commands:
            if self._stop_flag.is_set():
                break
            self._log_cb(f"[INFO] == {title} ==\n")
            self._log_cb(which(" ".join(cmd)) + "\n")

            try:
                self._proc = subprocess.Popen(
                    cmd,
                    cwd=cwd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    bufsize=1,
                    universal_newlines=True,
                )
            except Exception as e:
                self._log_cb(f"[ERROR] spawn failed: {e}\n")
                rc_final = 1
                break

            for line in self._proc.stdout:
                if self._stop_flag.is_set():
                    break
                self._log_cb(line)
                if self._on_line_cb:
                    self._on_line_cb(line)

            self._proc.wait()
            rc = self._proc.returncode or 0
            self._proc = None
            if rc != 0:
                self._log_cb(f"[ERROR] step failed: rc={rc}\n")
                rc_final = rc
                break
            else:
                self._log_cb("[OK] Step finished.\n")

        if self._on_done:
            self._on_done(rc_final)

class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title(APP_TITLE)
        root.geometry("1040x720")
        root.minsize(900, 600)

        self.excel_var = tk.StringVar(value=DEFAULT_EXCEL)
        self.glossary_var = tk.StringVar(value=DEFAULT_GLOSSARY)
        self.sheet_idx_var = tk.IntVar(value=0)
        self.lang_var = tk.StringVar(value="zh-CN")

        self.overwrite_var = tk.BooleanVar(value=False)
        self.row_range_var = tk.StringVar(value="")
        self.speakers_var = tk.StringVar(value="")
        self.scene_range_var = tk.StringVar(value="")
        self.dry_run_var = tk.BooleanVar(value=False)

        # post steps
        self.do_terms_var = tk.BooleanVar(value=True)   # 术语统一
        self.do_style_var = tk.BooleanVar(value=True)   # 风格适配
        self.do_qa_var = tk.BooleanVar(value=True)      # QA

        self.progress_total = 0
        self.progress_pct = 0.0
        self.last_output_path = None

        self._build_menu()
        self._build_body()

        self.runner = ProcRunner(log_cb=self.append_log, on_line_cb=self._parse_line, on_done=self._on_done)
        self._tick()

    def _build_menu(self):
        menubar = tk.Menu(self.root)
        # File
        m_file = tk.Menu(menubar, tearoff=0)
        m_file.add_command(label="选择 Excel…", command=self.pick_excel)
        m_file.add_command(label="选择 术语表…", command=self.pick_glossary)
        m_file.add_separator()
        m_file.add_command(label="打开输出文件", command=self.open_output)
        m_file.add_separator()
        m_file.add_command(label="退出", command=self.root.quit)
        menubar.add_cascade(label="文件", menu=m_file)

        # View
        m_view = tk.Menu(menubar, tearoff=0)
        self.show_time = tk.BooleanVar(value=True)
        m_view.add_checkbutton(label="日志显示时间戳", onvalue=True, offvalue=False, variable=self.show_time)
        menubar.add_cascade(label="视图", menu=m_view)

        # Help
        m_help = tk.Menu(menubar, tearoff=0)
        m_help.add_command(label="README（打开）", command=self.open_readme)
        menubar.add_cascade(label="帮助", menu=m_help)

        self.root.config(menu=menubar)

    def _build_body(self):
        # Top form
        frm_top = ttk.Frame(self.root, padding=8)
        frm_top.pack(side="top", fill="x")

        # Row 1: Excel + Glossary + Sheet
        row1 = ttk.Frame(frm_top)
        row1.pack(side="top", fill="x", pady=2)
        ttk.Label(row1, text="Excel:").pack(side="left")
        ttk.Entry(row1, textvariable=self.excel_var, width=60).pack(side="left", padx=4, fill="x", expand=True)
        ttk.Button(row1, text="浏览…", command=self.pick_excel).pack(side="left", padx=4)
        ttk.Label(row1, text="术语表:").pack(side="left", padx=(12, 0))
        ttk.Entry(row1, textvariable=self.glossary_var, width=30).pack(side="left", padx=4)
        ttk.Button(row1, text="浏览…", command=self.pick_glossary).pack(side="left", padx=4)
        ttk.Label(row1, text="Sheet:").pack(side="left", padx=(12, 0))
        spn = ttk.Spinbox(row1, from_=0, to=999, textvariable=self.sheet_idx_var, width=4)
        spn.pack(side="left")

        # Row 2: Target language + overwrite
        row2 = ttk.Frame(frm_top)
        row2.pack(side="top", fill="x", pady=2)
        ttk.Label(row2, text="目标语言:").pack(side="left")
        self.cb_lang = ttk.Combobox(row2, textvariable=self.lang_var, values=LANG_CHOICES, width=12, state="readonly")
        self.cb_lang.pack(side="left", padx=4)
        ttk.Checkbutton(row2, text="覆盖已有译文（重译）", variable=self.overwrite_var).pack(side="left", padx=12)

        # Row 3: filters
        row3 = ttk.Frame(frm_top)
        row3.pack(side="top", fill="x", pady=2)
        ttk.Label(row3, text="行号范围 start:end").pack(side="left")
        ttk.Entry(row3, textvariable=self.row_range_var, width=12).pack(side="left", padx=4)
        ttk.Label(row3, text="Speaker 过滤（* 支持）").pack(side="left", padx=(12,0))
        ttk.Entry(row3, textvariable=self.speakers_var, width=18).pack(side="left", padx=4)
        ttk.Label(row3, text="场景范围 a:b").pack(side="left", padx=(12,0))
        ttk.Entry(row3, textvariable=self.scene_range_var, width=10).pack(side="left", padx=4)
        ttk.Checkbutton(row3, text="仅预览（Dry run）", variable=self.dry_run_var).pack(side="left", padx=12)

        # Row 4: pipeline post steps
        row4 = ttk.Frame(frm_top)
        row4.pack(side="top", fill="x", pady=(6,2))
        ttk.Label(row4, text="后处理：").pack(side="left")
        ttk.Checkbutton(row4, text="术语统一", variable=self.do_terms_var).pack(side="left", padx=6)
        ttk.Checkbutton(row4, text="风格适配", variable=self.do_style_var).pack(side="left", padx=6)
        ttk.Checkbutton(row4, text="QA 检查", variable=self.do_qa_var).pack(side="left", padx=6)

        # Row 5: buttons
        row5 = ttk.Frame(frm_top)
        row5.pack(side="top", fill="x", pady=(6,4))
        self.btn_run = ttk.Button(row5, text="一键运行", command=self.on_run)
        self.btn_run.pack(side="left")
        ttk.Button(row5, text="仅预览", command=self.on_dry_run).pack(side="left", padx=8)
        self.btn_stop = ttk.Button(row5, text="停止", command=self.on_stop, state=tk.DISABLED)
        self.btn_stop.pack(side="left", padx=8)
        self.btn_open = ttk.Button(row5, text="打开输出", command=self.open_output, state=tk.DISABLED)
        self.btn_open.pack(side="left", padx=8)

        # Progress
        row6 = ttk.Frame(frm_top)
        row6.pack(side="top", fill="x", pady=(6,4))
        self.prog = ttk.Progressbar(row6, orient="horizontal", mode="determinate", length=300, maximum=1000)
        self.prog.pack(side="left")
        self.lbl_prog = ttk.Label(row6, text="等待中…")
        self.lbl_prog.pack(side="left", padx=8)

        # Log area (append-only, with scrollbar)
        frm_log = ttk.Frame(self.root, padding=4)
        frm_log.pack(side="top", fill="both", expand=True)
        self.txt = tk.Text(frm_log, wrap="word", height=20, background="#111", foreground="#ddd", insertbackground="#fff")
        self.txt.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(frm_log, orient="vertical", command=self.txt.yview)
        sb.pack(side="right", fill="y")
        self.txt.configure(yscrollcommand=sb.set)

        # color tags
        self.txt.tag_configure("INFO", foreground="#a0d8ff")
        self.txt.tag_configure("WARN", foreground="#ffd479")
        self.txt.tag_configure("ERROR", foreground="#ff8080")
        self.txt.tag_configure("OK", foreground="#8fff8f")
        self.txt.tag_configure("PATH", foreground="#a8ffa8")
        self.txt.tag_configure("H1", foreground="#fff", font=("Consolas", 10, "bold"))

    # ============ Menu handlers =============
    def pick_excel(self):
        p = filedialog.askopenfilename(title="选择 Excel 文件", filetypes=[("Excel", "*.xlsx;*.xls")])
        if p:
            self.excel_var.set(p)

    def pick_glossary(self):
        p = filedialog.askopenfilename(title="选择 术语表 JSON", filetypes=[("JSON", "*.json")])
        if p:
            self.glossary_var.set(p)

    def open_output(self):
        if not self.last_output_path:
            messagebox.showinfo("提示", "还没有输出文件。")
            return
        try:
            if sys.platform.startswith("win"):
                os.startfile(self.last_output_path)  # type: ignore
            else:
                subprocess.Popen(["xdg-open", self.last_output_path])
        except Exception as e:
            messagebox.showerror("错误", f"无法打开：{e}")

    def open_readme(self):
        p = Path("README.md")
        if not p.exists():
            messagebox.showinfo("提示", "项目根目录未找到 README.md")
            return
        try:
            if sys.platform.startswith("win"):
                os.startfile(str(p))  # type: ignore
            else:
                subprocess.Popen(["xdg-open", str(p)])
        except Exception as e:
            messagebox.showerror("错误", f"无法打开 README：{e}")

    # ============ Run logic =============
    def on_run(self):
        if self.runner.running():
            return
        excel = self.excel_var.get().strip()
        glossary = self.glossary_var.get().strip()
        if not excel:
            messagebox.showwarning("提示", "请选择 Excel。")
            return
        if not Path(excel).exists():
            messagebox.showwarning("提示", f"Excel 不存在：{excel}")
            return
        if glossary and (not Path(glossary).exists()):
            messagebox.showwarning("提示", f"术语表不存在：{glossary}")
            return

        self.txt_mark_h1("开始运行流水线…\n")
        self._set_running(True)
        self.progress_total = 0
        self.progress_pct = 0
        self._update_progress(0.0, "准备中…")

        cmds = []

        # Step 1: segmentation
        cmds.append(("Step 1/2", [
            PYTHON_EXE, "-u", "-m", "scripts.05_segment_context",
            "--excel", excel,
            "--sheet-index", str(self.sheet_idx_var.get())
        ], None))

        # Step 2: translate
        translate_cmd = [
            PYTHON_EXE, "-u", "-m", "scripts.12_llm_translate",
            "--excel", excel,
            "--target-lang", self.lang_var.get()
        ]
        if glossary:
            translate_cmd += ["--glossary", glossary]
        if self.overwrite_var.get():
            translate_cmd += ["--overwrite"]
        if self.row_range_var.get().strip():
            translate_cmd += ["--row-range", self.row_range_var.get().strip()]
        if self.speakers_var.get().strip():
            translate_cmd += ["--speakers", self.speakers_var.get().strip()]
        if self.scene_range_var.get().strip():
            translate_cmd += ["--scene-range", self.scene_range_var.get().strip()]

        cmds.append(("Step 2/2", translate_cmd, None))

        # post steps (optional)
        # 顺序：术语统一 -> 风格适配 -> QA
        if self.do_terms_var.get():
            if Path("scripts/20_enforce_terms.py").exists():
                cmds.append(("Post: Terms", [PYTHON_EXE, "-u", "-m", "scripts.20_enforce_terms",
                                             "--excel", excel,
                                             "--glossary", glossary], None))
            else:
                self.append_log("[WARN] 术语统一脚本缺失（scripts/20_enforce_terms.py），已跳过。\n")
        if self.do_style_var.get():
            if Path("scripts/30_style_adapt.py").exists():
                cmds.append(("Post: Style", [PYTHON_EXE, "-u", "-m", "scripts.30_style_adapt",
                                             "--excel", excel], None))
            else:
                self.append_log("[WARN] 风格适配脚本缺失（scripts/30_style_adapt.py），已跳过。\n")
        if self.do_qa_var.get():
            if Path("scripts/25_qa_check.py").exists():
                cmds.append(("Post: QA", [PYTHON_EXE, "-u", "-m", "scripts.25_qa_check",
                                          "--excel", excel], None))
            else:
                self.append_log("[WARN] QA 脚本缺失（scripts/25_qa_check.py），已跳过。\n")

        self.runner.run(cmds)

    def on_dry_run(self):
        if self.runner.running():
            return
        excel = self.excel_var.get().strip()
        glossary = self.glossary_var.get().strip()
        if not excel:
            messagebox.showwarning("提示", "请选择 Excel。")
            return
        if not Path(excel).exists():
            messagebox.showwarning("提示", f"Excel 不存在：{excel}")
            return

        self.txt_mark_h1("Dry run…\n")
        self._set_running(True)
        self._update_progress(0.0, "准备中…")

        translate_cmd = [
            PYTHON_EXE, "-u", "-m", "scripts.12_llm_translate",
            "--excel", excel,
            "--target-lang", self.lang_var.get(),
            "--dry-run"
        ]
        if glossary and Path(glossary).exists():
            translate_cmd += ["--glossary", glossary]
        if self.overwrite_var.get():
            translate_cmd += ["--overwrite"]
        if self.row_range_var.get().strip():
            translate_cmd += ["--row-range", self.row_range_var.get().strip()]
        if self.speakers_var.get().strip():
            translate_cmd += ["--speakers", self.speakers_var.get().strip()]
        if self.scene_range_var.get().strip():
            translate_cmd += ["--scene-range", self.scene_range_var.get().strip()]

        cmds = [("Dry Run", translate_cmd, None)]
        self.runner.run(cmds)

    def on_stop(self):
        self.runner.stop()
        self.append_log("[WARN] 请求停止…\n")

    # ============ logging / progress =============
    def append_log(self, text: str):
        # do not clear, append-only
        ts = time.strftime("[%H:%M:%S] ") if self.show_time.get() else ""
        # class tags by prefix
        tag = None
        if text.startswith("[ERROR]"):
            tag = "ERROR"
        elif text.startswith("[WARN]"):
            tag = "WARN"
        elif text.startswith("[OK]"):
            tag = "OK"
        elif text.startswith("[INFO]"):
            tag = "INFO"
        else:
            tag = None

        self.txt.insert("end", ts + text, tag)
        self.txt.see("end")

        # detect output path
        m = re.search(r"Output\s*->\s*(.+)$", text.strip())
        if m:
            outp = m.group(1).strip()
            self.last_output_path = outp
            self.btn_open.configure(state=tk.NORMAL)

    def txt_mark_h1(self, text):
        ts = time.strftime("[%H:%M:%S] ") if self.show_time.get() else ""
        self.txt.insert("end", ts + text, "H1")
        self.txt.see("end")

    def _parse_line(self, line: str):
        # progress from 12_llm_translate: "[PROGRESS] q=... (xx.x%)"
        m = re.search(r"\(([0-9]+(?:\.[0-9]+)?)%\)", line)
        if m:
            pct = float(m.group(1))
            self._update_progress(pct, f"翻译进度 {pct:.1f}%")
        if "Scenes saved to" in line:
            self._update_progress(0.0, "已完成场景切分…")

    def _update_progress(self, pct: float, text: str):
        pct = max(0.0, min(100.0, pct))
        self.prog.configure(value=int(pct*10))
        self.lbl_prog.configure(text=text)

    def _on_done(self, rc):
        if rc == 0:
            self.append_log("[OK] 全部完成。\n")
        else:
            self.append_log(f"[ERROR] 结束，返回码 {rc}\n")
        self._set_running(False)

    def _set_running(self, running: bool):
        self.btn_run.configure(state=tk.DISABLED if running else tk.NORMAL)
        self.btn_stop.configure(state=tk.NORMAL if running else tk.DISABLED)

def main():
    root = tk.Tk()
    App(root)
    root.mainloop()

if __name__ == "__main__":
    main()
