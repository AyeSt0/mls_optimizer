# -*- coding: utf-8 -*-
"""
scripts/00_launch_gui.py  (GUI v3.3.0)
- File pickers (Excel, Glossary, Output dir)
- Menubar: File / Config / View / Help
- Recent files (Excel/Glossary)
- Inline Advanced panel (RPM, TPM, autosave)
- Provider config dialog (DeepSeek/OpenAI) -> writes config/settings.local.yaml
- Start/Stop with graceful stop.flag (flush & exit)
- Stage & Translate progress bars
- Colored log with level filter + preview (RU/EN/OUT)
- i18n: English / 中文
"""

import os, sys, re, json, time, threading, subprocess, queue, webbrowser
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# ---------- Paths & Defaults ----------
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXCEL = str(ROOT / "data" / "MLS Chinese.xlsx")
DEFAULT_GLOSS = str(ROOT / "data" / "name_map.json")
DEFAULT_OUTDIR = str(ROOT / "artifacts")
CONFIG_DIR = ROOT / "config"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
SETTINGS_LOCAL = CONFIG_DIR / "settings.local.yaml"
GUI_PREFS = CONFIG_DIR / "gui_prefs.json"

# ---------- i18n ----------
I18N = {
    "en": {
        "title": "MLS Optimizer — GUI",
        "file": "File",
        "config": "Config",
        "view": "View",
        "help": "Help",
        "recent": "Recent",
        "open_artifacts": "Open Artifacts Folder",
        "open_config": "Open Config Folder",
        "api_settings": "API Provider Settings…",
        "toggle_adv": "Toggle Advanced Panel",
        "exit": "Exit",
        "log_level": "Log Level",
        "level_all": "ALL",
        "level_info": "INFO",
        "level_warn": "WARN",
        "level_error": "ERROR",
        "auto_scroll": "Auto Scroll",
        "word_wrap": "Word Wrap",
        "lang_ui": "UI Language",
        "lang_en": "English",
        "lang_zh": "中文",
        "open_readme": "Open README",
        "open_issues": "Open Issues",
        "about": "About",
        "excel": "Excel",
        "browse": "Browse…",
        "glossary": "Glossary",
        "outdir": "Output Dir",
        "provider": "Provider",
        "target_lang": "Target Language",
        "start": "Start",
        "stop": "Stop",
        "open_output": "Open Output",
        "stage": "Stage",
        "translate": "Translate",
        "advanced": "Advanced",
        "adv_rpm": "RPM",
        "adv_tpm": "TPM Max",
        "adv_auto_count": "Autosave Every (rows)",
        "adv_auto_secs": "Autosave Every (seconds)",
        "adv_do_seg": "Run scene segmentation before translate",
        "preview_tab": "Preview",
        "log_tab": "Log",
        "provider_panel": "API Provider Settings",
        "deepseek": "DeepSeek (SiliconFlow)",
        "openai": "OpenAI",
        "api_key": "API Key",
        "base_url": "Base URL",
        "model": "Model",
        "save": "Save",
        "cancel": "Cancel",
        "ru": "RU",
        "en": "EN",
        "out": "OUT",
    },
    "zh": {
        "title": "MLS 优化器 — 图形界面",
        "file": "文件",
        "config": "配置",
        "view": "视图",
        "help": "帮助",
        "recent": "最近打开",
        "open_artifacts": "打开 Artifacts 目录",
        "open_config": "打开配置目录",
        "api_settings": "API 提供商设置…",
        "toggle_adv": "显示/收起高级面板",
        "exit": "退出",
        "log_level": "日志级别",
        "level_all": "全部",
        "level_info": "信息",
        "level_warn": "警告",
        "level_error": "错误",
        "auto_scroll": "自动滚动",
        "word_wrap": "自动换行",
        "lang_ui": "界面语言",
        "lang_en": "English",
        "lang_zh": "中文",
        "open_readme": "打开 README",
        "open_issues": "打开 Issues",
        "about": "关于",
        "excel": "Excel 文件",
        "browse": "浏览…",
        "glossary": "术语表",
        "outdir": "输出目录",
        "provider": "API 提供商",
        "target_lang": "目标语言",
        "start": "开始",
        "stop": "停止",
        "open_output": "打开输出",
        "stage": "阶段",
        "translate": "翻译进度",
        "advanced": "高级选项",
        "adv_rpm": "每分钟请求（RPM）",
        "adv_tpm": "最大 Tokens（TPM Max）",
        "adv_auto_count": "自动保存间隔（行）",
        "adv_auto_secs": "自动保存间隔（秒）",
        "adv_do_seg": "翻译前执行场景切分",
        "preview_tab": "预览",
        "log_tab": "日志",
        "provider_panel": "API 提供商设置",
        "deepseek": "DeepSeek（SiliconFlow）",
        "openai": "OpenAI",
        "api_key": "API Key",
        "base_url": "Base URL",
        "model": "模型名",
        "save": "保存",
        "cancel": "取消",
        "ru": "俄文",
        "en": "英文",
        "out": "译文",
    }
}

# ---------- Language Mapping ----------
LANG_CHOICES = [
    ("简体中文 (zh-CN)", "zh-CN"),
    ("繁體中文 (zh-TW)", "zh-TW"),
    ("English (en)", "en"),
    ("日本語 (ja)", "ja"),
    ("한국어 (ko)", "ko"),
    ("Français (fr)", "fr"),
    ("Deutsch (de)", "de"),
    ("Español (es)", "es"),
    ("Русский (ru)", "ru"),
    ("Italiano (it)", "it"),
    ("Português do Brasil (pt-BR)", "pt-BR"),
    ("Tiếng Việt (vi)", "vi"),
    ("ภาษาไทย (th)", "th"),
    ("Bahasa Indonesia (id)", "id"),
    ("हिन्दी (hi)", "hi"),
    ("Türkçe (tr)", "tr"),
    ("العربية (ar)", "ar"),
]

# ---------- Helpers ----------
def open_path(p: Path):
    try:
        if os.name == "nt":
            os.startfile(str(p))  # type: ignore
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(p)])
        else:
            subprocess.Popen(["xdg-open", str(p)])
    except Exception:
        pass

def load_prefs():
    if GUI_PREFS.exists():
        try:
            return json.loads(GUI_PREFS.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}

def save_prefs(d: dict):
    try:
        GUI_PREFS.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass

def ensure_dir(s: str):
    p = Path(s)
    p.mkdir(parents=True, exist_ok=True)
    return p

def read_yaml(path: Path):
    try:
        import yaml
        if not path.exists():
            return {}
        return (yaml.safe_load(path.read_text(encoding="utf-8")) or {})
    except Exception:
        return {}

def write_yaml(path: Path, obj: dict):
    try:
        import yaml
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(obj, allow_unicode=True, sort_keys=False), encoding="utf-8")
    except Exception as e:
        messagebox.showerror("YAML", f"Failed to write YAML: {e}")

# ---------- Runner ----------
class ProcRunner(threading.Thread):
    def __init__(self, cmd_list, cwd, on_line, on_done):
        super().__init__(daemon=True)
        self.cmd_list = cmd_list
        self.cwd = cwd
        self.on_line = on_line
        self.on_done = on_done
        self._p = None
        self._kill = False

    def run(self):
        try:
            self._p = subprocess.Popen(
                self.cmd_list,
                cwd=self.cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True,
            )
            for line in self._p.stdout:  # type: ignore
                if self._kill:
                    break
                self.on_line(line.rstrip("\n"))
            rc = self._p.wait()
        except Exception as e:
            self.on_line(f"[ERROR] {e}")
            rc = -1
        self.on_done(rc)

    def stop(self):
        try:
            if self._p and self._p.poll() is None:
                self._p.terminate()
        except Exception:
            pass

# ---------- App ----------
class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.lang = "zh"  # default UI zh
        self.t = I18N[self.lang]

        self.log_level = tk.StringVar(value="ALL")
        self.auto_scroll = tk.BooleanVar(value=True)
        self.word_wrap = tk.BooleanVar(value=True)

        self.excel_var = tk.StringVar(value=DEFAULT_EXCEL)
        self.gloss_var = tk.StringVar(value=DEFAULT_GLOSS)
        self.outdir_var = tk.StringVar(value=DEFAULT_OUTDIR)
        self.provider_var = tk.StringVar(value="deepseek")
        self.lang_var = tk.StringVar(value="zh-CN")
        self.do_seg = tk.BooleanVar(value=True)
        self.rpm_var = tk.IntVar(value=400)
        self.tpm_var = tk.IntVar(value=100000)
        self.auto_rows = tk.IntVar(value=300)
        self.auto_secs = tk.IntVar(value=90)

        self.last_output = None
        self.stage_total = 2
        self.stage_now = 0
        self.to_translate = None
        self.q_remaining = None

        # load gui prefs
        prefs = load_prefs()
        self._apply_prefs(prefs)

        self._build_menubar()
        self._build_main()
        self._bind_resize()

        self._log_buffer = []
        self._recent_excels = prefs.get("recent_excels", [])
        self._recent_gloss = prefs.get("recent_gloss", [])
        self._refresh_recent_menus()

        self._clear_stop_flag()  # safety

        self.root.title(self.t["title"])

    # ----- Prefs -----
    def _apply_prefs(self, p):
        self.excel_var.set(p.get("excel", self.excel_var.get()))
        self.gloss_var.set(p.get("glossary", self.gloss_var.get()))
        self.outdir_var.set(p.get("outdir", self.outdir_var.get()))
        self.provider_var.set(p.get("provider", self.provider_var.get()))
        self.lang_var.set(p.get("target_lang", self.lang_var.get()))
        self.lang = p.get("ui_lang", self.lang)
        self.t = I18N.get(self.lang, I18N["zh"])

    def _store_prefs(self):
        d = {
            "excel": self.excel_var.get(),
            "glossary": self.gloss_var.get(),
            "outdir": self.outdir_var.get(),
            "provider": self.provider_var.get(),
            "target_lang": self.lang_var.get(),
            "ui_lang": self.lang,
            "recent_excels": self._recent_excels,
            "recent_gloss": self._recent_gloss,
        }
        save_prefs(d)

    # ----- Menubar -----
    def _build_menubar(self):
        self.menubar = tk.Menu(self.root)

        # File
        self.menu_file = tk.Menu(self.menubar, tearoff=0)
        self.menu_file.add_command(label=I18N[self.lang]["open_artifacts"], command=self.open_artifacts)
        self.menu_file.add_command(label=I18N[self.lang]["open_config"], command=self.open_config)
        self.menu_file.add_cascade(label=I18N[self.lang]["recent"], menu=tk.Menu(self.menu_file, tearoff=0), underline=0)
        self.menu_file.add_separator()
        self.menu_file.add_command(label=I18N[self.lang]["exit"], command=self.root.destroy)

        # Config
        self.menu_cfg = tk.Menu(self.menubar, tearoff=0)
        self.menu_cfg.add_command(label=I18N[self.lang]["api_settings"], command=self.open_api_settings)
        self.menu_cfg.add_command(label=I18N[self.lang]["toggle_adv"], command=self.toggle_advanced)

        # View
        self.menu_view = tk.Menu(self.menubar, tearoff=0)
        lv = I18N[self.lang]
        self.menu_view.add_command(label=f'{lv["log_level"]}: {lv["level_all"]}', command=lambda:self.set_log_level("ALL"))
        self.menu_view.add_command(label=f'{lv["log_level"]}: {lv["level_info"]}', command=lambda:self.set_log_level("INFO"))
        self.menu_view.add_command(label=f'{lv["log_level"]}: {lv["level_warn"]}', command=lambda:self.set_log_level("WARN"))
        self.menu_view.add_command(label=f'{lv["log_level"]}: {lv["level_error"]}', command=lambda:self.set_log_level("ERROR"))
        self.menu_view.add_checkbutton(label=I18N[self.lang]["auto_scroll"], variable=self.auto_scroll)
        self.menu_view.add_checkbutton(label=I18N[self.lang]["word_wrap"], variable=self.word_wrap, command=self._update_wrap)

        # Help
        self.menu_help = tk.Menu(self.menubar, tearoff=0)
        self.menu_help.add_command(label=I18N[self.lang]["open_readme"], command=self.open_readme)
        self.menu_help.add_command(label=I18N[self.lang]["open_issues"], command=self.open_issues)
        self.menu_help.add_separator()
        self.menu_help.add_command(label=I18N[self.lang]["about"], command=lambda:messagebox.showinfo("MLS Optimizer", "GUI v3.3.0"))

        self.menubar.add_cascade(label=I18N[self.lang]["file"], menu=self.menu_file)
        self.menubar.add_cascade(label=I18N[self.lang]["config"], menu=self.menu_cfg)
        self.menubar.add_cascade(label=I18N[self.lang]["view"], menu=self.menu_view)
        self.menubar.add_cascade(label=I18N[self.lang]["help"], menu=self.menu_help)

        self.root.config(menu=self.menubar)

    def _refresh_recent_menus(self):
        # rebuild "Recent" submenu
        recent_menu = tk.Menu(self.menu_file, tearoff=0)
        # Excel
        if self._recent_excels:
            recent_menu.add_separator()
            for s in self._recent_excels[:10]:
                recent_menu.add_command(label=f"Excel: {s}", command=lambda x=s:self.excel_var.set(x))
        # Glossary
        if self._recent_gloss:
            recent_menu.add_separator()
            for s in self._recent_gloss[:10]:
                recent_menu.add_command(label=f"Glossary: {s}", command=lambda x=s:self.gloss_var.set(x))
        # attach
        # The "Recent" cascade is at index 2
        self.menu_file.entryconfig(2, menu=recent_menu)

    # ----- Main UI -----
    def _build_main(self):
        t = I18N[self.lang]
        frm = ttk.Frame(self.root, padding=8)
        frm.grid(row=0, column=0, sticky="nsew")
        self.root.rowconfigure(0, weight=1)
        self.root.columnconfigure(0, weight=1)

        # Top pickers
        g = ttk.Frame(frm)
        g.grid(row=0, column=0, sticky="ew", pady=(0,6))
        for i in range(6): g.columnconfigure(i, weight=1)

        ttk.Label(g, text=t["excel"]).grid(row=0, column=0, sticky="w")
        ttk.Entry(g, textvariable=self.excel_var).grid(row=0, column=1, columnspan=4, sticky="ew")
        ttk.Button(g, text=t["browse"], command=self.pick_excel).grid(row=0, column=5, sticky="e")

        ttk.Label(g, text=t["glossary"]).grid(row=1, column=0, sticky="w")
        ttk.Entry(g, textvariable=self.gloss_var).grid(row=1, column=1, columnspan=4, sticky="ew")
        ttk.Button(g, text=t["browse"], command=self.pick_gloss).grid(row=1, column=5, sticky="e")

        ttk.Label(g, text=t["outdir"]).grid(row=2, column=0, sticky="w")
        ttk.Entry(g, textvariable=self.outdir_var).grid(row=2, column=1, columnspan=4, sticky="ew")
        ttk.Button(g, text=t["browse"], command=self.pick_outdir).grid(row=2, column=5, sticky="e")

        ttk.Label(g, text=t["provider"]).grid(row=3, column=0, sticky="w")
        self.cmb_prov = ttk.Combobox(g, textvariable=self.provider_var, values=["deepseek", "openai"], state="readonly", width=18)
        self.cmb_prov.grid(row=3, column=1, sticky="w")
        ttk.Label(g, text=t["target_lang"]).grid(row=3, column=2, sticky="e")
        self.cmb_lang = ttk.Combobox(g, values=[x[0] for x in LANG_CHOICES], state="readonly")
        # set initial
        for disp, code in LANG_CHOICES:
            if code == self.lang_var.get():
                self.cmb_lang.set(disp)
                break
        self.cmb_lang.grid(row=3, column=3, columnspan=2, sticky="ew")

        # Buttons
        btns = ttk.Frame(g)
        btns.grid(row=3, column=5, sticky="e")
        self.btn_start = ttk.Button(btns, text=t["start"], command=self.on_start, width=10)
        self.btn_stop = ttk.Button(btns, text=t["stop"], command=self.on_stop, width=10, state=tk.DISABLED)
        self.btn_open = ttk.Button(btns, text=t["open_output"], command=self.open_last_output, width=12, state=tk.DISABLED)
        self.btn_start.grid(row=0, column=0, padx=2)
        self.btn_stop.grid(row=0, column=1, padx=2)
        self.btn_open.grid(row=0, column=2, padx=2)

        # Advanced panel (collapsible)
        self.adv_frame = ttk.LabelFrame(frm, text=t["advanced"])
        self.adv_visible = True
        self._build_advanced(self.adv_frame, t)
        self.adv_frame.grid(row=1, column=0, sticky="ew", pady=(0,6))

        # Progress bars
        pb = ttk.Frame(frm)
        pb.grid(row=2, column=0, sticky="ew", pady=(0,6))
        pb.columnconfigure(1, weight=1)
        ttk.Label(pb, text=t["stage"]).grid(row=0, column=0, sticky="w")
        self.stage_var = tk.DoubleVar(value=0.0)
        self.pb_stage = ttk.Progressbar(pb, maximum=100, variable=self.stage_var)
        self.pb_stage.grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Label(pb, text=t["translate"]).grid(row=1, column=0, sticky="w")
        self.trans_var = tk.DoubleVar(value=0.0)
        self.pb_trans = ttk.Progressbar(pb, maximum=100, variable=self.trans_var)
        self.pb_trans.grid(row=1, column=1, sticky="ew", padx=6)

        # Notebook: Log / Preview
        nb = ttk.Notebook(frm)
        nb.grid(row=3, column=0, sticky="nsew")
        frm.rowconfigure(3, weight=1)

        # Log tab
        tab_log = ttk.Frame(nb)
        nb.add(tab_log, text=t["log_tab"])
        # toolbar
        tb = ttk.Frame(tab_log)
        tb.pack(side="top", fill="x")
        ttk.Label(tb, text=t["log_level"]+":").pack(side="left")
        ttk.Button(tb, text=self.t["level_all"], command=lambda:self.set_log_level("ALL")).pack(side="left", padx=2)
        ttk.Button(tb, text=self.t["level_info"], command=lambda:self.set_log_level("INFO")).pack(side="left", padx=2)
        ttk.Button(tb, text=self.t["level_warn"], command=lambda:self.set_log_level("WARN")).pack(side="left", padx=2)
        ttk.Button(tb, text=self.t["level_error"], command=lambda:self.set_log_level("ERROR")).pack(side="left", padx=2)
        ttk.Checkbutton(tb, text=t["auto_scroll"], variable=self.auto_scroll).pack(side="left", padx=8)
        ttk.Checkbutton(tb, text=t["word_wrap"], variable=self.word_wrap, command=self._update_wrap).pack(side="left")

        self.txt = tk.Text(tab_log, height=12, bg="#111", fg="#ddd", insertbackground="#fff", wrap="word")
        self.txt.pack(side="left", fill="both", expand=True)
        ysb = ttk.Scrollbar(tab_log, command=self.txt.yview)
        ysb.pack(side="right", fill="y")
        self.txt.configure(yscrollcommand=ysb.set)
        self._init_log_tags()

        # Preview tab
        tab_prev = ttk.Frame(nb)
        nb.add(tab_prev, text=t["preview_tab"])
        tab_prev.columnconfigure(1, weight=1)
        tab_prev.rowconfigure(3, weight=1)

        ttk.Label(tab_prev, text=t["ru"]).grid(row=0, column=0, sticky="nw")
        self.prev_ru = tk.Text(tab_prev, height=4, bg="#1e1e1e", fg="#e0e0b0", insertbackground="#fff", wrap="word")
        self.prev_ru.grid(row=0, column=1, sticky="nsew", padx=6, pady=2)

        ttk.Label(tab_prev, text=t["en"]).grid(row=1, column=0, sticky="nw")
        self.prev_en = tk.Text(tab_prev, height=4, bg="#1e1e1e", fg="#b0e0ff", insertbackground="#fff", wrap="word")
        self.prev_en.grid(row=1, column=1, sticky="nsew", padx=6, pady=2)

        ttk.Label(tab_prev, text=t["out"]).grid(row=2, column=0, sticky="nw")
        self.prev_out = tk.Text(tab_prev, height=4, bg="#1e1e1e", fg="#b0ffb0", insertbackground="#fff", wrap="word")
        self.prev_out.grid(row=2, column=1, sticky="nsew", padx=6, pady=2)

    def _build_advanced(self, parent, t):
        frm = ttk.Frame(parent)
        frm.grid(row=0, column=0, sticky="ew", padx=6, pady=4)
        for i in range(8): frm.columnconfigure(i, weight=1)

        ttk.Label(frm, text=t["adv_rpm"]).grid(row=0, column=0, sticky="w")
        ttk.Entry(frm, width=8, textvariable=self.rpm_var).grid(row=0, column=1, sticky="w")
        ttk.Label(frm, text=t["adv_tpm"]).grid(row=0, column=2, sticky="e")
        ttk.Entry(frm, width=10, textvariable=self.tpm_var).grid(row=0, column=3, sticky="w")
        ttk.Label(frm, text=t["adv_auto_count"]).grid(row=0, column=4, sticky="e")
        ttk.Entry(frm, width=10, textvariable=self.auto_rows).grid(row=0, column=5, sticky="w")
        ttk.Label(frm, text=t["adv_auto_secs"]).grid(row=0, column=6, sticky="e")
        ttk.Entry(frm, width=10, textvariable=self.auto_secs).grid(row=0, column=7, sticky="w")

        ttk.Checkbutton(parent, text=t["adv_do_seg"], variable=self.do_seg).grid(row=1, column=0, sticky="w", padx=6, pady=(0,6))

    def _bind_resize(self):
        self.root.minsize(980, 640)
        self.root.geometry("1080x720")

    # ----- Log -----
    def _init_log_tags(self):
        self.txt.tag_configure("INFO", foreground="#9cdcfe")
        self.txt.tag_configure("WARN", foreground="#f0ad4e")
        self.txt.tag_configure("ERROR", foreground="#ff6b6b")
        self.txt.tag_configure("OK", foreground="#98c379")
        self.txt.tag_configure("PROGRESS", foreground="#56b6c2")
        self.txt.tag_configure("SEND", foreground="#c586c0", font=("Consolas", 10, "bold"))
        self.txt.tag_configure("HEAD", foreground="#d7ba7d", font=("Consolas", 10, "bold"))
        self.txt.tag_configure("PLAIN", foreground="#ddd")

    def _append(self, s: str):
        lvl, tag = self._classify_line(s)
        self._log_buffer.append((lvl, s))

        # level filter
        lv_order = {"ALL":0,"INFO":1,"WARN":2,"ERROR":3}
        cur = lv_order.get(self.log_level.get(), 0)
        ln = {"ERROR":3,"WARN":2,"INFO":1}.get(lvl,1)
        if cur>ln and self.log_level.get()!="ALL":
            return

        self.txt.insert("end", s+"\n", tag)
        if self.auto_scroll.get():
            self.txt.see("end")

        # preview RU/EN/OUT
        if s.startswith("RU: "):
            self._set_prev(self.prev_ru, s[4:])
        elif s.startswith("EN: "):
            self._set_prev(self.prev_en, s[4:])
        elif s.startswith("OUT: "):
            self._set_prev(self.prev_out, s[5:])

        # stage / translate progress
        if "== Step " in s and "==" in s:
            self._parse_stage(s)
        elif s.startswith("[PLAN]"):
            m = re.search(r"to_translate=(\d+)", s)
            if m:
                self.to_translate = int(m.group(1))
                self.q_remaining = self.to_translate
                self._update_trans_bar()
        elif s.startswith("[PROGRESS]"):
            m = re.search(r"q=(\d+)", s)
            if m and self.to_translate is not None:
                self.q_remaining = int(m.group(1))
                self._update_trans_bar()
        elif "Output -> " in s:
            path = s.split("Output ->",1)[1].strip()
            self.last_output = path
            self.btn_open.configure(state=tk.NORMAL)

    def _classify_line(self, s: str):
        if s.startswith("[ERROR]"): return ("ERROR", "ERROR")
        if s.startswith("[WARN]"): return ("WARN", "WARN")
        if s.startswith("[OK]"): return ("INFO", "OK")
        if s.startswith("[SEND]"): return ("INFO", "SEND")
        if s.startswith("[PROGRESS]") or s.startswith("[PLAN]"): return ("INFO", "PROGRESS")
        if s.startswith("== Step "): return ("INFO", "HEAD")
        return ("INFO","PLAIN")

    def _set_prev(self, widget: tk.Text, text: str):
        widget.delete("1.0","end")
        widget.insert("end", text)

    def _parse_stage(self, s: str):
        m = re.search(r"== Step\s+(\d+)/(\d+)\s*==", s)
        if m:
            self.stage_now = int(m.group(1))
            self.stage_total = int(m.group(2))
            pct = 100.0 * (self.stage_now-1)/max(1,self.stage_total)
            self.stage_var.set(pct)
        elif "[OK] Scenes:" in s:
            # after segmentation ends, set stage to first complete
            self.stage_var.set(100.0 * 1/max(1,self.stage_total))

    def _update_trans_bar(self):
        if self.to_translate is None: return
        done = self.to_translate - (self.q_remaining or 0)
        pct = 0.0 if self.to_translate==0 else 100.0 * done / self.to_translate
        self.trans_var.set(max(0.0, min(100.0, pct)))

    def append_log(self, s: str):
        self._append(s)

    def clear_log(self):
        self.txt.delete("1.0","end")
        self._log_buffer.clear()
        self.prev_ru.delete("1.0","end"); self.prev_en.delete("1.0","end"); self.prev_out.delete("1.0","end")

    def set_log_level(self, level: str):
        self.log_level.set(level)
        # re-render
        self.txt.delete("1.0","end")
        for lvl, s in self._log_buffer:
            lv_order = {"ALL":0,"INFO":1,"WARN":2,"ERROR":3}
            cur = lv_order.get(self.log_level.get(), 0)
            ln = {"ERROR":3,"WARN":2,"INFO":1}.get(lvl,1)
            if cur>ln and self.log_level.get()!="ALL":
                continue
            tag = self._classify_line(s)[1]
            self.txt.insert("end", s+"\n", tag)
        if self.auto_scroll.get():
            self.txt.see("end")

    def _update_wrap(self):
        self.txt.configure(wrap="word" if self.word_wrap.get() else "none")

    # ----- Menus actions -----
    def open_artifacts(self):
        open_path(Path(self.outdir_var.get() or DEFAULT_OUTDIR))

    def open_config(self):
        open_path(CONFIG_DIR)

    def open_readme(self):
        p = ROOT / "README.md"
        if p.exists():
            open_path(p)
        else:
            webbrowser.open("https://github.com/")

    def open_issues(self):
        webbrowser.open("https://github.com/")

    # ----- Provider Dialog -----
    def open_api_settings(self):
        t = I18N[self.lang]
        win = tk.Toplevel(self.root)
        win.title(t["provider_panel"])
        win.transient(self.root)
        win.grab_set()
        frm = ttk.Frame(win, padding=12)
        frm.grid(row=0, column=0, sticky="nsew")
        win.columnconfigure(0, weight=1); win.rowconfigure(0, weight=1)

        # DeepSeek
        ttk.Label(frm, text=t["deepseek"]).grid(row=0, column=0, sticky="w", pady=(0,6))
        ttk.Label(frm, text=t["api_key"]).grid(row=1, column=0, sticky="e")
        ds_key = tk.StringVar()
        ttk.Entry(frm, textvariable=ds_key, width=52).grid(row=1, column=1, sticky="ew", pady=2)
        ttk.Label(frm, text=t["base_url"]).grid(row=2, column=0, sticky="e")
        ds_url = tk.StringVar(value="https://api.siliconflow.cn/v1")
        ttk.Entry(frm, textvariable=ds_url, width=52).grid(row=2, column=1, sticky="ew", pady=2)
        ttk.Label(frm, text=t["model"]).grid(row=3, column=0, sticky="e")
        ds_model = tk.StringVar(value="deepseek-ai/DeepSeek-V3.2-Exp")
        ttk.Entry(frm, textvariable=ds_model, width=52).grid(row=3, column=1, sticky="ew", pady=2)

        # OpenAI
        ttk.Separator(frm).grid(row=4, column=0, columnspan=2, sticky="ew", pady=8)
        ttk.Label(frm, text=t["openai"]).grid(row=5, column=0, sticky="w", pady=(0,6))
        ttk.Label(frm, text=t["api_key"]).grid(row=6, column=0, sticky="e")
        oa_key = tk.StringVar()
        ttk.Entry(frm, textvariable=oa_key, width=52).grid(row=6, column=1, sticky="ew", pady=2)
        ttk.Label(frm, text=t["base_url"]).grid(row=7, column=0, sticky="e")
        oa_url = tk.StringVar(value="https://api.openai.com/v1")
        ttk.Entry(frm, textvariable=oa_url, width=52).grid(row=7, column=1, sticky="ew", pady=2)
        ttk.Label(frm, text=t["model"]).grid(row=8, column=0, sticky="e")
        oa_model = tk.StringVar(value="gpt-4o-mini")
        ttk.Entry(frm, textvariable=oa_model, width=52).grid(row=8, column=1, sticky="ew", pady=2)

        # load current YAML if any
        cfg = read_yaml(SETTINGS_LOCAL)
        if cfg:
            prov = cfg.get("provider")
            if prov: self.provider_var.set(prov)
            if (cfg.get("llm") or {}).get("deepseek"):
                ds_key.set(cfg["llm"]["deepseek"].get("api_key",""))
                ds_url.set(cfg["llm"]["deepseek"].get("base_url","https://api.siliconflow.cn/v1"))
            if (cfg.get("model") or {}).get("deepseek"):
                ds_model.set(cfg["model"]["deepseek"].get("name","deepseek-ai/DeepSeek-V3.2-Exp"))
            if (cfg.get("llm") or {}).get("openai"):
                oa_key.set(cfg["llm"]["openai"].get("api_key",""))
                oa_url.set(cfg["llm"]["openai"].get("base_url","https://api.openai.com/v1"))
            if (cfg.get("model") or {}).get("openai"):
                oa_model.set(cfg["model"]["openai"].get("name","gpt-4o-mini"))

        btns = ttk.Frame(frm); btns.grid(row=9, column=0, columnspan=2, sticky="e", pady=8)
        def _save():
            obj = {
                "provider": self.provider_var.get(),
                "llm": {
                    "deepseek": {
                        "api_key": ds_key.get().strip(),
                        "base_url": ds_url.get().strip(),
                        "organization": None,
                        "extra_headers": {},
                    },
                    "openai": {
                        "api_key": oa_key.get().strip(),
                        "base_url": oa_url.get().strip(),
                        "organization": None,
                        "extra_headers": {},
                    }
                },
                "model": {
                    "deepseek": {"name": ds_model.get().strip() or "deepseek-ai/DeepSeek-V3.2-Exp"},
                    "openai": {"name": oa_model.get().strip() or "gpt-4o-mini"},
                },
                "rate_limit": {"rpm": self.rpm_var.get()}
            }
            write_yaml(SETTINGS_LOCAL, obj)
            messagebox.showinfo("OK", "Saved to config/settings.local.yaml")
            win.destroy()
        ttk.Button(btns, text=I18N[self.lang]["save"], command=_save).pack(side="right", padx=6)
        ttk.Button(btns, text=I18N[self.lang]["cancel"], command=win.destroy).pack(side="right")

    # ----- Start/Stop -----
    def on_start(self):
        self._store_prefs()
        self._clear_stop_flag()
        self.clear_log()
        self.btn_start.configure(state=tk.DISABLED)
        self.btn_stop.configure(state=tk.NORMAL)
        self.btn_open.configure(state=tk.DISABLED)
        self.stage_var.set(0.0); self.trans_var.set(0.0)
        self.to_translate = None; self.q_remaining=None

        # get lang code from display
        disp = self.cmb_lang.get()
        code = next((c for d,c in LANG_CHOICES if d==disp), "zh-CN")

        # add recents
        ex = self.excel_var.get().strip(); gl = self.gloss_var.get().strip()
        if ex and ex not in self._recent_excels: self._recent_excels.insert(0, ex)
        if gl and gl not in self._recent_gloss: self._recent_gloss.insert(0, gl)
        self._refresh_recent_menus(); self._store_prefs()

        cmds = []
        if self.do_seg.get():
            cmds.append([sys.executable, "-u", "-m", "scripts.05_segment_context", "--excel", ex])
        # translation
        outdir = ensure_dir(self.outdir_var.get())
        cmd2 = [
            sys.executable, "-u", "-m", "scripts.12_llm_translate",
            "--excel", ex,
            "--target-lang", code,
            "--glossary", gl,
            "--rpm", str(self.rpm_var.get()),
            "--tpm-max", str(self.tpm_var.get()),
            "--autosave-every", str(self.auto_rows.get()),
            "--autosave-seconds", str(self.auto_secs.get()),
        ]
        # optional out path
        # (let script default if you don't want to force it)
        self._pipeline = cmds + [cmd2]

        self.append_log(f"== Workdir: {ROOT} ==")
        self._run_pipeline()

    def _run_pipeline(self):
        if not self._pipeline:
            self.on_done(0)
            return
        cmd = self._pipeline.pop(0)
        pretty = " ".join(cmd)
        self.append_log(f"== Running ==\n$ {pretty}")
        self.stage_now += 1
        self._runner = ProcRunner(cmd, cwd=str(ROOT), on_line=self.append_log, on_done=self._on_step_done)
        self._runner.start()

    def _on_step_done(self, rc):
        if rc != 0:
            self.append_log(f"[ERROR] step failed: rc={rc}")
            self.on_done(rc); return
        if self._pipeline:
            # mark stage progress as completed segment for 2-step
            pct = 100.0 * (self.stage_now)/max(1,self.stage_total)
            self.stage_var.set(pct)
            self._run_pipeline()
        else:
            self.on_done(0)

    def on_done(self, rc):
        self.btn_start.configure(state=tk.NORMAL)
        self.btn_stop.configure(state=tk.DISABLED)
        if rc == 0:
            self.append_log("[OK] All done.")
        else:
            self.append_log("[WARN] Finished with return code: %s" % rc)

    def on_stop(self):
        # graceful stop: write stop.flag; let translator flush & exit
        self._create_stop_flag()
        self.append_log("[INFO] stop.flag created; translator will flush & exit soon...")
        self.root.after(2000, self._hard_kill)

    def _hard_kill(self):
        try:
            if hasattr(self, "_runner"):
                self._runner.stop()
        except Exception:
            pass
        self.btn_start.configure(state=tk.NORMAL)
        self.btn_stop.configure(state=tk.DISABLED)

    def open_last_output(self):
        if self.last_output:
            open_path(Path(self.last_output))

    # ----- stop.flag helpers -----
    def _stop_flag_path(self):
        outdir = ensure_dir(self.outdir_var.get() or DEFAULT_OUTDIR)
        return outdir / "stop.flag"

    def _create_stop_flag(self):
        try:
            self._stop_flag_path().write_text("stop", encoding="utf-8")
        except Exception as e:
            self.append_log(f"[WARN] cannot write stop.flag: {e}")

    def _clear_stop_flag(self):
        try:
            p = self._stop_flag_path()
            if p.exists(): p.unlink()
        except Exception:
            pass

    # ----- File pickers -----
    def pick_excel(self):
        p = filedialog.askopenfilename(title="Pick Excel", filetypes=[("Excel","*.xlsx")], initialdir=str((ROOT/"data")))
        if p:
            self.excel_var.set(p); self._store_prefs(); self._recent_excels.insert(0, p); self._refresh_recent_menus()

    def pick_gloss(self):
        p = filedialog.askopenfilename(title="Pick Glossary (JSON)", filetypes=[("JSON","*.json")], initialdir=str((ROOT/"data")))
        if p:
            self.gloss_var.set(p); self._store_prefs(); self._recent_gloss.insert(0, p); self._refresh_recent_menus()

    def pick_outdir(self):
        p = filedialog.askdirectory(title="Pick Output Dir", initialdir=str(ROOT))
        if p:
            self.outdir_var.set(p); self._store_prefs()

    # ----- Toggle advanced -----
    def toggle_advanced(self):
        if self.adv_visible:
            self.adv_frame.grid_remove()
            self.adv_visible = False
        else:
            self.adv_frame.grid()
            self.adv_visible = True

# ---------- main ----------
def main():
    root = tk.Tk()
    app = App(root)
    root.mainloop()

if __name__ == "__main__":
    main()
