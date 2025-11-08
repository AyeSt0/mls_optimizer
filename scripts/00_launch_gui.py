
from pathlib import Path
import os, sys, json, re, subprocess, threading, time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

APP_ROOT = Path(__file__).resolve().parent.parent
CFG_DIR  = APP_ROOT / "config"
ART_DIR  = APP_ROOT / "artifacts"
DATA_DIR = APP_ROOT / "data"
RECENT_FILE = ART_DIR / "ui_recent.json"
SETTINGS_FILE = CFG_DIR / "settings.local.yaml"

I18N = {
    "zh": {
        "app_title": "MLS 翻译助手 · GUI",
        "file": "文件",
        "recent": "最近打开",
        "recent_excel": "最近 Excel",
        "recent_glossary": "最近 术语表",
        "config": "配置",
        "provider": "API 提供商设置",
        "view": "视图",
        "log_level": "日志级别",
        "help": "帮助",
        "open_readme": "打开 README",
        "open_issues": "打开 Issues",
        "excel": "Excel 文件",
        "glossary": "术语表 JSON",
        "browse": "浏览",
        "target_lang": "目标语言",
        "provider_lbl": "默认提供商",
        "run": "运行流水线",
        "stop": "停止",
        "open_artifacts": "打开 artifacts",
        "open_output": "打开输出",
        "log": "日志",
        "preview": "预览/说明",
        "advanced": "显示高级选项",
        "save": "保存",
        "cancel": "取消",
        "provider_title": "编辑 API 配置",
        "provider_type": "提供商",
        "api_key": "API Key",
        "base_url": "Base URL",
        "model": "模型名",
        "ok": "确定",
        "level_all": "全部",
        "level_info": "信息",
        "level_warn": "警告",
        "level_err": "错误",
        "seg_first": "（自动）步骤1：场景切分",
        "trans_second": "（自动）步骤2：大模型翻译",
        "select_excel": "选择 Excel 文件",
        "select_glossary": "选择术语表 JSON",
        "restart_needed": "部分修改需重启运行生效。",
        "lang_toggle": "EN/中文",
        "adv_title": "高级选项",
        "workers": "并发数",
        "rpm": "RPM",
        "tpm": "TPM 上限",
        "flag_show": "显示逐行日志（--show-lines）",
        "flag_resume": "断点续传（--resume）",
    },
    "en": {
        "app_title": "MLS Translator · GUI",
        "file": "File",
        "recent": "Recent",
        "recent_excel": "Recent Excels",
        "recent_glossary": "Recent Glossaries",
        "config": "Config",
        "provider": "Provider Settings",
        "view": "View",
        "log_level": "Log Level",
        "help": "Help",
        "open_readme": "Open README",
        "open_issues": "Open Issues",
        "excel": "Excel",
        "glossary": "Glossary JSON",
        "browse": "Browse",
        "target_lang": "Target language",
        "provider_lbl": "Default Provider",
        "run": "Run",
        "stop": "Stop",
        "open_artifacts": "Open artifacts",
        "open_output": "Open output",
        "log": "Log",
        "preview": "Preview/Notes",
        "advanced": "Show advanced options",
        "save": "Save",
        "cancel": "Cancel",
        "provider_title": "Edit API Settings",
        "provider_type": "Provider",
        "api_key": "API Key",
        "base_url": "Base URL",
        "model": "Model",
        "ok": "OK",
        "level_all": "ALL",
        "level_info": "INFO",
        "level_warn": "WARN",
        "level_err": "ERROR",
        "seg_first": "(Auto) Step 1: Scene segmentation",
        "trans_second": "(Auto) Step 2: LLM translation",
        "select_excel": "Select Excel",
        "select_glossary": "Select Glossary JSON",
        "restart_needed": "Some changes may need restart to take effect.",
        "lang_toggle": "EN/中文",
        "adv_title": "Advanced",
        "workers": "workers",
        "rpm": "rpm",
        "tpm": "tpm-max",
        "flag_show": "Show lines (--show-lines)",
        "flag_resume": "Resume (--resume)",
    }
}

LANG_CHOICES = [
    ("Chinese (Simplified) 简体中文", "zh-CN"),
    ("Chinese (Traditional) 繁體中文", "zh-TW"),
    ("English 英语", "en"),
    ("Japanese 日本語", "ja"),
    ("Korean 한국어", "ko"),
    ("Russian Русский", "ru"),
    ("Spanish Español", "es"),
    ("German Deutsch", "de"),
    ("French Français", "fr"),
    ("Italian Italiano", "it"),
    ("Portuguese (Brazil) Português (BR)", "pt-BR"),
    ("Portuguese (Portugal) Português (EU)", "pt-PT"),
    ("Thai ไทย", "th"),
    ("Vietnamese Tiếng Việt", "vi"),
]

def read_text(path: Path) -> str:
    try:
        return path.read_text("utf-8")
    except Exception:
        return ""

def write_text(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")

def load_recent() -> dict:
    if RECENT_FILE.exists():
        try:
            return json.loads(read_text(RECENT_FILE)) or {}
        except Exception:
            return {}
    return {}

def save_recent(d: dict):
    try:
        write_text(RECENT_FILE, json.dumps(d, ensure_ascii=False, indent=2))
    except Exception:
        pass

def open_folder(p: Path):
    try:
        if os.name == "nt":
            os.startfile(p)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", p])
        else:
            subprocess.Popen(["xdg-open", p])
    except Exception as e:
        messagebox.showerror("Error", str(e))

class ProcRunner:
    def __init__(self, log_cb, done_cb):
        self._proc = None
        self._thr = None
        self.log_cb = log_cb
        self.done_cb = done_cb

    def run(self, cmd, cwd):
        def _work():
            try:
                p = subprocess.Popen(
                    cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, bufsize=1, universal_newlines=True
                )
                self._proc = p
                for line in p.stdout:
                    self.log_cb(line.rstrip("\n"))
                rc = p.wait()
                self.done_cb(rc)
            except Exception as e:
                self.log_cb(f"[ERROR] {e}")
                self.done_cb(1)
        self._thr = threading.Thread(target=_work, daemon=True)
        self._thr.start()

    def stop(self):
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.terminate()
            except Exception:
                pass

class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.lang = "zh"
        self.recent = load_recent()
        self.last_output = None
        self.proc = None

        self.root.title(I18N[self.lang]["app_title"])
        self.root.geometry("1080x740")
        self.root.minsize(900, 620)
        for i in range(3):
            self.root.grid_columnconfigure(i, weight=1)
        self.root.grid_rowconfigure(3, weight=1)

        # state vars (persist across rebuilds)
        self.var_excel = tk.StringVar(value=str((DATA_DIR/"MLS Chinese.xlsx").resolve()))
        self.var_gloss = tk.StringVar(value=str((DATA_DIR/"name_map.json").resolve()))
        self.var_lang  = tk.StringVar(value="zh-CN")
        self.var_provider = tk.StringVar(value="deepseek")
        self.var_adv = tk.BooleanVar(value=True)
        self.var_workers = tk.StringVar(value="16")
        self.var_rpm = tk.StringVar(value="400")
        self.var_tpm = tk.StringVar(value="100000")
        self.var_show = tk.BooleanVar(value=False)
        self.var_resume = tk.BooleanVar(value=True)
        self.log_level = tk.StringVar(value="ALL")

        # build full UI
        self._build_all()

    # ---------- builders ----------
    def _build_all(self):
        for w in self.root.grid_slaves():
            w.destroy()
        self._build_menubar()
        self._build_toolbar()
        self._build_tabs()
        self._init_log_tags()
        self._place_lang_button()

    def _build_menubar(self):
        self.menubar = tk.Menu(self.root)
        self.root.config(menu=self.menubar)

        t = I18N[self.lang]
        # File
        self.file_menu = tk.Menu(self.menubar, tearoff=0)
        self.menubar.add_cascade(label=t["file"], menu=self.file_menu)
        self.recent_excel_menu = tk.Menu(self.file_menu, tearoff=0)
        self.recent_gloss_menu = tk.Menu(self.file_menu, tearoff=0)
        self.file_menu.add_cascade(label=t["recent_excel"], menu=self.recent_excel_menu)
        self.file_menu.add_cascade(label=t["recent_glossary"], menu=self.recent_gloss_menu)
        self.file_menu.add_separator()
        self.file_menu.add_command(label=t["open_artifacts"], command=lambda: open_folder(ART_DIR))
        self._refresh_recent_menus()

        # Config
        self.cfg_menu = tk.Menu(self.menubar, tearoff=0)
        self.menubar.add_cascade(label=t["config"], menu=self.cfg_menu)
        self.cfg_menu.add_command(label=t["provider"], command=self._open_provider_dialog)

        # View
        self.view_menu = tk.Menu(self.menubar, tearoff=0)
        self.menubar.add_cascade(label=t["view"], menu=self.view_menu)
        self.view_menu.add_radiobutton(label=t["level_all"], variable=self.log_level, value="ALL", command=self._apply_log_filter)
        self.view_menu.add_radiobutton(label=t["level_info"], variable=self.log_level, value="INFO", command=self._apply_log_filter)
        self.view_menu.add_radiobutton(label=t["level_warn"], variable=self.log_level, value="WARN", command=self._apply_log_filter)
        self.view_menu.add_radiobutton(label=t["level_err"], variable=self.log_level, value="ERROR", command=self._apply_log_filter)

        # Help
        self.help_menu = tk.Menu(self.menubar, tearoff=0)
        self.menubar.add_cascade(label=t["help"], menu=self.help_menu)
        self.help_menu.add_command(label=t["open_readme"], command=self._open_readme)
        self.help_menu.add_command(label=t["open_issues"], command=self._open_issues)

        # language toggle hotkey
        self.root.bind("<F12>", lambda e: self._toggle_lang())

    def _build_toolbar(self):
        t = I18N[self.lang]
        frm = ttk.Frame(self.root)
        frm.grid(row=0, column=0, columnspan=3, sticky="ew", padx=8, pady=6)
        for i in range(10):
            frm.grid_columnconfigure(i, weight=1)

        ttk.Label(frm, text=t["excel"]).grid(row=0, column=0, sticky="w")
        e1 = ttk.Entry(frm, textvariable=self.var_excel)
        e1.grid(row=0, column=1, columnspan=6, sticky="ew", padx=4)
        ttk.Button(frm, text=t["browse"], command=self._pick_excel).grid(row=0, column=7, sticky="ew")

        ttk.Label(frm, text=t["glossary"]).grid(row=1, column=0, sticky="w")
        e2 = ttk.Entry(frm, textvariable=self.var_gloss)
        e2.grid(row=1, column=1, columnspan=6, sticky="ew", padx=4)
        ttk.Button(frm, text=t["browse"], command=self._pick_glossary).grid(row=1, column=7, sticky="ew")

        ttk.Label(frm, text=t["target_lang"]).grid(row=0, column=8, sticky="e")
        self.combo_lang = ttk.Combobox(frm, state="readonly",
                                       values=[f"{name} | {code}" for name,code in LANG_CHOICES])
        self.combo_lang.grid(row=0, column=9, sticky="ew")
        # set & bind
        try:
            label = next(lbl for lbl, code in LANG_CHOICES if code == self.var_lang.get())
        except StopIteration:
            label = LANG_CHOICES[0][0]
            self.var_lang.set(LANG_CHOICES[0][1])
        self.combo_lang.set(f"{label} | {self.var_lang.get()}")
        self.combo_lang.bind("<<ComboboxSelected>>", lambda e: self.var_lang.set(self.combo_lang.get().split("|")[-1].strip()))

        ttk.Label(frm, text=t["provider_lbl"]).grid(row=1, column=8, sticky="e")
        self.combo_provider = ttk.Combobox(frm, state="readonly", values=["deepseek","openai"])
        self.combo_provider.grid(row=1, column=9, sticky="ew")
        self.combo_provider.set(self.var_provider.get())
        self.combo_provider.bind("<<ComboboxSelected>>", lambda e: self.var_provider.set(self.combo_provider.get()))

        bar = ttk.Frame(self.root)
        bar.grid(row=1, column=0, columnspan=3, sticky="ew", padx=8)
        for i in range(6):
            bar.grid_columnconfigure(i, weight=1)

        self.btn_run = ttk.Button(bar, text=t["run"], command=self._run_pipeline)
        self.btn_stop = ttk.Button(bar, text=t["stop"], command=self._stop_pipeline, state=tk.DISABLED)
        self.btn_art = ttk.Button(bar, text=t["open_artifacts"], command=lambda: open_folder(ART_DIR))
        self.btn_open = ttk.Button(bar, text=t["open_output"], command=self._open_output, state=tk.DISABLED)

        self.btn_run.grid(row=0, column=0, sticky="w", padx=2, pady=4)
        self.btn_stop.grid(row=0, column=1, sticky="w", padx=2, pady=4)
        self.btn_art.grid(row=0, column=2, sticky="w", padx=2, pady=4)
        self.btn_open.grid(row=0, column=3, sticky="w", padx=2, pady=4)

        self.chk_adv = ttk.Checkbutton(bar, text=t["advanced"],
                                       variable=self.var_adv, command=self._toggle_advanced)
        self.chk_adv.grid(row=0, column=5, sticky="e", padx=2)

        # progress
        self.pbar = ttk.Progressbar(bar, mode="indeterminate")
        self.pbar.grid(row=0, column=4, sticky="ew", padx=4, pady=4)

        # Advanced pane
        self.adv = ttk.Labelframe(self.root, text=t["adv_title"])
        self.adv.grid(row=2, column=0, columnspan=3, sticky="nsew", padx=8, pady=4)
        for i in range(8):
            self.adv.grid_columnconfigure(i, weight=1)

        ttk.Label(self.adv, text=t["workers"]).grid(row=0, column=0, sticky="e")
        ttk.Entry(self.adv, textvariable=self.var_workers, width=8).grid(row=0, column=1, sticky="w")
        ttk.Label(self.adv, text=t["rpm"]).grid(row=0, column=2, sticky="e")
        ttk.Entry(self.adv, textvariable=self.var_rpm, width=8).grid(row=0, column=3, sticky="w")
        ttk.Label(self.adv, text=t["tpm"]).grid(row=0, column=4, sticky="e")
        ttk.Entry(self.adv, textvariable=self.var_tpm, width=10).grid(row=0, column=5, sticky="w")
        ttk.Checkbutton(self.adv, text=t["flag_show"], variable=self.var_show).grid(row=0, column=6, sticky="w")
        ttk.Checkbutton(self.adv, text=t["flag_resume"], variable=self.var_resume).grid(row=0, column=7, sticky="w")

        if not self.var_adv.get():
            self.adv.grid_remove()

    def _build_tabs(self):
        t = I18N[self.lang]
        self.nb = ttk.Notebook(self.root)
        self.nb.grid(row=3, column=0, columnspan=3, sticky="nsew", padx=8, pady=(0,8))
        self.root.grid_rowconfigure(3, weight=1)

        self.tab_log = ttk.Frame(self.nb)
        self.nb.add(self.tab_log, text=t["log"])

        self.txt = tk.Text(self.tab_log, wrap="word", bg="#111", fg="#ddd", insertbackground="#fff")
        self.txt.pack(fill="both", expand=True)
        self.txt.configure(state="disabled")

        self.tab_prev = ttk.Frame(self.nb)
        self.nb.add(self.tab_prev, text=t["preview"])

        prev_label = tk.Text(self.tab_prev, height=10, wrap="word", bg="#181818", fg="#d4d4d4", insertbackground="#fff")
        prev_label.pack(fill="both", expand=True, padx=8, pady=8)
        prev_label.insert("end",
            "· 本工具会自动执行：\n"
            "  1) 场景切分  2) 大模型翻译（仅翻译第5列空单元格）\n"
            "· 术语表采用最长匹配优先\n"
            "· string speaker 的校内地点会按“教室/办公室/礼堂”等自然表达\n"
            "· 占位符/品牌名原样保留\n"
        )
        prev_label.configure(state="disabled")

    def _init_log_tags(self):
        self.txt.tag_configure("OK", foreground="#16C60C")
        self.txt.tag_configure("WARN", foreground="#CCA700")
        self.txt.tag_configure("ERROR", foreground="#E74856")
        self.txt.tag_configure("CFG", foreground="#11A8CD")
        self.txt.tag_configure("BOLD", font=("Consolas", 10, "bold"))
        self._apply_log_filter()

    # ---------- helpers ----------
    def _place_lang_button(self):
        btn = getattr(self, "lang_btn", None)
        if btn is None:
            self.lang_btn = ttk.Button(self.root, text=I18N[self.lang]["lang_toggle"], command=self._toggle_lang)
        else:
            self.lang_btn.configure(text=I18N[self.lang]["lang_toggle"])
        self.lang_btn.place(relx=1.0, rely=0.0, x=-120, y=2, anchor="ne", width=110, height=26)

    def _add_recent(self, kind: str, path: str):
        d = self.recent
        arr = d.get(kind, [])
        path = str(Path(path))
        if path in arr:
            arr.remove(path)
        arr.insert(0, path)
        d[kind] = arr[:10]
        save_recent(d)
        self._refresh_recent_menus()

    def _refresh_recent_menus(self):
        self.recent_excel_menu.delete(0, "end")
        for p in self.recent.get("excel", []):
            self.recent_excel_menu.add_command(label=p, command=lambda x=p: self.var_excel.set(x))
        self.recent_gloss_menu.delete(0, "end")
        for p in self.recent.get("glossary", []):
            self.recent_gloss_menu.add_command(label=p, command=lambda x=p: self.var_gloss.set(x))

    # ---------- dialogs ----------
    def _open_provider_dialog(self):
        t = I18N[self.lang]
        win = tk.Toplevel(self.root)
        win.title(t["provider_title"])
        win.geometry("520x240")
        win.transient(self.root)
        win.grab_set()

        provider = tk.StringVar(value=self.var_provider.get())
        api_key  = tk.StringVar(value="")
        base_url = tk.StringVar(value="")
        model    = tk.StringVar(value="")

        frm = ttk.Frame(win, padding=10)
        frm.pack(fill="both", expand=True)

        ttk.Label(frm, text=t["provider_type"]).grid(row=0, column=0, sticky="e")
        cb = ttk.Combobox(frm, values=["deepseek","openai"], state="readonly", textvariable=provider)
        cb.grid(row=0, column=1, sticky="w", padx=6)

        ttk.Label(frm, text=t["api_key"]).grid(row=1, column=0, sticky="e")
        ttk.Entry(frm, textvariable=api_key, show="*").grid(row=1, column=1, sticky="ew", padx=6)

        ttk.Label(frm, text=t["base_url"]).grid(row=2, column=0, sticky="e")
        ttk.Entry(frm, textvariable=base_url).grid(row=2, column=1, sticky="ew", padx=6)

        ttk.Label(frm, text=t["model"]).grid(row=3, column=0, sticky="e")
        ttk.Entry(frm, textvariable=model).grid(row=3, column=1, sticky="ew", padx=6)

        frm.grid_columnconfigure(1, weight=1)

        def save_cfg():
            prov = provider.get()
            self.var_provider.set(prov)
            self.combo_provider.set(prov)
            if prov == "deepseek":
                text = (
                    "provider: deepseek\n\n"
                    "llm:\n"
                    "  deepseek:\n"
                    f"    api_key: \"{api_key.get()}\"\n"
                    f"    base_url: \"{base_url.get() or 'https://api.siliconflow.cn/v1'}\"\n"
                    f"    name: \"{model.get() or 'deepseek-ai/DeepSeek-V3.2-Exp'}\"\n"
                    "  openai:\n"
                    "    api_key: \"\"\n"
                    "    base_url: \"https://api.openai.com/v1\"\n"
                    "    name: \"gpt-4o-mini\"\n"
                )
            else:
                text = (
                    "provider: openai\n\n"
                    "llm:\n"
                    "  deepseek:\n"
                    "    api_key: \"\"\n"
                    "    base_url: \"https://api.siliconflow.cn/v1\"\n"
                    "    name: \"deepseek-ai/DeepSeek-V3.2-Exp\"\n"
                    "  openai:\n"
                    f"    api_key: \"{api_key.get()}\"\n"
                    f"    base_url: \"{base_url.get() or 'https://api.openai.com/v1'}\"\n"
                    f"    name: \"{model.get() or 'gpt-4o-mini'}\"\n"
                )
            SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
            SETTINGS_FILE.write_text(text, encoding="utf-8")
            messagebox.showinfo("OK", I18N[self.lang]["restart_needed"])
            win.destroy()

        btnf = ttk.Frame(win)
        btnf.pack(fill="x", padx=10, pady=6)
        ttk.Button(btnf, text=t["ok"], command=save_cfg).pack(side="right")

    # ---------- actions ----------
    def _pick_excel(self):
        t = I18N[self.lang]
        p = filedialog.askopenfilename(
            title=t["select_excel"],
            filetypes=[("Excel","*.xlsx *.xls"), ("All","*.*")],
            initialdir=str(DATA_DIR)
        )
        if p:
            self.var_excel.set(p)
            self._add_recent("excel", p)

    def _pick_glossary(self):
        t = I18N[self.lang]
        p = filedialog.askopenfilename(
            title=t["select_glossary"],
            filetypes=[("JSON","*.json"), ("All","*.*")],
            initialdir=str(DATA_DIR)
        )
        if p:
            self.var_gloss.set(p)
            self._add_recent("glossary", p)

    def _append_log(self, line: str):
        lvl = self.log_level.get()
        if lvl != "ALL":
            if lvl == "INFO" and (("[WARN]" in line) or ("[ERROR]" in line)):
                return
            if lvl == "WARN" and ("[ERROR]" in line):
                return
            if lvl == "ERROR" and ("[ERROR]" not in line):
                return

        self.txt.configure(state="normal")
        tag = None
        if "[OK]" in line: tag = "OK"
        elif "[WARN]" in line: tag = "WARN"
        elif "[ERROR]" in line or "Traceback" in line: tag = "ERROR"
        elif "[CFG]" in line: tag = "CFG"

        self.txt.insert("end", line + "\n", tag)
        for kw in ["RU:", "EN:", "OUT:", "Output ->"]:
            idx = "1.0"
            while True:
                idx = self.txt.search(kw, idx, stopindex="end")
                if not idx: break
                self.txt.tag_add("BOLD", idx, f"{idx}+{len(kw)}c")
                idx = f"{idx}+1c"
        self.txt.see("end")
        self.txt.configure(state="disabled")

        m = re.search(r"Output\s*->\s*(.+)$", line)
        if m:
            self.last_output = m.group(1).strip()
            self.btn_open.config(state=tk.NORMAL)

    def _run_pipeline(self):
        # reset log
        self.txt.configure(state="normal"); self.txt.delete("1.0","end"); self.txt.configure(state="disabled")
        self.btn_run.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        self.btn_open.config(state=tk.DISABLED)
        self.pbar.start(10)

        excel = self.var_excel.get().strip('"')
        gloss = self.var_gloss.get().strip('"')
        lang_code = self.var_lang.get() or "zh-CN"

        cmd1 = [sys.executable, "-u", "-m", "scripts.05_segment_context", "--excel", excel]
        cmd2 = [
            sys.executable, "-u", "-m", "scripts.12_llm_translate",
            "--excel", excel, "--target-lang", lang_code, "--glossary", gloss,
            "--rpm", self.var_rpm.get(), "--tpm-max", self.var_tpm.get(),
            "--workers", self.var_workers.get(), "--auto-tune"
        ]
        if self.var_resume.get():
            cmd2.append("--resume")
        if self.var_show.get():
            cmd2.append("--show-lines")

        def _run_all():
            self._append_log("== Step 1/2 =="); self._append_log(" ".join(cmd1))
            pr = ProcRunner(self._append_log, lambda rc: None); pr.run(cmd1, cwd=str(APP_ROOT))
            while pr._thr.is_alive(): time.sleep(0.1)
            self._append_log("== Step 2/2 =="); self._append_log(" ".join(cmd2))
            self.proc = ProcRunner(self._append_log, self._on_done); self.proc.run(cmd2, cwd=str(APP_ROOT))

        threading.Thread(target=_run_all, daemon=True).start()

    def _stop_pipeline(self):
        if self.proc:
            self.proc.stop()
        self.pbar.stop()
        self.btn_run.config(state=tk.NORMAL)
        self.btn_stop.config(state=tk.DISABLED)

    def _on_done(self, rc: int):
        self.pbar.stop()
        self.btn_run.config(state=tk.NORMAL)
        self.btn_stop.config(state=tk.DISABLED)
        if rc == 0:
            self._append_log("[OK] Step finished.")
        else:
            self._append_log("[ERROR] step failed: rc={}".format(rc))

    def _open_output(self):
        if self.last_output and Path(self.last_output).exists():
            try:
                os.startfile(self.last_output) if os.name == "nt" else subprocess.Popen(["open" if sys.platform=="darwin" else "xdg-open", self.last_output])
            except Exception as e:
                messagebox.showerror("Error", str(e))
        else:
            open_folder(DATA_DIR)

    def _toggle_advanced(self):
        if self.var_adv.get():
            self.adv.grid()
        else:
            self.adv.grid_remove()

    def _apply_log_filter(self):
        # filtering happens on insert; here we could re-render if needed
        pass

    def _open_readme(self):
        p = APP_ROOT / "README.md"
        if p.exists():
            os.startfile(p) if os.name == "nt" else subprocess.Popen(["open" if sys.platform=="darwin" else "xdg-open", p])
        else:
            messagebox.showinfo("README", "README.md not found.")

    def _open_issues(self):
        try:
            import webbrowser
            webbrowser.open("https://github.com/")
        except Exception:
            pass

    def _toggle_lang(self):
        # keep current values; rebuild all widgets with new language
        self.lang = "en" if self.lang == "zh" else "zh"
        self.root.title(I18N[self.lang]["app_title"])
        self._build_all()

def main():
    root = tk.Tk()
    App(root)
    root.mainloop()

if __name__ == "__main__":
    main()
