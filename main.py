#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
极简阅读器 - 透明无边框 TXT 阅读器 (Python tkinter，零依赖)
快捷键: Ctrl+` 唤出/隐藏  |  Ctrl+Shift+H 老板键  |  Ctrl+Shift+Q 退出  |  F9 备用
"""

import tkinter as tk
from tkinter import font as tkfont, filedialog
import ctypes
import ctypes.wintypes as wintypes
import json
import re
import pathlib
import threading
import sys

# ==================== 常量 ====================
APP_DIR = pathlib.Path(__file__).resolve().parent
DATA_DIR = APP_DIR / 'app-data'
DATA_DIR.mkdir(exist_ok=True)
STATE_FILE = DATA_DIR / 'reader-state.json'
PROGRESS_FILE = DATA_DIR / 'progress.json'

DEFAULTS = {'fontSize': 20, 'bgAlpha': 0.55, 'theme': 'dark',
            'autoHideDelay': 400, 'pin': False, 'lastFile': None,
            'geometry': '480x640+200+60',
            'customText': '#d4d4d4', 'customBg': '#1a1a2e'}

CHAPTER_RE = re.compile(
    r'^\s*第[\s]*[一二三四五六七八九十百千零〇两0-9]+[\s]*[章节回卷集部篇幕折话场](?:[\s:：·、\-].*)?$')

# Win32 全局快捷键
WM_HOTKEY = 0x0312
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_NOREPEAT = 0x4000
VK_OEM_3 = 0xC0   # `~ 键
VK_H = 0x48
VK_Q = 0x51
VK_F9 = 0x78       # F9 备用唤出键
HOTKEY_TOGGLE = 1
HOTKEY_BOSS = 2
HOTKEY_QUIT = 3
HOTKEY_TOGGLE2 = 4  # F9 备用

user32 = ctypes.windll.user32
user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
user32.GetCursorPos.restype = wintypes.BOOL
user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
user32.RegisterHotKey.restype = wintypes.BOOL
user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
user32.UnregisterHotKey.restype = wintypes.BOOL
user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.GetMessageW.restype = wintypes.BOOL

THEMES = {
    'dark':  {'bg': '#1a1a2e', 'fg': '#d4d4d4', 'tb': '#2a2a3a', 'tb_fg': '#ddd',
              'accent': '#14b8a6', 'sel_bg': '#2d4d4d', 'gutter': '#1a1a2e', 'gutter_fg': '#555'},
    'light': {'bg': '#faf9f6', 'fg': '#1f2937', 'tb': '#ebebeb', 'tb_fg': '#333',
              'accent': '#0284c7', 'sel_bg': '#cce4f5', 'gutter': '#faf9f6', 'gutter_fg': '#aaa'},
    'code':  {'bg': '#1e1e1e', 'fg': '#9cdcbb', 'tb': '#252526', 'tb_fg': '#ccc',
              'accent': '#569cd6', 'sel_bg': '#264f78', 'gutter': '#1e1e1e', 'gutter_fg': '#858585'},
    'custom':{'bg': '#1a1a2e', 'fg': '#d4d4d4', 'tb': '#2a2a3a', 'tb_fg': '#ddd',
              'accent': '#14b8a6', 'sel_bg': '#2d4d4d', 'gutter': '#1a1a2e', 'gutter_fg': '#555'},
}

# ==================== 工具函数 ====================

def load_state():
    try:
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            state = {**DEFAULTS, **json.load(f)}
    except Exception:
        state = dict(DEFAULTS)
    try:
        state['bgAlpha'] = min(1.0, max(0.15, float(state['bgAlpha'])))
    except (TypeError, ValueError):
        state['bgAlpha'] = DEFAULTS['bgAlpha']
    return state

def save_state(state):
    try:
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print('save_state:', e)

def load_progress():
    try:
        with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}

def save_progress(progress):
    try:
        with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
            json.dump(progress, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def read_txt(path):
    """读取 TXT 文件，自动识别编码"""
    with open(path, 'rb') as f:
        raw = f.read()
    if raw[:3] == b'\xef\xbb\xbf':
        return raw[3:].decode('utf-8'), 'UTF-8(BOM)'
    elif raw[:2] == b'\xff\xfe':
        return raw[2:].decode('utf-16-le'), 'UTF-16LE'
    elif raw[:2] == b'\xfe\xff':
        return raw[2:].decode('utf-16-be'), 'UTF-16BE'
    else:
        try:
            return raw.decode('utf-8'), 'UTF-8'
        except UnicodeDecodeError:
            return raw.decode('gb18030'), 'GB18030'

def parse_chapters(text):
    lines = text.split('\n')
    chapters = []
    cur = {'title': '开头', 'start': 0}
    has_heading = False
    for i, line in enumerate(lines):
        if CHAPTER_RE.match(line) and len(line.strip()) <= 40:
            if any(part.strip() for part in lines[cur['start']:i]):
                cur['end'] = i
                chapters.append(cur)
            cur = {'title': line.strip(), 'start': i + 1}
            has_heading = True
    if any(part.strip() for part in lines[cur['start']:]) or has_heading:
        cur['end'] = len(lines)
        chapters.append(cur)
    if not has_heading:
        chapters = []
        step = 1200
        for i in range(0, len(lines), step):
            chapters.append({'title': f'第 {i // step + 1} 段', 'start': i,
                             'end': min(i + step, len(lines))})
        if not chapters:
            chapters.append({'title': '正文', 'start': 0, 'end': len(lines)})
    return lines, chapters


# ==================== 全局快捷键线程 ====================

class HotkeyThread(threading.Thread):
    def __init__(self, root, on_hotkey):
        super().__init__(daemon=True)
        self.root = root
        self.on_hotkey = on_hotkey

    def run(self):
        hotkeys = [
            (HOTKEY_TOGGLE,  MOD_CONTROL, VK_OEM_3),          # Ctrl+`
            (HOTKEY_TOGGLE2, 0, VK_F9),                       # F9 备用
            (HOTKEY_BOSS,   MOD_CONTROL | MOD_SHIFT, VK_H),   # Ctrl+Shift+H
            (HOTKEY_QUIT,   MOD_CONTROL | MOD_SHIFT, VK_Q),   # Ctrl+Shift+Q
        ]
        for hid, mod, vk in hotkeys:
            ok = user32.RegisterHotKey(0, hid, mod | MOD_NOREPEAT, vk)
            if not ok:
                print(f'快捷键注册失败: id={hid} mod={mod} vk={vk}')
        msg = wintypes.MSG()
        while True:
            ret = user32.GetMessageW(ctypes.byref(msg), 0, WM_HOTKEY, WM_HOTKEY)
            if ret <= 0:
                break
            key_id = msg.wParam
            self.root.after(0, lambda k=key_id: self.on_hotkey(k))
        for hid in (HOTKEY_TOGGLE, HOTKEY_TOGGLE2, HOTKEY_BOSS, HOTKEY_QUIT):
            user32.UnregisterHotKey(0, hid)


# ==================== 主应用 ====================

class ReaderApp:
    def __init__(self):
        self.state = load_state()
        if self.state.get('theme') not in THEMES:
            self.state['theme'] = DEFAULTS['theme']
        self._set_custom_theme()
        self.progress = load_progress()
        self.book = None           # {'path','name','lines','chapters','chapter_index','encoding'}
        self.immersive = False
        self.hide_after_id = None
        self.hint_after_id = None
        self.progress_save_after_id = None
        self.state_save_after_id = None
        self.geometry_save_after_id = None
        self.drag_x = self.drag_y = 0
        self.resize_w = self.resize_h = 0

        self.root = tk.Tk()
        self.root.title('极简阅读器')
        self.setup_window()
        self.setup_fonts()
        self.setup_ui()
        self.apply_theme()
        self.apply_transparency()
        self.start_mouse_check()
        self.hotkey_thread = HotkeyThread(self.root, self.on_hotkey)
        self.hotkey_thread.start()

        # 加载上次文件或自动打开对话框
        if self.state.get('lastFile') and pathlib.Path(self.state['lastFile']).exists():
            self.root.after(300, lambda: self.load_file(self.state['lastFile']))
        else:
            self.root.after(500, self.open_file)

        self.root.protocol('WM_DELETE_WINDOW', self.quit_app)

    # ---- 窗口 ----
    def setup_window(self):
        self.root.overrideredirect(True)          # 无边框
        self.root.attributes('-topmost', True)     # 置顶
        self.root.attributes('-alpha', self.state['bgAlpha'])  # 透明
        geo = self.state.get('geometry', '480x640+200+60')
        self.root.geometry(geo)
        self.root.bind('<MouseWheel>', self.on_mousewheel)

    def on_mousewheel(self, event):
        if event.delta == 0:
            return 'break'
        units = int(-event.delta / 120) or (-1 if event.delta > 0 else 1)
        if self.immersive and self.book:
            first, last = self.text.yview()
            index = self.book['chapter_index']
            final_index = len(self.book['chapters']) - 1
            if units > 0 and last >= 0.999 and index < final_index:
                self.next_chapter()
                return 'break'
            if units < 0 and first <= 0.001 and index > 0:
                self.prev_chapter()
                self.root.after_idle(lambda: self.text.yview_moveto(1.0))
                return 'break'
        self.text.yview_scroll(units, 'units')
        return 'break'

    def setup_fonts(self):
        self.read_font = tkfont.Font(family='Microsoft YaHei', size=self.state['fontSize'])
        self.code_font = tkfont.Font(family='Consolas', size=max(11, self.state['fontSize'] - 4))
        self.tb_font = tkfont.Font(family='Microsoft YaHei', size=12)
        self.code_tb_font = tkfont.Font(family='Consolas', size=12)

    # ---- UI ----
    def setup_ui(self):
        t = THEMES[self.state['theme']]
        self.root.config(bg=t['bg'])

        # 伪装 IDE 顶栏
        self.fake_tabbar = tk.Frame(self.root, bg='#252526', height=28)
        for i, name in enumerate(['service.py', 'config.yml', 'utils.py']):
            bg = '#1e1e1e' if i == 0 else '#252526'
            fg = '#fff' if i == 0 else '#969696'
            tk.Label(self.fake_tabbar, text=f' {name} ', bg=bg, fg=fg,
                     font=self.code_tb_font).pack(side='left')

        # 顶部状态栏（含书名 + 颜色按钮，可拖动）
        self.top_bar = tk.Frame(self.root, bg=t['tb'], height=28)
        self.book_name = tk.Label(self.top_bar, text='未打开文件', bg=t['tb'], fg=t['tb_fg'],
                                  font=self.tb_font)
        self.book_name.pack(side='left', padx=(8, 6))
        tk.Frame(self.top_bar, bg=t['accent'], width=1).pack(side='left', fill='y', padx=2)

        # 字色按钮（按钮背景显示当前颜色）
        self.text_color_btn = tk.Button(self.top_bar, text='字色', command=self.pick_text_color,
                                        **self._btn_opts(t))
        self.text_color_btn.pack(side='left', padx=1)
        self.text_color_btn.config(bg=self.state.get('customText', '#d4d4d4'),
                                   fg=self._contrast_fg(self.state.get('customText', '#d4d4d4')))
        self._tooltip(self.text_color_btn, '字体颜色')

        self.bg_color_btn = tk.Button(self.top_bar, text='底色', command=self.pick_bg_color,
                                      **self._btn_opts(t))
        self.bg_color_btn.pack(side='left', padx=1)
        self.bg_color_btn.config(bg=self.state.get('customBg', '#1a1a2e'),
                                 fg=self._contrast_fg(self.state.get('customBg', '#1a1a2e')))
        self._tooltip(self.bg_color_btn, '背景颜色')

        # 右侧填充（拖动区域）
        tk.Frame(self.top_bar, bg=t['tb']).pack(side='left', fill='x', expand=True)
        # 底部彩色细线
        tk.Frame(self.top_bar, bg=t['accent'], height=2).pack(side='bottom', fill='x')
        # 拖动绑定：绑定到 top_bar 及其所有非按钮子控件
        self._bind_drag(self.top_bar)
        for child in self.top_bar.winfo_children():
            self._bind_drag(child)

        self.toolbar = tk.Frame(self.root, bg=t['tb'], height=42)
        self._make_toolbar()

        # 正文区
        self.content = tk.Frame(self.root, bg=t['bg'])
        self.gutter = tk.Text(self.content, width=5, font=self.code_tb_font,
                              bg=t['gutter'], fg=t['gutter_fg'], bd=0, padx=6,
                              insertwidth=0, highlightthickness=0, state='disabled',
                              wrap='none', cursor='arrow')
        self.gutter.pack(side='left', fill='y')
        self.gutter.pack_forget()  # 默认隐藏，仅 code 主题显示

        self.scrollbar = tk.Scrollbar(self.content, command=self._on_scrollbar,
                                      troughcolor=t['bg'], width=8)
        # 默认隐藏滚动条，鼠标进入正文区才显示

        self.text = tk.Text(self.content, font=self.read_font, wrap='word',
                            bg=t['bg'], fg=t['fg'], bd=0, padx=26, pady=16,
                            insertwidth=0, highlightthickness=0, cursor='arrow',
                            selectbackground=t['sel_bg'])
        self.text.pack(side='left', fill='both', expand=True)
        self.text['yscrollcommand'] = self._on_text_scroll

        self.content.pack(side='top', fill='both', expand=True)

        # 章节面板
        self.chapter_panel = tk.Frame(self.root, bg=t['tb'], width=220)
        tk.Label(self.chapter_panel, text='章节', bg=t['tb'], fg=t['tb_fg'],
                 font=self.tb_font).pack(side='top', fill='x', padx=8, pady=(6, 2))
        self.chapter_list = tk.Listbox(self.chapter_panel, bg=t['tb'], fg=t['tb_fg'],
                                       font=self.tb_font, bd=0, highlightthickness=0,
                                       selectbackground=t['accent'], selectforeground='#fff',
                                       activestyle='none')
        self.chapter_list.pack(side='top', fill='both', expand=True)
        self.chapter_list.bind('<<ListboxSelect>>', self.on_chapter_select)

        # 底部导航
        self.bottom_nav = tk.Frame(self.root, bg=t['tb'], height=40)
        self.prev_btn2 = tk.Button(self.bottom_nav, text='◀ 上一章', **self._btn_opts(t))
        self.prev_btn2.pack(side='left', padx=(10, 6), pady=4)
        self.prev_btn2.config(command=self.prev_chapter, bg=t['accent'], fg='#fff',
                              activebackground=t['accent'], activeforeground='#fff')
        self.progress_lbl = tk.Label(self.bottom_nav, text='阅读进度 0%', bg=t['tb'], fg=t['tb_fg'],
                                     font=self.tb_font)
        self.progress_lbl.pack(side='left', fill='x', expand=True)
        self.next_btn2 = tk.Button(self.bottom_nav, text='下一章 ▶', **self._btn_opts(t))
        self.next_btn2.pack(side='right', padx=10, pady=4)
        self.next_btn2.config(command=self.next_chapter, bg=t['accent'], fg='#fff',
                              activebackground=t['accent'], activeforeground='#fff')
        self.bottom_nav.pack(side='bottom', fill='x')

        # 伪装 IDE 状态栏
        self.fake_statusbar = tk.Frame(self.root, bg='#007acc', height=20)
        tk.Label(self.fake_statusbar, text='⎇ main', bg='#007acc', fg='#fff',
                 font=self.code_tb_font).pack(side='left', padx=8)
        self.fake_ln_lbl = tk.Label(self.fake_statusbar, text='Ln 1, Col 1', bg='#007acc', fg='#fff',
                                    font=self.code_tb_font)
        self.fake_ln_lbl.pack(side='right', padx=8)
        tk.Label(self.fake_statusbar, text='UTF-8  Python', bg='#007acc', fg='#fff',
                 font=self.code_tb_font).pack(side='right', padx=8)

        # 斜纹缩放角标
        self.resize_grip = tk.Canvas(self.content, width=20, height=20, bg=t['bg'],
                                     bd=0, highlightthickness=0, cursor='size')
        self.resize_grip_lines = [
            self.resize_grip.create_line(18, y, y, 18, fill=t['accent'], width=1)
            for y in (5, 10, 15)
        ]
        self.resize_grip.place(relx=1.0, rely=1.0, anchor='se', width=20, height=20)
        self.resize_grip.bind('<Button-1>', self.on_resize_start)
        self.resize_grip.bind('<B1-Motion>', self.on_resize_motion)
        self.resize_grip.bind('<ButtonRelease-1>', lambda e: self._schedule_geometry_save())
        self.resize_grip.bind('<Button-3>', lambda e: self.cycle_size())
        self._tooltip(self.resize_grip, '拖动调整大小；右键切换预设')

        # 提示
        self.hint_lbl = tk.Label(self.root, text='', bg='#000', fg='#fff',
                                 font=self.tb_font, padx=12, pady=6)
        # 提示气泡不拦截鼠标事件，避免挡住双击
        self.hint_lbl.bind('<Button-1>', lambda e: 'break')

        # 双击正文切换沉浸 / F11 也行 / 右键也行
        self.text.bind('<Double-Button-1>', lambda e: (self.toggle_immersive(), 'break')[1])
        self.text.bind('<Button-3>', lambda e: self.toggle_immersive() if self.immersive else None)
        self.root.bind('<F11>', lambda e: self.toggle_immersive())
        self.root.bind('<Control-Left>', lambda e: (self.prev_chapter(), 'break')[1])
        self.root.bind('<Control-Right>', lambda e: (self.next_chapter(), 'break')[1])
        # 鼠标进入正文区显示滚动条，离开隐藏
        self.text.bind('<Enter>', lambda e: self.scrollbar.pack(side='right', fill='y'))
        self.text.bind('<Leave>', lambda e: self.scrollbar.pack_forget())
        # 窗口布局变化时保持缩放手柄在最上层

        # 沉浸模式浮动退出按钮（默认隐藏）
        self.immersive_exit_btn = tk.Label(self.root, text='✕ 退出沉浸',
                                           bg='#e74c3c', fg='#fff', font=self.tb_font,
                                           padx=10, pady=4, cursor='hand2')
        self.immersive_exit_btn.bind('<Button-1>', lambda e: self.toggle_immersive())

    def _btn_opts(self, t):
        return dict(bg=t['tb'], fg=t['tb_fg'], font=self.tb_font, bd=0,
                    relief='flat', highlightthickness=0,
                    activebackground=t['accent'], activeforeground='#fff',
                    padx=7, pady=3, cursor='hand2')

    def _bind_drag(self, widget):
        """给控件绑定窗口拖动事件（按钮除外，按钮自己处理点击）"""
        if isinstance(widget, tk.Button):
            return
        widget.bind('<Button-1>', self.on_drag_start, add='+')
        widget.bind('<B1-Motion>', self.on_drag_motion, add='+')

    def _make_toolbar(self):
        t = THEMES[self.state['theme']]
        opts = self._btn_opts(t)

        for text, cmd, tip in [
            ('📂', self.open_file, '打开 TXT'),
            ('📑', self.toggle_chapter_panel, '章节列表'),
        ]:
            b = tk.Button(self.toolbar, text=text, command=cmd, **opts)
            b.pack(side='left', padx=1)
            self._tooltip(b, tip)

        tk.Frame(self.toolbar, bg=t['accent'], width=1).pack(side='left', fill='y', padx=2)

        for text, cmd, tip in [
            ('A-', lambda: self.set_font_size(-2), '缩小字号'),
            ('A+', lambda: self.set_font_size(2), '放大字号'),
        ]:
            b = tk.Button(self.toolbar, text=text, command=cmd, **opts)
            b.pack(side='left', padx=1)
            self._tooltip(b, tip)

        tk.Frame(self.toolbar, bg=t['accent'], width=1).pack(side='left', fill='y', padx=2)

        # 整个窗口连续透明度
        tk.Label(self.toolbar, text='◐', bg=t['tb'], fg=t['tb_fg'],
                 font=self.tb_font).pack(side='left', padx=(4, 2))
        self.opacity_var = tk.DoubleVar(value=self.state['bgAlpha'])
        self.opacity_scale = tk.Scale(self.toolbar, from_=0.15, to=1.0, resolution=0.05,
                                      orient='horizontal', variable=self.opacity_var,
                                      command=self.on_opacity, bg=t['tb'], fg=t['tb_fg'],
                                      font=self.tb_font, length=80, bd=0,
                                      troughcolor=t['bg'], highlightthickness=0,
                                      showvalue=False)
        self.opacity_scale.pack(side='left', padx=2)
        self._tooltip(self.opacity_scale, '窗口透明度（左=更透明，右=不透明）')

        tk.Frame(self.toolbar, bg=t['accent'], width=1).pack(side='left', fill='y', padx=2)

        for text, cmd, tip in [
            ('🎨', self.cycle_theme, '切换主题'),
            ('⤢', self.cycle_size, '窗口大小预设'),
            ('⛶', self.toggle_immersive, '沉浸模式'),
            ('📌', self.toggle_pin, '固定（暂停自动隐藏）'),
            ('—', self.hide_window, '隐藏'),
            ('✕', self.quit_app, '退出'),
        ]:
            b = tk.Button(self.toolbar, text=text, command=cmd, **opts)
            b.pack(side='left', padx=1)
            self._tooltip(b, tip)

        self.top_bar.pack(side='top', fill='x')
        self.toolbar.pack(side='top', fill='x')

    def _tooltip(self, widget, text):
        """简单的 hover tooltip"""
        tip = None
        def enter(e):
            nonlocal tip
            tip = tk.Toplevel(widget)
            tip.overrideredirect(True)
            tip.geometry(f'+{e.x_root + 10}+{e.y_root + 10}')
            tk.Label(tip, text=text, bg='#222', fg='#fff', font=self.tb_font,
                     padx=6, pady=2).pack()
        def leave(e):
            nonlocal tip
            if tip:
                tip.destroy()
                tip = None
        widget.bind('<Enter>', enter)
        widget.bind('<Leave>', leave)

    # ---- 滚动同步 ----
    def _on_scrollbar(self, *args):
        self.text.yview(*args)
    def _on_text_scroll(self, first, last):
        self.scrollbar.set(first, last)
        self.gutter.yview_moveto(float(first))
        self.update_gutter()
        self.update_progress()
        self.save_progress_debounced()

    # ---- 主题 ----
    def apply_theme(self):
        t = THEMES[self.state['theme']]
        self.root.config(bg=t['bg'])
        self.text.config(bg=t['bg'], fg=t['fg'], selectbackground=t['sel_bg'])
        self.gutter.config(bg=t['gutter'], fg=t['gutter_fg'])
        self.top_bar.config(bg=t['tb'])
        for child in self.top_bar.winfo_children():
            try: child.config(bg=t['tb'], fg=t['tb_fg'])
            except tk.TclError: pass
        text_color = self.state.get('customText', '#d4d4d4')
        bg_color = self.state.get('customBg', '#1a1a2e')
        self.text_color_btn.config(bg=text_color, fg=self._contrast_fg(text_color))
        self.bg_color_btn.config(bg=bg_color, fg=self._contrast_fg(bg_color))
        self.book_name.config(bg=t['tb'], fg=t['tb_fg'])
        self.toolbar.config(bg=t['tb'])
        self.content.config(bg=t['bg'])
        self.bottom_nav.config(bg=t['tb'])
        self.resize_grip.config(bg=t['bg'])
        for line in self.resize_grip_lines:
            self.resize_grip.itemconfig(line, fill=t['accent'])
        self.progress_lbl.config(bg=t['tb'], fg=t['tb_fg'])
        self.book_name.config(bg=t['tb'], fg=t['tb_fg'])
        self.chapter_panel.config(bg=t['tb'])
        self.chapter_list.config(bg=t['tb'], fg=t['tb_fg'], selectbackground=t['accent'])
        # 工具栏按钮颜色
        for child in self.toolbar.winfo_children():
            try:
                child.config(bg=t['tb'], fg=t['tb_fg'])
            except tk.TclError:
                pass
        for child in self.bottom_nav.winfo_children():
            try:
                if child in (self.prev_btn2, self.next_btn2):
                    child.config(bg=t['accent'], fg='#fff',
                                 activebackground=t['accent'], activeforeground='#fff')
                else:
                    child.config(bg=t['tb'], fg=t['tb_fg'])
            except tk.TclError:
                pass

        is_code = self.state['theme'] == 'code'
        if is_code:
            self.gutter.pack(side='left', fill='y', before=self.text)
            self.gutter.config(font=self.code_tb_font)
            self.text.config(font=self.code_font)
            if not self.immersive:
                self.fake_tabbar.pack(side='top', fill='x', before=self.top_bar)
                self.fake_statusbar.pack(side='bottom', fill='x', before=self.bottom_nav)
            else:
                # 沉浸模式：保留 IDE 伪装外观（标签栏 + 状态栏）
                self.fake_tabbar.pack(side='top', fill='x')
                self.fake_statusbar.pack(side='bottom', fill='x')
        else:
            self.gutter.pack_forget()
            self.text.config(font=self.read_font)
            self.fake_tabbar.pack_forget()
            self.fake_statusbar.pack_forget()

        # 重新渲染当前章节（切换 // 前缀和行号）
        if self.book:
            ratio = self.text.yview()[0]
            self.render_chapter(self.book['chapter_index'])
            self.root.after(50, lambda: self.text.yview_moveto(ratio))

        self.apply_transparency()

    def cycle_theme(self):
        order = ['dark', 'light', 'code', 'custom']
        i = order.index(self.state['theme']) if self.state['theme'] in order else 0
        self.state['theme'] = order[(i + 1) % len(order)]
        self.apply_theme()
        self.apply_transparency()
        self.save_state_debounced()
        names = {'dark': '深色', 'light': '浅色', 'code': '伪装代码', 'custom': '自定义'}
        self.show_hint(f'主题: {names[self.state["theme"]]}', 900)

    # ---- 文件加载 ----
    def open_file(self):
        # 临时取消置顶，否则对话框被挡住
        self.root.attributes('-topmost', False)
        path = filedialog.askopenfilename(
            title='选择 TXT 小说',
            filetypes=[('文本文件', '*.txt'), ('所有文件', '*.*')])
        self.root.attributes('-topmost', True)
        if path:
            self.load_file(path)

    def load_file(self, path):
        try:
            text, encoding = read_txt(path)
        except Exception as e:
            self.show_hint(f'读取失败: {e}', 2000)
            return
        lines, chapters = parse_chapters(text)
        self.book = {'path': path, 'name': pathlib.Path(path).name,
                     'lines': lines, 'chapters': chapters,
                     'chapter_index': 0, 'encoding': encoding}
        self.book_name.config(text=self.book['name'])

        # 恢复进度
        pr = self.progress.get(path)
        start_idx = pr.get('chapter_index', 0) if pr else 0
        start_idx = min(start_idx, len(chapters) - 1)
        scroll_ratio = pr.get('scroll_ratio', 0) if pr else 0

        self.update_chapter_list()
        self.render_chapter(start_idx)
        self.root.after(100, lambda: self.text.yview_moveto(scroll_ratio))
        self.show_hint(f'已加载: {self.book["name"]} · {len(chapters)} 章 · {encoding}', 2000)
        self.state['lastFile'] = path
        self.save_state_debounced()

    # ---- 渲染章节 ----
    def render_chapter(self, idx):
        if not self.book:
            return
        chapters = self.book['chapters']
        idx = max(0, min(idx, len(chapters) - 1))
        self.book['chapter_index'] = idx
        ch = chapters[idx]

        self.text.config(state='normal')
        self.text.delete('1.0', 'end')

        is_code = self.state['theme'] == 'code'
        lines = self.book['lines'][ch['start']:ch['end']]
        content = [line.strip() for line in lines if line.strip()]
        if is_code:
            rendered = ''.join(f'// {line}\n' for line in content)
        else:
            rendered = ''.join(f'{line}\n\n' for line in content)
            self.text.tag_config('all', lmargin1=30, lmargin2=30, spacing1=3, spacing3=7)

        if rendered:
            self.text.insert('1.0', rendered)
        if not is_code:
            self.text.tag_add('all', '1.0', 'end')

        self.text.config(state='disabled')
        self.text.yview_moveto(0)
        self.update_chapter_list()
        self.update_gutter()
        self.update_progress()
        self.save_progress_debounced()

    # ---- 章节列表 ----
    def update_chapter_list(self):
        if not self.book:
            return
        self.chapter_list.delete(0, 'end')
        for ch in self.book['chapters']:
            self.chapter_list.insert('end', ch['title'])
        self.chapter_list.selection_clear(0, 'end')
        idx = self.book['chapter_index']
        if idx < self.chapter_list.size():
            self.chapter_list.selection_set(idx)
            self.chapter_list.see(idx)

    def on_chapter_select(self, event):
        sel = self.chapter_list.curselection()
        if sel:
            self.render_chapter(sel[0])
            self.toggle_chapter_panel(force_close=True)

    def toggle_chapter_panel(self, force_close=False):
        if force_close:
            self.chapter_panel.place_forget()
            return
        if self.chapter_panel.winfo_ismapped():
            self.chapter_panel.place_forget()
        else:
            self.root.update_idletasks()
            w = self.root.winfo_width()
            self.chapter_panel.place(x=w - 222, y=46,
                                     width=220, relheight=1.0, height=-82)
            self.chapter_panel.lift()

    def prev_chapter(self):
        if self.book:
            self.render_chapter(self.book['chapter_index'] - 1)

    def next_chapter(self):
        if self.book:
            self.render_chapter(self.book['chapter_index'] + 1)

    # ---- 行号 ----
    def update_gutter(self):
        if self.state['theme'] != 'code':
            return
        self.gutter.config(state='normal')
        self.gutter.delete('1.0', 'end')
        try:
            first = int(self.text.index('@0,0').split('.')[0])
            top_y = self.text.winfo_height()
            last = int(self.text.index(f'@0,{top_y}').split('.')[0]) if top_y > 0 else first + 30
            total = int(self.text.index('end-1c').split('.')[0])
            nums = []
            for i in range(first, min(last + 2, total + 1)):
                nums.append(f'{i:>4d}')
            self.gutter.insert('1.0', '\n'.join(nums))
        except Exception:
            pass
        self.gutter.config(state='disabled')

    # ---- 进度 ----
    def update_progress(self):
        if not self.book:
            return
        ratio = self.text.yview()[0]
        overall = (self.book['chapter_index'] + ratio) / len(self.book['chapters'])
        self.progress_lbl.config(text=f'阅读进度 {overall * 100:.0f}%')
        ln = int(ratio * max(1, int(self.text.index('end-1c').split('.')[0]))) + 1
        self.fake_ln_lbl.config(text=f'Ln {ln}, Col 1')

    def save_state_debounced(self, delay=350):
        if self.state_save_after_id is not None:
            self.root.after_cancel(self.state_save_after_id)
        self.state_save_after_id = self.root.after(delay, self._write_state)

    def _write_state(self):
        self.state_save_after_id = None
        save_state(self.state)

    def _save_state_now(self):
        if self.state_save_after_id is not None:
            self.root.after_cancel(self.state_save_after_id)
            self.state_save_after_id = None
        save_state(self.state)

    def save_progress_debounced(self):
        if self.progress_save_after_id is not None:
            self.root.after_cancel(self.progress_save_after_id)
        self.progress_save_after_id = self.root.after(600, self._do_save_progress)

    def _save_progress_now(self):
        if self.progress_save_after_id is not None:
            self.root.after_cancel(self.progress_save_after_id)
            self.progress_save_after_id = None
        self._do_save_progress()

    def _do_save_progress(self):
        self.progress_save_after_id = None
        if not self.book:
            return
        ratio = self.text.yview()[0]
        self.progress[self.book['path']] = {
            'chapter_index': self.book['chapter_index'],
            'scroll_ratio': ratio}
        save_progress(self.progress)

    # ---- 字号 / 透明度 ----
    def set_font_size(self, delta):
        self.state['fontSize'] = max(12, min(48, self.state['fontSize'] + delta))
        self.read_font.config(size=self.state['fontSize'])
        self.code_font.config(size=max(11, self.state['fontSize'] - 4))
        self.save_state_debounced()
        self.show_hint(f'字号 {self.state["fontSize"]}px', 800)

    def on_opacity(self, val):
        """滑块控制整个窗口的透明度。"""
        self.state['bgAlpha'] = float(val)
        self.apply_transparency()
        self.save_state_debounced()

    # ---- 颜色选择器 ----
    def _contrast_fg(self, hexcolor):
        """根据背景亮度返回黑或白前景色"""
        try:
            h = hexcolor.lstrip('#')
            r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
            luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
            return '#000' if luminance > 0.55 else '#fff'
        except Exception:
            return '#fff'

    def pick_text_color(self):
        from tkinter import colorchooser
        cur = self.state.get('customText', '#d4d4d4')
        result = colorchooser.askcolor(color=cur, title='选择字体颜色')
        if result and result[1]:
            self.state['customText'] = result[1]
            self._apply_custom_colors()
            self.save_state_debounced()
            self.show_hint('字体颜色已设置', 800)

    def pick_bg_color(self):
        from tkinter import colorchooser
        cur = self.state.get('customBg', '#1a1a2e')
        result = colorchooser.askcolor(color=cur, title='选择背景颜色')
        if result and result[1]:
            self.state['customBg'] = result[1]
            self._apply_custom_colors()
            self.save_state_debounced()
            self.show_hint('背景颜色已设置', 800)

    def _set_custom_theme(self):
        """根据已保存的颜色构建自定义主题。"""
        ct = self.state.get('customText', '#d4d4d4')
        cb = self.state.get('customBg', '#1a1a2e')
        THEMES['custom']['fg'] = ct
        THEMES['custom']['bg'] = cb
        THEMES['custom']['gutter'] = cb
        THEMES['custom']['tb'] = self._shift_color(cb, 20)
        THEMES['custom']['tb_fg'] = self._contrast_fg(cb)
        THEMES['custom']['sel_bg'] = self._shift_color(cb, 40)

    def _apply_custom_colors(self):
        """将自定义颜色应用到 custom 主题并切换"""
        self._set_custom_theme()
        ct = self.state.get('customText', '#d4d4d4')
        cb = self.state.get('customBg', '#1a1a2e')
        self.state['theme'] = 'custom'
        self.text_color_btn.config(bg=ct, fg=self._contrast_fg(ct))
        self.bg_color_btn.config(bg=cb, fg=self._contrast_fg(cb))
        self.apply_theme()
        self.apply_transparency()

    def _shift_color(self, hexcolor, delta):
        """颜色加亮/变暗"""
        try:
            h = hexcolor.lstrip('#')
            r = max(0, min(255, int(h[0:2], 16) + delta))
            g = max(0, min(255, int(h[2:4], 16) + delta))
            b = max(0, min(255, int(h[4:6], 16) + delta))
            return f'#{r:02x}{g:02x}{b:02x}'
        except Exception:
            return hexcolor

    def apply_transparency(self):
        """使用 Tk 的窗口 alpha 属性控制连续的整窗透明度。"""
        try:
            alpha = float(self.state.get('bgAlpha', DEFAULTS['bgAlpha']))
        except (TypeError, ValueError):
            alpha = DEFAULTS['bgAlpha']
        alpha = min(1.0, max(0.15, alpha))
        self.state['bgAlpha'] = alpha
        self.root.attributes('-alpha', alpha)

    def cycle_size(self):
        sizes = [(380, 520), (480, 640), (600, 760), (720, 860)]
        cur = (self.root.winfo_width(), self.root.winfo_height())
        idx = 0
        for i, s in enumerate(sizes):
            if abs(s[0] - cur[0]) < 20:
                idx = i
                break
        nxt = sizes[(idx + 1) % len(sizes)]
        x = self.root.winfo_x()
        y = self.root.winfo_y()
        self.root.geometry(f'{nxt[0]}x{nxt[1]}+{x}+{y}')
        self._schedule_geometry_save()
        self.show_hint(f'{nxt[0]}×{nxt[1]}', 800)

    # ---- 固定 / 沉浸 ----
    def toggle_pin(self):
        self.state['pin'] = not self.state['pin']
        self.save_state_debounced()
        self.show_hint('已固定（暂停自动隐藏）' if self.state['pin'] else '已解除固定', 900)

    def toggle_immersive(self):
        self.immersive = not self.immersive
        is_code = self.state['theme'] == 'code'
        if self.immersive:
            # 始终隐藏顶部状态栏 + 工具栏 + 底部导航
            self.top_bar.pack_forget()
            self.toolbar.pack_forget()
            self.bottom_nav.pack_forget()
            # content 重新 pack 确保占满
            self.content.pack_forget()
            self.content.pack(side='top', fill='both', expand=True)
            # 显示右上角浮动退出按钮（始终可点击，不受透明穿透影响）
            self.immersive_exit_btn.place(relx=1.0, rely=0.0, anchor='ne', x=-4, y=4)
            self.immersive_exit_btn.lift()
            # 沉浸模式改用 -alpha，避免 -transparentcolor 的点击穿透问题
            self.apply_transparency()
            if is_code:
                self.show_hint('伪装阅读（点右上角✕ / F11 / 双击 退出）', 2500)
            else:
                self.text.config(padx=12, pady=6)
                self.show_hint('沉浸模式（点右上角✕ / F11 / 双击 退出）', 2500)
        else:
            self.text.config(padx=26, pady=16)
            self.immersive_exit_btn.place_forget()
            self.scrollbar.pack_forget()
            # 先 forget content，再按正确顺序重新 pack 所有栏
            self.content.pack_forget()
            self.bottom_nav.pack(side='bottom', fill='x')
            self.top_bar.pack(side='top', fill='x')
            self.toolbar.pack(side='top', fill='x')
            self.content.pack(side='top', fill='both', expand=True)
            self.apply_theme()
            self.root.update_idletasks()
            self.show_hint('退出沉浸模式', 800)

    # ---- 提示 ----
    def show_hint(self, msg, duration=1400):
        self.hint_lbl.config(text=msg)
        self.hint_lbl.place(relx=0.5, rely=0.93, anchor='s')
        self.hint_lbl.lower()  # 沉到最底层，不挡双击
        if self.hint_after_id:
            self.root.after_cancel(self.hint_after_id)
        self.hint_after_id = self.root.after(duration, lambda: self.hint_lbl.place_forget())

    # ---- 鼠标自动隐藏 ----
    def start_mouse_check(self):
        self.root.after(100, self.check_mouse)

    def check_mouse(self):
        if not self.state['pin'] and self.root.state() == 'normal':
            try:
                pt = wintypes.POINT()
                user32.GetCursorPos(ctypes.byref(pt))
                px, py = pt.x, pt.y
                gx = self.root.winfo_rootx()
                gy = self.root.winfo_rooty()
                gw = self.root.winfo_width()
                gh = self.root.winfo_height()
                inside = (gx <= px <= gx + gw and gy <= py <= gy + gh)
                if not inside:
                    if self.hide_after_id is None:
                        delay = self.state.get('autoHideDelay', 400)
                        self.hide_after_id = self.root.after(delay, self.do_hide)
                else:
                    if self.hide_after_id is not None:
                        self.root.after_cancel(self.hide_after_id)
                        self.hide_after_id = None
            except Exception:
                pass
        self.root.after(100, self.check_mouse)

    def do_hide(self):
        self.hide_after_id = None
        self._save_progress_now()
        self.root.withdraw()

    # ---- 窗口显示/隐藏 ----
    def toggle_window(self):
        if self.root.state() == 'normal':
            self.root.withdraw()
        else:
            self.show_window()

    def show_window(self):
        self.root.deiconify()
        self.root.lift()
        self.root.attributes('-topmost', True)
        self.root.focus_force()
        if self.hide_after_id:
            self.root.after_cancel(self.hide_after_id)
            self.hide_after_id = None
        self.show_hint('Ctrl+` 或 F9 唤出/隐藏 ｜ Ctrl+Shift+H 老板键', 2500)

    def hide_window(self):
        self._save_progress_now()
        self.root.withdraw()

    # ---- 快捷键 ----
    def on_hotkey(self, key_id):
        if key_id in (HOTKEY_TOGGLE, HOTKEY_TOGGLE2):
            self.toggle_window()
        elif key_id == HOTKEY_BOSS:
            self.hide_window()
        elif key_id == HOTKEY_QUIT:
            self.quit_app()

    # ---- 拖动 ----
    def on_drag_start(self, event):
        self.drag_x = event.x_root - self.root.winfo_rootx()
        self.drag_y = event.y_root - self.root.winfo_rooty()

    def on_drag_motion(self, event):
        x = event.x_root - self.drag_x
        y = event.y_root - self.drag_y
        self.root.geometry(f'+{x}+{y}')
        self._schedule_geometry_save()

    # ---- 缩放 ----
    def on_resize_start(self, event):
        self.resize_w = self.root.winfo_width()
        self.resize_h = self.root.winfo_height()

    def on_resize_motion(self, event):
        w = max(300, self.resize_w + event.x)
        h = max(360, self.resize_h + event.y)
        self.root.geometry(f'{w}x{h}')
        self._schedule_geometry_save()

    def _schedule_geometry_save(self):
        if self.geometry_save_after_id is not None:
            self.root.after_cancel(self.geometry_save_after_id)
        self.geometry_save_after_id = self.root.after(500, self._commit_geometry)

    def _commit_geometry(self):
        self.geometry_save_after_id = None
        self.state['geometry'] = self.root.geometry()
        self.save_state_debounced()

    def _save_geometry(self):
        if self.geometry_save_after_id is not None:
            self.root.after_cancel(self.geometry_save_after_id)
            self.geometry_save_after_id = None
        self.state['geometry'] = self.root.geometry()
        self._save_state_now()

    # ---- 退出 ----
    def quit_app(self):
        self._save_progress_now()
        self._save_geometry()
        try:
            self.root.destroy()
        except Exception:
            pass
        sys.exit(0)

    # ---- 运行 ----
    def run(self):
        self.root.mainloop()


def main():
    app = ReaderApp()
    app.run()


if __name__ == '__main__':
    main()
