# -*- coding: utf-8 -*-
"""
00_launch_gui.py
A compact yet robust Tkinter GUI wrapper for the MLS optimizer pipeline.

Features
- File pickers (Excel, Glossary)
- Language chooser (human-friendly name -> code) + GUI language toggle (中/EN)
- Step 1 (segment) + Step 2 (translate) pipeline, sequential
- Checkboxes and inputs for: retranslate, row-range, speaker filter, scene-range
- Post-processing toggles: enforce terms, style adapt, QA (20/30/25)
- Colorful log with scrollback; incremental append; true progress bar parsing
- Stop button that terminates the running child process
- Recent (Excel/Glossary) list, persisted to artifacts/gui_recent.json
- Settings dialog to edit provider/api_key/base_url/model in config/settings.local.yaml
- Opens output/artifacts/README/issues

NOTE
- This script assumes your other scripts are in scripts/ and data/ & artifacts/ exist.
- Tested on Windows Python 3.12+ (Tkinter included).

"""

import os
import sys
import re
import json
import queue
import time
import threading
import subprocess
import webbrowser
from pathlib import Path

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

try:
    import yaml  # PyYAML
except Exception:
    yaml = None

APP_TITLE = "MLS Optimizer GUI"
BASE_DIR = Path(__file__).resolve().parent.parent
SCRIPTS = BASE_DIR / "scripts"
DATA = BASE_DIR / "data"
ARTIFACTS = BASE_DIR / "artifacts"
CONFIG = BASE_DIR / "config"
RECENT_FILE = ARTIFACTS / "gui_recent.json"
SETTINGS_FILE = CONFIG / "settings.local.yaml"

# ---------------- I18N ----------------

I18N = {
    "zh": {
        "title": "MLS 本地化助手",
        "file": "文件",
        "config": "配置",
        "view": "视图",
        "help": "帮助",
        "recent_excel": "最近 Excel",
        "recent_glossary": "最近术语表",
        "open_readme": "打开 README",
        "open_issues": "打开问题页",
        "provider_panel": "API 提供商设置",
        "log_level": "日志级别",
        "level_all": "全部",
        "level_info": "信息",
        "level_warn": "警告",
        "level_error": "错误",
        "excel": "Excel 文件",
        "sheet": "工作表索引",
        "glossary": "术语表",
        "target_lang": "目标语言",
        "toggle_lang": "界面语言",
        "retranslate": "覆盖已有译文（重译）",
        "row_range": "行号范围（如 100:500）",
        "speaker_filter": "Speaker 过滤（支持 *）",
        "scene_range": "场景范围（如 1:20）",
        "postproc": "后处理：术语统一 / 风格适配 / QA",
        "run": "运行",
        "dryrun": "仅预览（Dry run）",
        "stop": "停止",
        "open_output": "打开输出",
        "open_artifacts": "打开 artifacts",
        "log": "运行日志",
        "progress": "进度",
        "settings": "设置",
        "provider": "提供商",
        "api_key": "API Key",
        "base_url": "Base URL",
        "model": "模型",
        "save": "保存",
        "cancel": "取消",
        "seg_step": "== Step 1/2 ==",
        "tr_step": "== Step 2/2 ==",
        "started": "开始运行流水线…",
        "finished": "完成。",
        "choose": "选择…",
    },
    "en": {
        "title": "MLS Localization Assistant",
        "file": "File",
        "config": "Config",
        "view": "View",
        "help": "Help",
        "recent_excel": "Recent Excel",
        "recent_glossary": "Recent Glossary",
        "open_readme": "Open README",
        "open_issues": "Open Issues",
        "provider_panel": "API Provider Settings",
        "log_level": "Log Level",
        "level_all": "ALL",
        "level_info": "INFO",
        "level_warn": "WARN",
        "level_error": "ERROR",
        "excel": "Excel",
        "sheet": "Sheet Index",
        "glossary": "Glossary",
        "target_lang": "Target language",
        "toggle_lang": "UI Lang",
        "retranslate": "Overwrite existing translations",
        "row_range": "Row range (e.g. 100:500)",
        "speaker_filter": "Speaker filter (* supported)",
        "scene_range": "Scene range (e.g. 1:20)",
        "postproc": "Post-processing: Terms / Style / QA",
        "run": "Run",
        "dryrun": "Dry run",
        "stop": "Stop",
        "open_output": "Open Output",
        "open_artifacts": "Open artifacts",
        "log": "Logs",
        "progress": "Progress",
        "settings": "Settings",
        "provider": "Provider",
        "api_key": "API Key",
        "base_url": "Base URL",
        "model": "Model",
        "save": "Save",
        "cancel": "Cancel",
        "seg_step": "== Step 1/2 ==",
        "tr_step": "== Step 2/2 ==",
        "started": "Pipeline started…",
        "finished": "Done.",
        "choose": "Browse…",
    }
}

LANG_CHOICES = [
    ("简体中文", "zh-CN"),
    ("繁體中文", "zh-TW"),
    ("English", "en"),
    ("日本語", "ja"),
    ("한국어", "ko"),
    ("Français", "fr"),
    ("Deutsch", "de"),
    ("Español", "es"),
    ("Português (BR)", "pt-BR"),
    ("Русский", "ru"),
    ("Italiano", "it"),
    ("Türkçe", "tr"),
    ("ภาษาไทย", "th"),
    ("Tiếng Việt", "vi"),
]

LEVEL_TAGS = ("ALL", "INFO", "WARN", "ERROR")

def ensure_dirs():
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    DATA.mkdir(parents=True, exist_ok=True)
    CONFIG.mkdir(parents=True, exist_ok=True)

def load_yaml(path: Path):
    if not path.exists() or yaml is None:
        return {}
    with path.open("r", encoding="utf-8") as f:
        try:
            return yaml.safe_load(f) or {}
        except Exception:
            return {}

def save_yaml(path: Path, obj: dict):
    if yaml is None:
        raise RuntimeError("PyYAML is not installed, cannot save settings.")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(obj, f, allow_unicode=True, sort_keys=False)

def load_recent():
    if RECENT_FILE.exists():
        try:
            return json.loads(RECENT_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}

def save_recent(obj):
    RECENT_FILE.parent.mkdir(parents=True, exist_ok=True)
    RECENT_FILE.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")

def add_recent(recent: dict, key: str, path: str, keep=10):
    arr = list(dict.fromkeys([path] + recent.get(key, [])))
    recent[key] = arr[:keep]

# -------------- Runner -----------------

class ProcRunner:
    def __init__(self, log_cb, progress_cb, done_cb):
        self._log_cb = log_cb
        self._progress_cb = progress_cb
        self._done_cb = done_cb
        self._thread = None
        self._stop = threading.Event()
        self._proc = None
        self._last_output = None
        self._plan_total = None

    def running(self):
        return self._thread is not None and self._thread.is_alive()

    def stop(self):
        self._stop.set()
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.terminate()
            except Exception:
                pass

    def _run_cmd(self, cmd: list, cwd: Path):
        # Log the exact command string for transparency
        self._log_cb("[CMD] " + " ".join([f'"{c}"' if " " in c else c for c in cmd]), "INFO")
        self._proc = subprocess.Popen(
            cmd,
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        assert self._proc.stdout
        for line in self._proc.stdout:
            if self._stop.is_set():
                break
            line = line.rstrip("\n")
            self._log_cb(line, "ALL")
            # Progress parse
            m_plan = re.search(r"\[PLAN\]\s+total=(\d+)\s+(?:to_translate|to\_translate)=(\d+)", line)
            if m_plan:
                try:
                    self._plan_total = int(m_plan.group(2))
                    self._progress_cb(0.0)
                except Exception:
                    pass
            m_prog = re.search(r"\[PROGRESS\].*q=(\d+)", line)
            if m_prog and self._plan_total:
                try:
                    q = int(m_prog.group(1))
                    done = max(0, self._plan_total - q)
                    pct = 100.0 * done / max(1, self._plan_total)
                    self._progress_cb(pct)
                except Exception:
                    pass
            # Capture output file hint
            m_out = re.search(r"Output\s*->\s*(.+\.xlsx)", line)
            if m_out:
                self._last_output = m_out.group(1).strip()

        rc = self._proc.wait()
        return rc

    def _run_pipeline(self, cmds, cwd: Path):
        rc = 0
        for cmd in cmds:
            if self._stop.is_set():
                rc = 1
                break
            rc = self._run_cmd(cmd, cwd)
            if rc != 0:
                break
        self._done_cb(rc, self._last_output)

    def start(self, cmds, cwd: Path):
        if self.running():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run_pipeline, args=(cmds, cwd), daemon=True)
        self._thread.start()

# -------------- GUI --------------------

class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.lang = "zh"
        self.level = "ALL"
        self.recent = load_recent()
        self.settings = load_yaml(SETTINGS_FILE)
        ensure_dirs()

        self.last_output = None

        # UI state vars
        self.var_excel = tk.StringVar(value=str((DATA / "MLS Chinese.xlsx")) if (DATA / "MLS Chinese.xlsx").exists() else "")
        self.var_sheet = tk.IntVar(value=0)
        self.var_glossary = tk.StringVar(value=str(DATA / "name_map.json") if (DATA / "name_map.json").exists() else "")
        self.var_target_lang = tk.StringVar(value="zh-CN")
        self.var_retranslate = tk.BooleanVar(value=False)
        self.var_row_range = tk.StringVar(value="")
        self.var_speaker = tk.StringVar(value="")
        self.var_scene_range = tk.StringVar(value="")
        self.var_post_terms = tk.BooleanVar(value=False)
        self.var_post_style = tk.BooleanVar(value=False)
        self.var_post_qa = tk.BooleanVar(value=False)

        self.runner = ProcRunner(self._append_log, self._set_progress, self._on_done)

        self._build_ui()
        self._apply_i18n()
        self._append_log(self._t("started"), "INFO")

    # ---------- UI Build ----------

    def _build_ui(self):
        self.root.title(I18N[self.lang]["title"])
        self.root.geometry("1100x720")
        self.root.minsize(920, 600)

        # Menu
        self._build_menu()

        # Top form
        frm = ttk.Frame(self.root, padding=8)
        frm.grid(row=0, column=0, sticky="nsew")
        self.root.grid_rowconfigure(0, weight=0)
        self.root.grid_rowconfigure(1, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        # --- Row 1: Excel + Browse
        r = 0
        ttk.Label(frm, text=self._t("excel")).grid(row=r, column=0, sticky="w", padx=4, pady=2)
        self.ent_excel = ttk.Entry(frm, textvariable=self.var_excel, width=70)
        self.ent_excel.grid(row=r, column=1, sticky="ew", padx=4, pady=2)
        ttk.Button(frm, text=self._t("choose"), command=self._choose_excel).grid(row=r, column=2, sticky="w", padx=4, pady=2)
        ttk.Label(frm, text=self._t("sheet")).grid(row=r, column=3, sticky="w", padx=4, pady=2)
        self.ent_sheet = ttk.Spinbox(frm, from_=0, to=99, textvariable=self.var_sheet, width=5)
        self.ent_sheet.grid(row=r, column=4, sticky="w", padx=4, pady=2)

        # --- Row 2: Glossary + Target Lang + UI toggle
        r += 1
        ttk.Label(frm, text=self._t("glossary")).grid(row=r, column=0, sticky="w", padx=4, pady=2)
        self.ent_gloss = ttk.Entry(frm, textvariable=self.var_glossary, width=70)
        self.ent_gloss.grid(row=r, column=1, sticky="ew", padx=4, pady=2)
        ttk.Button(frm, text=self._t("choose"), command=self._choose_glossary).grid(row=r, column=2, sticky="w", padx=4, pady=2)

        ttk.Label(frm, text=self._t("target_lang")).grid(row=r, column=3, sticky="w", padx=4, pady=2)
        self.cmb_lang = ttk.Combobox(frm, state="readonly", values=[f"{n} ({c})" for n,c in LANG_CHOICES], width=24)
        self.cmb_lang.grid(row=r, column=4, sticky="w", padx=4, pady=2)
        self._set_combo_lang_from_code(self.var_target_lang.get())
        self.cmb_lang.bind("<<ComboboxSelected>>", self._on_target_lang_change)

        # UI lang toggle
        self.btn_ui_lang = ttk.Button(frm, text=self._t("toggle_lang"), command=self._toggle_ui_lang, width=12)
        self.btn_ui_lang.grid(row=r, column=5, sticky="e", padx=4, pady=2)

        # --- Row 3: Options line
        r += 1
        self.chk_re = ttk.Checkbutton(frm, text=self._t("retranslate"), variable=self.var_retranslate)
        self.chk_re.grid(row=r, column=0, columnspan=2, sticky="w", padx=4, pady=2)

        ttk.Label(frm, text=self._t("row_range")).grid(row=r, column=2, sticky="e", padx=4, pady=2)
        self.ent_row = ttk.Entry(frm, textvariable=self.var_row_range, width=18)
        self.ent_row.grid(row=r, column=3, sticky="w", padx=4, pady=2)

        ttk.Label(frm, text=self._t("speaker_filter")).grid(row=r, column=4, sticky="e", padx=4, pady=2)
        self.ent_spk = ttk.Entry(frm, textvariable=self.var_speaker, width=20)
        self.ent_spk.grid(row=r, column=5, sticky="w", padx=4, pady=2)

        # --- Row 4: scene range + postproc
        r += 1
        ttk.Label(frm, text=self._t("scene_range")).grid(row=r, column=0, sticky="e", padx=4, pady=2)
        self.ent_scene = ttk.Entry(frm, textvariable=self.var_scene_range, width=18)
        self.ent_scene.grid(row=r, column=1, sticky="w", padx=4, pady=2)

        self.chk_terms = ttk.Checkbutton(frm, text="Terms", variable=self.var_post_terms)
        self.chk_style = ttk.Checkbutton(frm, text="Style", variable=self.var_post_style)
        self.chk_qa = ttk.Checkbutton(frm, text="QA", variable=self.var_post_qa)
        ttk.Label(frm, text=self._t("postproc")).grid(row=r, column=2, sticky="e", padx=4, pady=2)
        self.chk_terms.grid(row=r, column=3, sticky="w", padx=4, pady=2)
        self.chk_style.grid(row=r, column=4, sticky="w", padx=4, pady=2)
        self.chk_qa.grid(row=r, column=5, sticky="w", padx=4, pady=2)

        # --- Row 5: buttons
        r += 1
        btns = ttk.Frame(frm)
        btns.grid(row=r, column=0, columnspan=6, sticky="ew", pady=6)
        btns.grid_columnconfigure(0, weight=1)
        self.btn_run = ttk.Button(btns, text=self._t("run"), command=lambda: self._run_pipeline(dry=False), width=14)
        self.btn_dry = ttk.Button(btns, text=self._t("dryrun"), command=lambda: self._run_pipeline(dry=True), width=14)
        self.btn_stop = ttk.Button(btns, text=self._t("stop"), command=self._on_stop, width=12, state=tk.DISABLED)
        self.btn_open_out = ttk.Button(btns, text=self._t("open_output"), command=self._open_last_output, width=14, state=tk.DISABLED)
        self.btn_open_art = ttk.Button(btns, text=self._t("open_artifacts"), command=lambda: self._open_path(ARTIFACTS), width=14)

        self.btn_run.grid(row=0, column=1, padx=4, sticky="e")
        self.btn_dry.grid(row=0, column=2, padx=4, sticky="w")
        self.btn_stop.grid(row=0, column=3, padx=16, sticky="w")
        self.btn_open_out.grid(row=0, column=4, padx=4, sticky="w")
        self.btn_open_art.grid(row=0, column=5, padx=4, sticky="w")

        # --- Row 6: Progress + Log
        r += 1
        prf = ttk.Frame(self.root, padding=(8,2,8,8))
        prf.grid(row=1, column=0, sticky="nsew")
        self.root.grid_rowconfigure(1, weight=1)
        prf.grid_rowconfigure(1, weight=1)
        prf.grid_columnconfigure(0, weight=1)

        ttk.Label(prf, text=self._t("progress")).grid(row=0, column=0, sticky="w")
        self.pbar = ttk.Progressbar(prf, mode="determinate", maximum=100.0)
        self.pbar.grid(row=0, column=1, sticky="ew", padx=8)
        self.lbl_pct = ttk.Label(prf, text="0%")
        self.lbl_pct.grid(row=0, column=2, sticky="e")

        # Text log + scrollbar
        logf = ttk.Frame(prf)
        logf.grid(row=1, column=0, columnspan=3, sticky="nsew", pady=(6,0))
        logf.grid_rowconfigure(0, weight=1)
        logf.grid_columnconfigure(0, weight=1)

        self.txt = tk.Text(logf, wrap="word", height=18, bg="#111111", fg="#E0E0E0")
        self.txt.grid(row=0, column=0, sticky="nsew")
        self.scroll = ttk.Scrollbar(logf, orient="vertical", command=self.txt.yview)
        self.scroll.grid(row=0, column=1, sticky="ns")
        self.txt.configure(yscrollcommand=self.scroll.set)

        # tags
        self.txt.tag_configure("INFO", foreground="#99D9EA")
        self.txt.tag_configure("WARN", foreground="#FFCC00")
        self.txt.tag_configure("ERROR", foreground="#FF6B6B")
        self.txt.tag_configure("ALL", foreground="#C8C8C8")

        # Columns stretch
        for c in [1]:
            frm.grid_columnconfigure(c, weight=1)

    def _build_menu(self):
        t = I18N[self.lang]
        self.mbar = tk.Menu(self.root)

        # File
        self.mn_file = tk.Menu(self.mbar, tearoff=0)
        self.mn_recent_excel = tk.Menu(self.mn_file, tearoff=0)
        self.mn_recent_gloss = tk.Menu(self.mn_file, tearoff=0)
        self.mn_file.add_cascade(label=t["recent_excel"], menu=self.mn_recent_excel)
        self.mn_file.add_cascade(label=t["recent_glossary"], menu=self.mn_recent_gloss)
        self.mbar.add_cascade(label=t["file"], menu=self.mn_file)

        # Config
        self.mn_cfg = tk.Menu(self.mbar, tearoff=0)
        self.mn_cfg.add_command(label=t["provider_panel"], command=self._open_settings)
        self.mbar.add_cascade(label=t["config"], menu=self.mn_cfg)

        # View
        self.mn_view = tk.Menu(self.mbar, tearoff=0)
        self.log_level = tk.StringVar(value="ALL")
        self.mn_view.add_radiobutton(label=t["level_all"], variable=self.log_level, value="ALL")
        self.mn_view.add_radiobutton(label=t["level_info"], variable=self.log_level, value="INFO")
        self.mn_view.add_radiobutton(label=t["level_warn"], variable=self.log_level, value="WARN")
        self.mn_view.add_radiobutton(label=t["level_error"], variable=self.log_level, value="ERROR")
        self.mbar.add_cascade(label=t["view"], menu=self.mn_view)

        # Help
        self.mn_help = tk.Menu(self.mbar, tearoff=0)
        self.mn_help.add_command(label=t["open_readme"], command=self._open_readme)
        self.mn_help.add_command(label=t["open_issues"], command=self._open_issues)
        self.mbar.add_cascade(label=t["help"], menu=self.mn_help)

        self.root.config(menu=self.mbar)
        self._refresh_recent_menus()

    def _refresh_recent_menus(self):
        # Excel
        self.mn_recent_excel.delete(0, "end")
        for p in self.recent.get("excel", []):
            self.mn_recent_excel.add_command(label=p, command=lambda x=p: self.var_excel.set(x))
        # Glossary
        self.mn_recent_gloss.delete(0, "end")
        for p in self.recent.get("glossary", []):
            self.mn_recent_gloss.add_command(label=p, command=lambda x=p: self.var_glossary.set(x))

    # ---------- i18n ----------
    def _t(self, key):
        return I18N[self.lang].get(key, key)

    def _apply_i18n(self):
        self.root.title(self._t("title"))
        # Labels/buttons are rebuilt on demand during layout or toggle.
        # Menu relabel:
        self.mbar.entryconfig(0, label=self._t("file"))
        self.mbar.entryconfig(1, label=self._t("config"))
        self.mbar.entryconfig(2, label=self._t("view"))
        self.mbar.entryconfig(3, label=self._t("help"))
        # File submenu
        self.mn_file.entryconfig(0, label=self._t("recent_excel"))
        self.mn_file.entryconfig(1, label=self._t("recent_glossary"))
        # Config submenu
        self.mn_cfg.entryconfig(0, label=self._t("provider_panel"))
        # View submenu
        self.mn_view.entryconfig(0, label=self._t("level_all"))
        self.mn_view.entryconfig(1, label=self._t("level_info"))
        self.mn_view.entryconfig(2, label=self._t("level_warn"))
        self.mn_view.entryconfig(3, label=self._t("level_error"))
        # Help submenu
        self.mn_help.entryconfig(0, label=self._t("open_readme"))
        self.mn_help.entryconfig(1, label=self._t("open_issues"))

    def _toggle_ui_lang(self):
        self.lang = "en" if self.lang == "zh" else "zh"
        self._apply_i18n()
        # Update form captions
        # Rebuild key row labels
        # (Quick approach: update button texts; labels are static – safe to leave)

        self.btn_ui_lang.configure(text=self._t("toggle_lang"))
        self.btn_run.configure(text=self._t("run"))
        self.btn_dry.configure(text=self._t("dryrun"))
        self.btn_stop.configure(text=self._t("stop"))
        self.btn_open_out.configure(text=self._t("open_output"))
        self.btn_open_art.configure(text=self._t("open_artifacts"))

    def _set_combo_lang_from_code(self, code: str):
        for i, (name, c) in enumerate(LANG_CHOICES):
            if c == code:
                self.cmb_lang.current(i)
                return
        self.cmb_lang.current(0)

    def _on_target_lang_change(self, *_):
        sel = self.cmb_lang.get()
        m = re.search(r"\(([^)]+)\)$", sel)
        code = m.group(1) if m else "zh-CN"
        self.var_target_lang.set(code)

    # ---------- file ops ----------

    def _choose_excel(self):
        p = filedialog.askopenfilename(
            title="Excel",
            filetypes=[("Excel", "*.xlsx *.xls")],
            initialdir=str(DATA if DATA.exists() else BASE_DIR),
        )
        if p:
            self.var_excel.set(p)
            add_recent(self.recent, "excel", p)
            save_recent(self.recent)
            self._refresh_recent_menus()

    def _choose_glossary(self):
        p = filedialog.askopenfilename(
            title="Glossary",
            filetypes=[("JSON", "*.json"), ("All", "*.*")],
            initialdir=str(DATA if DATA.exists() else BASE_DIR),
        )
        if p:
            self.var_glossary.set(p)
            add_recent(self.recent, "glossary", p)
            save_recent(self.recent)
            self._refresh_recent_menus()

    def _open_last_output(self):
        if self.last_output and os.path.exists(self.last_output):
            self._open_path(Path(self.last_output).parent)
        else:
            self._open_path(DATA)

    def _open_readme(self):
        p = BASE_DIR / "README.md"
        if p.exists():
            os.startfile(str(p))
        else:
            # If you host repo later, replace with web URL
            messagebox.showinfo("README", "README.md not found in project root.")

    def _open_issues(self):
        # Replace with your repo issues URL if available
        messagebox.showinfo("Issues", "Please open your GitHub issues page if available.")

    def _open_path(self, p: Path):
        try:
            os.startfile(str(p))
        except Exception as e:
            messagebox.showerror("Open", f"Cannot open: {p}\n{e}")

    # ---------- settings ----------

    def _open_settings(self):
        t = self._t
        win = tk.Toplevel(self.root)
        win.title(t("provider_panel"))
        win.grab_set()
        win.resizable(False, False)

        cfg = load_yaml(SETTINGS_FILE)
        llm = ((cfg.get("llm") or {}))
        provider = cfg.get("provider") or "deepseek"
        deep = llm.get("deepseek") or {}
        openai = llm.get("openai") or {}

        var_provider = tk.StringVar(value=provider)
        var_deep_key = tk.StringVar(value=str(deep.get("api_key") or ""))
        var_deep_url = tk.StringVar(value=str(deep.get("base_url") or ""))
        var_deep_model = tk.StringVar(value=str((cfg.get("model") or {}).get("deepseek", {}).get("name") or ""))

        var_oa_key = tk.StringVar(value=str(openai.get("api_key") or ""))
        var_oa_url = tk.StringVar(value=str(openai.get("base_url") or ""))
        var_oa_model = tk.StringVar(value=str((cfg.get("model") or {}).get("openai", {}).get("name") or ""))

        frm = ttk.Frame(win, padding=12)
        frm.grid(row=0, column=0, sticky="nsew")
        ttk.Label(frm, text=t("provider")).grid(row=0, column=0, sticky="w")
        cb = ttk.Combobox(frm, values=["deepseek", "openai"], state="readonly", textvariable=var_provider, width=12)
        cb.grid(row=0, column=1, sticky="w", padx=6, pady=4)

        # DeepSeek
        ttk.Label(frm, text="[DeepSeek] "+t("api_key")).grid(row=1, column=0, sticky="e", padx=4, pady=2)
        ttk.Entry(frm, textvariable=var_deep_key, width=42).grid(row=1, column=1, sticky="w", padx=4, pady=2)
        ttk.Label(frm, text="[DeepSeek] "+t("base_url")).grid(row=2, column=0, sticky="e", padx=4, pady=2)
        ttk.Entry(frm, textvariable=var_deep_url, width=42).grid(row=2, column=1, sticky="w", padx=4, pady=2)
        ttk.Label(frm, text="[DeepSeek] "+t("model")).grid(row=3, column=0, sticky="e", padx=4, pady=2)
        ttk.Entry(frm, textvariable=var_deep_model, width=42).grid(row=3, column=1, sticky="w", padx=4, pady=2)

        # OpenAI
        ttk.Label(frm, text="[OpenAI] "+t("api_key")).grid(row=4, column=0, sticky="e", padx=4, pady=6)
        ttk.Entry(frm, textvariable=var_oa_key, width=42).grid(row=4, column=1, sticky="w", padx=4, pady=2)
        ttk.Label(frm, text="[OpenAI] "+t("base_url")).grid(row=5, column=0, sticky="e", padx=4, pady=2)
        ttk.Entry(frm, textvariable=var_oa_url, width=42).grid(row=5, column=1, sticky="w", padx=4, pady=2)
        ttk.Label(frm, text="[OpenAI] "+t("model")).grid(row=6, column=0, sticky="e", padx=4, pady=2)
        ttk.Entry(frm, textvariable=var_oa_model, width=42).grid(row=6, column=1, sticky="w", padx=4, pady=2)

        def on_save():
            new = cfg.copy()
            new["provider"] = var_provider.get()
            new.setdefault("llm", {})
            new["llm"].setdefault("deepseek", {})
            new["llm"]["deepseek"]["api_key"] = var_deep_key.get().strip()
            new["llm"]["deepseek"]["base_url"] = var_deep_url.get().strip()
            new.setdefault("model", {})
            new["model"].setdefault("deepseek", {})
            new["model"]["deepseek"]["name"] = var_deep_model.get().strip()

            new["llm"].setdefault("openai", {})
            new["llm"]["openai"]["api_key"] = var_oa_key.get().strip()
            new["llm"]["openai"]["base_url"] = var_oa_url.get().strip()
            new["model"].setdefault("openai", {})
            new["model"]["openai"]["name"] = var_oa_model.get().strip()

            try:
                save_yaml(SETTINGS_FILE, new)
                messagebox.showinfo(self._t("settings"), "Saved.")
                win.destroy()
            except Exception as e:
                messagebox.showerror(self._t("settings"), str(e))

        btns = ttk.Frame(frm)
        btns.grid(row=7, column=0, columnspan=2, pady=8, sticky="e")
        ttk.Button(btns, text=self._t("save"), command=on_save).grid(row=0, column=0, padx=6)
        ttk.Button(btns, text=self._t("cancel"), command=win.destroy).grid(row=0, column=1, padx=6)

    # ---------- logging ----------

    def _append_log(self, msg: str, level: str="ALL"):
        # level filter (view menu)
        lv = self.log_level.get() if hasattr(self, "log_level") else "ALL"
        show = (lv == "ALL") or (level == lv) or (level in ("ERROR","WARN") and lv in ("INFO","WARN","ERROR")) or (level=="INFO" and lv in ("INFO",))
        if not show and level != "ALL":
            return
        ts = time.strftime("[%H:%M:%S] ")
        self.txt.insert("end", ts+msg+"\n", (level,))
        self.txt.see("end")

    def _set_progress(self, pct: float):
        pct = max(0.0, min(100.0, pct))
        self.pbar["value"] = pct
        self.lbl_pct.configure(text=f"{pct:.0f}%")
        self.root.update_idletasks()

    # ---------- pipeline ----------

    def _run_pipeline(self, dry: bool):
        if self.runner.running():
            return
        excel = self.var_excel.get().strip()
        if not excel:
            messagebox.showwarning("Excel", "请选择 Excel 文件")
            return
        # Build commands:
        cmds = []

        # Step 1: segment
        cmds.append([sys.executable, "-u", "-m", "scripts.05_segment_context",
            "--excel", excel, "--sheet-index", str(self.var_sheet.get())])

        # Step 2: translate
        target = self.var_target_lang.get().strip() or "zh-CN"
        cmd2 = [sys.executable, "-u", "-m", "scripts.12_llm_translate",
            "--excel", excel, "--sheet-index", str(self.var_sheet.get()),
            "--target-lang", target]

        gloss = self.var_glossary.get().strip()
        if gloss:
            cmd2 += ["--glossary", gloss]

        if self.var_retranslate.get():
            cmd2 += ["--retranslate"]

        if self.var_row_range.get().strip():
            cmd2 += ["--row-range", self.var_row_range.get().strip()]

        if self.var_speaker.get().strip():
            cmd2 += ["--speaker", self.var_speaker.get().strip()]

        if self.var_scene_range.get().strip():
            cmd2 += ["--scene-range", self.var_scene_range.get().strip()]

        if dry:
            cmd2 += ["--dry-run"]

        # reasonable defaults; real auto-tune is inside translator
        cmd2 += ["--rpm", "400", "--tpm-max", "100000", "--show-lines"]

        cmds.append(cmd2)

        # Post-processing toggles
        out_hint = self._predict_out_path(excel, target)
        if self.var_post_terms.get():
            cmds.append([sys.executable, "-u", "-m", "scripts.20_enforce_terms",
                        "--excel", out_hint, "--glossary", gloss or "data/name_map.json"])
        if self.var_post_style.get():
            cmds.append([sys.executable, "-u", "-m", "scripts.30_style_adapt",
                        "--excel", out_hint, "--target-lang", target])
        if self.var_post_qa.get():
            cmds.append([sys.executable, "-u", "-m", "scripts.25_qa_check",
                        "--excel", out_hint, "--target-lang", target])

        # lock buttons
        self.btn_run.configure(state=tk.DISABLED)
        self.btn_dry.configure(state=tk.DISABLED)
        self.btn_stop.configure(state=tk.NORMAL)
        self.btn_open_out.configure(state=tk.DISABLED)

        self._append_log(self._t("started"), "INFO")
        self.runner.start(cmds, BASE_DIR)

    def _predict_out_path(self, excel_path: str, target: str):
        # Default behavior of translator script
        p = Path(excel_path)
        return str(p.with_name(f"{p.stem}.{target}.llm{p.suffix}"))

    def _on_stop(self):
        self.runner.stop()
        self._append_log("[INFO] Stop requested", "WARN")

    def _on_done(self, rc: int, last_out: str):
        self.last_output = last_out
        if rc == 0:
            self._append_log(self._t("finished"), "INFO")
            self.btn_open_out.configure(state=tk.NORMAL)
            if last_out:
                self._append_log(f"[OK] Output: {last_out}", "INFO")
        else:
            self._append_log(f"[ERROR] finished with rc={rc}", "ERROR")
        self.btn_run.configure(state=tk.NORMAL)
        self.btn_dry.configure(state=tk.NORMAL)
        self.btn_stop.configure(state=tk.DISABLED)

# -------------- main ---------------

def main():
    ensure_dirs()
    root = tk.Tk()
    style = ttk.Style()
    try:
        style.theme_use("clam")
    except Exception:
        pass
    App(root)
    root.mainloop()

if __name__ == "__main__":
    main()
