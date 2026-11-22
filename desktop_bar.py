"""LEHA Desktop Bar PRO - a Virtual Desktop navigation bar for Windows 10/11.

A lightweight bar pinned to the top edge of the screen (Windows AppBar) that
shows every Virtual Desktop and switches between them with one click. The bar
is rendered through a Win32 layered window (UpdateLayeredWindow) and can be
customized live from Pro Studio, a local-only web UI served on 127.0.0.1.

Requirements: Windows 10 (build 1903+) or Windows 11, Python 3.10+,
Pillow and pyvda (see requirements.txt).

Author: Le Ha
License: MIT
"""

import ctypes
import sys

# Single instance: exit immediately when another copy is already running.
# This check intentionally stays above the heavier imports.
_mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "LEHA_DESKTOP_BAR_SINGLE_INSTANCE_MUTEX")
if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
    sys.exit(0)

import json
import math
import os
import shutil
import subprocess
import threading
import tkinter as tk
import winreg
from ctypes import wintypes
from http.server import BaseHTTPRequestHandler, HTTPServer

from PIL import Image, ImageDraw, ImageFont
from pyvda import VirtualDesktop, get_virtual_desktops

__version__ = "1.0.0"

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

try:
    ctypes.windll.winmm.timeBeginPeriod(1)
except Exception:
    pass

APP_NAME = "[LEHA] Desktop Bar PRO"
APP_AUTHOR = "by Le Ha"
REG_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
FONT_CACHE = {}
TEXT_BBOX_CACHE = {}

FONTS = {
    "regular": "C:/Windows/Fonts/segoeui.ttf",
    "bold": "C:/Windows/Fonts/seguisb.ttf",
    "light": "C:/Windows/Fonts/segoeuil.ttf",
    "italic": "C:/Windows/Fonts/segoeuii.ttf",
    "bold_italic": "C:/Windows/Fonts/seguisbi.ttf",
}

MOD_ALT, MOD_CONTROL, VK_H, HOTKEY_ID = 0x0001, 0x0002, 0x48, 1
ABM_NEW, ABM_REMOVE, ABM_QUERYPOS, ABM_SETPOS, ABE_TOP = 0, 1, 2, 3, 1
GWL_EXSTYLE, WS_EX_LAYERED, WS_EX_TOOLWINDOW, WS_EX_NOACTIVATE = -20, 0x00080000, 0x00000080, 0x08000000
HWND_TOPMOST, SWP_NOMOVE, SWP_NOSIZE, SWP_NOACTIVATE, SWP_SHOWWINDOW = -1, 0x0002, 0x0001, 0x0010, 0x0040
ULW_ALPHA, AC_SRC_OVER, AC_SRC_ALPHA = 0x00000002, 0x00, 0x01

LUXURY_MULTI_PALETTE = [
    {"bg": "#0284c7", "fg": "#ffffff", "accent": "#38bdf8"},
    {"bg": "#059669", "fg": "#ffffff", "accent": "#34d399"},
    {"bg": "#7c3aed", "fg": "#ffffff", "accent": "#c084fc"},
    {"bg": "#ea580c", "fg": "#ffffff", "accent": "#fb923c"},
    {"bg": "#db2777", "fg": "#ffffff", "accent": "#f472b6"},
    {"bg": "#ca8a04", "fg": "#ffffff", "accent": "#facc15"},
    {"bg": "#0d9488", "fg": "#ffffff", "accent": "#2dd4bf"},
    {"bg": "#4f46e5", "fg": "#ffffff", "accent": "#818cf8"},
]

class APPBARDATA(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND), ("uCallbackMessage", wintypes.UINT),
                ("uEdge", wintypes.UINT), ("rc", wintypes.RECT), ("lParam", wintypes.LPARAM)]

class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [("BlendOp", ctypes.c_byte), ("BlendFlags", ctypes.c_byte),
                ("SourceConstantAlpha", ctypes.c_byte), ("AlphaFormat", ctypes.c_byte)]

class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG), ("biYPelsPerMeter", wintypes.LONG),
                ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]

class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]

class SIZE(ctypes.Structure):
    _fields_ = [("cx", wintypes.LONG), ("cy", wintypes.LONG)]

def hex_to_rgba(hex_str, alpha=255):
    h = hex_str.lstrip("#")
    if len(h) != 6:
        return (20, 20, 25, alpha)
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), alpha)

def get_app_dir():
    return os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))

def get_config_path():
    return os.path.join(get_app_dir(), "config.json")

def is_autostart_enabled():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_RUN_KEY, 0, winreg.KEY_READ) as key:
            val, _ = winreg.QueryValueEx(key, APP_NAME)
            return bool(val)
    except Exception:
        return False

def set_autostart(enable: bool):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if enable:
                exe_path = sys.executable if getattr(sys, 'frozen', False) else os.path.abspath(__file__)
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, f'"{exe_path}"')
            else:
                try:
                    winreg.DeleteValue(key, APP_NAME)
                except FileNotFoundError:
                    pass
    except Exception:
        pass

def load_config_data():
    default_cfg = {
        "bar_transparent": True,
        "color_mode": "multi",
        "pill_style": "filled",
        "bg_color": "#0d0d10",
        "border_color": "#2a2a35",
        "mono_idle_bg": "#18181f",
        "mono_idle_text": "#b4b4be",
        "mono_active_bg": "#0284c7",
        "mono_active_text": "#ffffff",
        "mono_accent": "#38bdf8",
        "multi_pills": {str(i+1): LUXURY_MULTI_PALETTE[i % len(LUXURY_MULTI_PALETTE)].copy() for i in range(12)},
        "idle_has_bg": True,
        "active_underline": False,
        "active_border": True,
        "active_pop_padding": 6,
        "hover_zoom": True,
        "show_dot": False,
        "font_weight": "bold",
        "font_italic": False,
        "text_case": "normal",
        "layout_mode": "center",
        "pill_size": "normal",
        "pill_gap": 10,
        "pill_radius": 9,
        "height": 32,
        "opacity": 0.94,
        "auto_hide_fullscreen": False
    }
    try:
        p = get_config_path()
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                default_cfg.update(json.load(f))
    except Exception:
        pass
    default_cfg["autostart"] = is_autostart_enabled()
    return default_cfg

SETTINGS_HTML = """<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<title>[LEHA] Desktop Bar Studio</title>
<style>
  :root{--bg:#0e0e11;--card:#16161a;--border:#26262e;--text:#f4f4f6;--muted:#8b8b96;--accent:#38bdf8;--accent-bg:rgba(56,189,248,0.14)}
  *{box-sizing:border-box;margin:0;padding:0;font-family:'Segoe UI',system-ui,sans-serif;user-select:none}
  body{background:var(--bg);color:var(--text);height:100vh;display:flex;flex-direction:column;overflow:hidden}
  .header{padding:14px 22px;display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--border)}
  .title-wrap{display:flex;align-items:center;gap:10px}
  .badge{background:var(--accent-bg);color:var(--accent);font-size:11px;font-weight:700;padding:3px 8px;border-radius:6px}
  .title{font-size:15px;font-weight:600}
  .tabs{display:flex;gap:4px;padding:10px 22px 0;border-bottom:1px solid var(--border)}
  .tab{padding:9px 14px;font-size:13px;font-weight:500;color:var(--muted);cursor:pointer;border-bottom:2px solid transparent;transition:0.15s;border-radius:8px 8px 0 0}
  .tab:hover{color:var(--text);background:rgba(255,255,255,0.03)}
  .tab.active{color:var(--accent);border-bottom-color:var(--accent);font-weight:600}
  .content{flex:1;overflow-y:auto;padding:18px 22px 28px;display:flex;flex-direction:column;gap:14px}
  .content::-webkit-scrollbar{width:6px}.content::-webkit-scrollbar-thumb{background:#2e2e38;border-radius:99px}
  .page{display:none;flex-direction:column;gap:14px}.page.active{display:flex}
  .card{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:14px 16px;display:flex;flex-direction:column;gap:12px}
  .card-title{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.7px;color:var(--muted)}
  .row{display:flex;justify-content:space-between;align-items:center;gap:12px}
  .row-label{font-size:13px;color:var(--text)}.row-sub{font-size:11px;color:var(--muted);margin-top:2px}
  .seg{display:inline-flex;background:#0a0a0c;padding:3px;border-radius:8px;border:1px solid var(--border)}
  .seg-btn{padding:5px 12px;font-size:12px;font-weight:500;color:var(--muted);border-radius:6px;cursor:pointer;transition:0.15s}
  .seg-btn.active{background:#26262f;color:var(--accent);font-weight:600}
  .switch{position:relative;width:40px;height:22px;background:#2a2a34;border-radius:99px;cursor:pointer;transition:0.2s;flex-shrink:0}
  .switch.on{background:var(--accent)}
  .switch::after{content:'';position:absolute;top:3px;left:3px;width:16px;height:16px;background:#fff;border-radius:50%;transition:0.2s}
  .switch.on::after{left:21px;background:#09090b}
  .color-group{display:flex;align-items:center;gap:8px}
  .color-box{position:relative;width:28px;height:28px;border-radius:7px;border:1px solid rgba(255,255,255,0.18);overflow:hidden;cursor:pointer;flex-shrink:0}
  .color-box input[type="color"]{position:absolute;inset:-6px;width:42px;height:42px;border:none;cursor:pointer;opacity:0}
  .hex-tag{font-family:Consolas,monospace;font-size:11px;color:var(--muted);width:58px}
  .presets{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}
  .preset-btn{padding:8px 10px;border-radius:8px;border:1px solid var(--border);background:#1c1c22;color:var(--text);font-size:12px;font-weight:500;cursor:pointer;text-align:center;transition:0.15s}
  .preset-btn:hover{border-color:var(--accent);background:#22222a}
  .slider-wrap{display:flex;align-items:center;gap:12px;width:220px}
  input[type="range"]{-webkit-appearance:none;flex:1;height:5px;background:#2a2a35;border-radius:99px;outline:none}
  input[type="range"]::-webkit-slider-thumb{-webkit-appearance:none;width:15px;height:15px;border-radius:50%;background:var(--accent);cursor:pointer}
  .val-badge{font-size:12px;font-weight:600;color:var(--accent);width:42px;text-align:right}
  .text-input{background:#0a0a0c;border:1px solid var(--border);color:var(--text);padding:8px 12px;border-radius:8px;font-size:13px;width:100%;outline:none}
  .text-input:focus{border-color:var(--accent)}
  .btn-primary{background:var(--accent);color:#09090b;font-weight:600;font-size:13px;border:none;padding:10px 16px;border-radius:8px;cursor:pointer;width:100%}
  .btn-primary:hover{filter:brightness(1.1)}
  .multi-row{display:flex;justify-content:space-between;align-items:center;padding:8px 10px;background:#111115;border-radius:8px;border:1px solid #202028}
  .screen-name-tag{font-size:13px;font-weight:600;color:var(--text)}
</style>
</head>
<body>
<div class="header">
  <div class="title-wrap"><span class="badge">RETINA 120FPS</span><span class="title">[LEHA] Desktop Bar PRO</span></div>
  <span style="font-size:11px;color:var(--muted)">by Le Ha</span>
</div>
<div class="tabs">
  <div class="tab active" onclick="switchTab('active',this)">Màn Đang Chọn & Hiệu Ứng</div>
  <div class="tab" onclick="switchTab('style',this)">Màu Sắc & Nền</div>
  <div class="tab" onclick="switchTab('layout',this)">Bố Cục & Chữ</div>
  <div class="tab" onclick="switchTab('names',this)">Tên Màn & Hệ Thống</div>
</div>
<div class="content">
  <div id="page-active" class="page active">
    <div class="card">
      <div class="card-title">Hiệu ứng động & Phân biệt màn đang chọn</div>
      <div class="row"><div><div class="row-label">Hiệu ứng phóng to nhẹ khi rê chuột (macOS Dock)</div><div class="row-sub">Viên thuốc phóng to siêu mượt khi lướt chuột</div></div><div class="switch" id="sw-hover_zoom" onclick="toggleOpt('hover_zoom')"></div></div>
      <div class="row"><div><div class="row-label">Thanh gạch sáng chỉ báo dưới đáy viên đang chọn</div><div class="row-sub">Hiển thị vạch sáng rực dưới màn hình đang mở</div></div><div class="switch" id="sw-active_underline" onclick="toggleOpt('active_underline')"></div></div>
      <div class="row"><div><div class="row-label">Viền sáng nổi bao quanh viên đang chọn</div><div class="row-sub">Tạo khung viền mượt mà giúp nhận diện tức thì</div></div><div class="switch" id="sw-active_border" onclick="toggleOpt('active_border')"></div></div>
      <div class="row"><div><div class="row-label">Tự động nở rộng viên đang chọn</div></div><div class="slider-wrap"><input type="range" id="sl-active_pop_padding" min="0" max="18" step="2" oninput="setSlider('active_pop_padding',parseInt(this.value),'px')"><span class="val-badge" id="val-active_pop_padding"></span></div></div>
    </div>
    <div class="card">
      <div class="card-title">Màu sắc của các màn CHƯA chọn (Inactive / Idle)</div>
      <div class="row"><div><div class="row-label">Giữ khung nền cho các màn chưa chọn</div><div class="row-sub">Tắt đi để các màn chưa chọn chỉ hiện chữ siêu mịn trên nền</div></div><div class="switch" id="sw-idle_has_bg" onclick="toggleOpt('idle_has_bg')"></div></div>
      <div class="row"><span class="row-label">Màu nền các màn chưa chọn</span><div class="color-group" id="cg-mono_idle_bg"></div></div>
      <div class="row"><span class="row-label">Màu chữ các màn chưa chọn</span><div class="color-group" id="cg-mono_idle_text"></div></div>
    </div>
  </div>
  <div id="page-style" class="page">
    <div class="card">
      <div class="card-title">Mẫu phối màu nhanh (Presets)</div>
      <div class="presets">
        <div class="preset-btn" onclick="applyPreset('floating_multi')">Viên nổi Đa màu</div>
        <div class="preset-btn" onclick="applyPreset('floating_dark')">Viên nổi Tối giản</div>
        <div class="preset-btn" onclick="applyPreset('obsidian')">Thanh đen Obsidian</div>
        <div class="preset-btn" onclick="applyPreset('catppuccin')">Catppuccin</div>
        <div class="preset-btn" onclick="applyPreset('emerald')">Cyber Mint</div>
        <div class="preset-btn" onclick="applyPreset('light')">Apple Light</div>
      </div>
    </div>
    <div class="card">
      <div class="card-title">Nền thanh bar & Chế độ màu</div>
      <div class="row"><div><div class="row-label">Nền thanh bar trong suốt 100%</div><div class="row-sub">Chữ và viền hòa mượt vào hình nền không viền đen</div></div><div class="switch" id="sw-bar_transparent" onclick="toggleOpt('bar_transparent')"></div></div>
      <div class="row" id="row-bg-color"><span class="row-label">Màu nền thanh bar (khi tắt trong suốt)</span><div class="color-group" id="cg-bg_color"></div></div>
      <div class="row"><span class="row-label">Chế độ màu khi Active</span><div class="seg" id="seg-color_mode"><div class="seg-btn" data-val="multi" onclick="setOpt('color_mode','multi')">Đa màu từng màn</div><div class="seg-btn" data-val="mono" onclick="setOpt('color_mode','mono')">Đơn màu</div></div></div>
    </div>
    <div id="dynamic-colors-area"></div>
  </div>
  <div id="page-layout" class="page">
    <div class="card">
      <div class="card-title">Kiểu dáng & Định dạng chữ</div>
      <div class="row"><span class="row-label">Phong cách Pill</span><div class="seg" id="seg-pill_style"><div class="seg-btn" data-val="filled" onclick="setOpt('pill_style','filled')">Có nền</div><div class="seg-btn" data-val="outline" onclick="setOpt('pill_style','outline')">Chỉ viền</div><div class="seg-btn" data-val="minimal" onclick="setOpt('pill_style','minimal')">Tối giản chữ</div></div></div>
      <div class="row"><span class="row-label">Chấm tròn trạng thái</span><div class="switch" id="sw-show_dot" onclick="toggleOpt('show_dot')"></div></div>
      <div class="row"><span class="row-label">Độ đậm chữ</span><div class="seg" id="seg-font_weight"><div class="seg-btn" data-val="light" onclick="setOpt('font_weight','light')">In nhạt</div><div class="seg-btn" data-val="regular" onclick="setOpt('font_weight','regular')">Thường</div><div class="seg-btn" data-val="bold" onclick="setOpt('font_weight','bold')">In đậm</div></div></div>
      <div class="row"><span class="row-label">Chữ in nghiêng (Italic)</span><div class="switch" id="sw-font_italic" onclick="toggleOpt('font_italic')"></div></div>
      <div class="row"><span class="row-label">Viết hoa / thường</span><div class="seg" id="seg-text_case"><div class="seg-btn" data-val="normal" onclick="setOpt('text_case','normal')">Mặc định</div><div class="seg-btn" data-val="upper" onclick="setOpt('text_case','upper')">IN HOA</div><div class="seg-btn" data-val="lower" onclick="setOpt('text_case','lower')">chữ thường</div></div></div>
    </div>
    <div class="card">
      <div class="card-title">Căn lề, Khoảng cách & Kích thước</div>
      <div class="row"><span class="row-label">Căn lề các viên</span><div class="seg" id="seg-layout_mode"><div class="seg-btn" data-val="left" onclick="setOpt('layout_mode','left')">Trái</div><div class="seg-btn" data-val="center" onclick="setOpt('layout_mode','center')">Giữa</div><div class="seg-btn" data-val="stretch" onclick="setOpt('layout_mode','stretch')">Chia đều 100%</div></div></div>
      <div class="row"><span class="row-label">Độ rộng cơ bản</span><div class="seg" id="seg-pill_size"><div class="seg-btn" data-val="compact" onclick="setOpt('pill_size','compact')">Gọn</div><div class="seg-btn" data-val="normal" onclick="setOpt('pill_size','normal')">Vừa</div><div class="seg-btn" data-val="wide" onclick="setOpt('pill_size','wide')">Dài</div></div></div>
      <div class="row"><span class="row-label">Khoảng cách giữa các viên</span><div class="slider-wrap"><input type="range" id="sl-pill_gap" min="4" max="28" step="2" oninput="setSlider('pill_gap',parseInt(this.value),'px')"><span class="val-badge" id="val-pill_gap"></span></div></div>
      <div class="row"><span class="row-label">Độ bo tròn góc</span><div class="slider-wrap"><input type="range" id="sl-pill_radius" min="0" max="15" step="1" oninput="setSlider('pill_radius',parseInt(this.value),'px')"><span class="val-badge" id="val-pill_radius"></span></div></div>
      <div class="row"><span class="row-label">Chiều cao thanh bar</span><div class="slider-wrap"><input type="range" id="sl-height" min="26" max="44" step="2" oninput="setSlider('height',parseInt(this.value),'px')"><span class="val-badge" id="val-height"></span></div></div>
      <div class="row"><span class="row-label">Độ đậm của các viên</span><div class="slider-wrap"><input type="range" id="sl-opacity" min="0.3" max="1.0" step="0.05" oninput="setSlider('opacity',parseFloat(this.value),'%')"><span class="val-badge" id="val-opacity"></span></div></div>
    </div>
  </div>
  <div id="page-names" class="page">
    <div class="card">
      <div class="card-title">Hành vi hệ thống</div>
      <div class="row"><div><div class="row-label">Tự động khởi động cùng Windows</div><div class="row-sub">Bật thanh bar ngay khi mở máy</div></div><div class="switch" id="sw-autostart" onclick="toggleOpt('autostart')"></div></div>
      <div class="row"><div><div class="row-label">Tự ẩn khi chơi Game / Xem phim Fullscreen</div><div class="row-sub">Tự động ẩn khi có ứng dụng tràn viền</div></div><div class="switch" id="sw-auto_hide_fullscreen" onclick="toggleOpt('auto_hide_fullscreen')"></div></div>
    </div>
    <div class="card">
      <div class="card-title">Đổi tên các Virtual Desktop</div>
      <div id="desktop-names-list" style="display:flex;flex-direction:column;gap:8px"></div>
      <button class="btn-primary" onclick="saveDesktopNames()" style="margin-top:6px">Lưu Tên Các Màn Hình</button>
      <div id="save-toast" style="font-size:12px;color:#34d399;text-align:center;display:none">✓ Đã cập nhật tên thành công!</div>
    </div>
  </div>
</div>
<script>
  let cfg={},desktops=[];
  async function postJSON(u,d){await fetch(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(d)})}
  function switchTab(id,el){document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));el.classList.add('active');document.getElementById('page-'+id).classList.add('active')}
  function makeColorPicker(cid,hex,cb){const el=document.getElementById(cid);if(!el)return;el.innerHTML=`<span class="hex-tag">${hex.toUpperCase()}</span><div class="color-box" style="background:${hex}"><input type="color" value="${hex}"></div>`;const inp=el.querySelector('input'),box=el.querySelector('.color-box'),tag=el.querySelector('.hex-tag');inp.addEventListener('input',e=>{const v=e.target.value;box.style.background=v;tag.textContent=v.toUpperCase();cb(v)})}
  function syncUI(){
    ['color_mode','pill_style','font_weight','text_case','layout_mode','pill_size'].forEach(k=>{const s=document.getElementById('seg-'+k);if(s)s.querySelectorAll('.seg-btn').forEach(b=>b.classList.toggle('active',b.dataset.val===cfg[k]))});
    ['bar_transparent','idle_has_bg','active_underline','active_border','hover_zoom','show_dot','font_italic','autostart','auto_hide_fullscreen'].forEach(k=>{const sw=document.getElementById('sw-'+k);if(sw)sw.classList.toggle('on',!!cfg[k])});
    document.getElementById('row-bg-color').style.opacity=cfg.bar_transparent?'0.4':'1';
    document.getElementById('sl-active_pop_padding').value=cfg.active_pop_padding??6;document.getElementById('val-active_pop_padding').textContent='+'+(cfg.active_pop_padding??6)+'px';
    document.getElementById('sl-pill_gap').value=cfg.pill_gap??10;document.getElementById('val-pill_gap').textContent=(cfg.pill_gap??10)+'px';
    document.getElementById('sl-pill_radius').value=cfg.pill_radius;document.getElementById('val-pill_radius').textContent=cfg.pill_radius+'px';
    document.getElementById('sl-height').value=cfg.height;document.getElementById('val-height').textContent=cfg.height+'px';
    document.getElementById('sl-opacity').value=cfg.opacity;document.getElementById('val-opacity').textContent=Math.round(cfg.opacity*100)+'%';
    makeColorPicker('cg-bg_color',cfg.bg_color,v=>updateCfg({bg_color:v}));
    makeColorPicker('cg-mono_idle_bg',cfg.mono_idle_bg,v=>updateCfg({mono_idle_bg:v}));
    makeColorPicker('cg-mono_idle_text',cfg.mono_idle_text,v=>updateCfg({mono_idle_text:v}));
    renderDynamicColors();
  }
  function renderDynamicColors(){
    const area=document.getElementById('dynamic-colors-area');
    if(cfg.color_mode==='mono'){
      area.innerHTML=`<div class="card"><div class="card-title">Màu sắc khi ĐANG CHỌN (Đơn màu)</div><div class="row"><span class="row-label">Nền viên đang chọn</span><div class="color-group" id="cg-mono_active_bg"></div></div><div class="row"><span class="row-label">Chữ viên đang chọn</span><div class="color-group" id="cg-mono_active_text"></div></div><div class="row"><span class="row-label">Viền sáng & Gạch chân</span><div class="color-group" id="cg-mono_accent"></div></div></div>`;
      ['mono_active_bg','mono_active_text','mono_accent'].forEach(k=>makeColorPicker('cg-'+k,cfg[k],v=>updateCfg({[k]:v})));
    }else{
      let h=`<div class="card"><div class="card-title">Màu riêng từng màn khi ĐANG CHỌN (Nền • Chữ • Sáng)</div>`;
      desktops.forEach(d=>{const k=String(d.num),p=cfg.multi_pills[k]||{bg:'#0284c7',fg:'#ffffff',accent:'#38bdf8'};h+=`<div class="multi-row"><span class="screen-name-tag">${d.name}</span><div style="display:flex;align-items:center;gap:10px"><span style="font-size:11px;color:var(--muted)">Nền</span><div class="color-box" style="background:${p.bg}"><input type="color" value="${p.bg}" oninput="setMultiColor('${k}','bg',this)"></div><span style="font-size:11px;color:var(--muted)">Chữ</span><div class="color-box" style="background:${p.fg}"><input type="color" value="${p.fg}" oninput="setMultiColor('${k}','fg',this)"></div><span style="font-size:11px;color:var(--muted)">Sáng</span><div class="color-box" style="background:${p.accent||p.fg}"><input type="color" value="${p.accent||p.fg}" oninput="setMultiColor('${k}','accent',this)"></div></div></div>`});
      area.innerHTML=h+`</div>`;
    }
  }
  function setMultiColor(k,p,el){const v=el.value;el.parentElement.style.background=v;if(!cfg.multi_pills[k])cfg.multi_pills[k]={bg:'#0284c7',fg:'#ffffff',accent:'#38bdf8'};cfg.multi_pills[k][p]=v;postJSON('/api/save_config',cfg)}
  function setOpt(k,v){cfg[k]=v;syncUI();postJSON('/api/save_config',cfg)}
  function toggleOpt(k){cfg[k]=!cfg[k];syncUI();postJSON('/api/save_config',cfg)}
  function setSlider(k,v,u){cfg[k]=v;const px=(k==='active_pop_padding')?'+':'';document.getElementById('val-'+k).textContent=(u==='%')?Math.round(v*100)+'%':px+v+u;postJSON('/api/save_config',cfg)}
  function updateCfg(p){Object.assign(cfg,p);postJSON('/api/save_config',cfg)}
  function applyPreset(n){
    if(n==='floating_multi')Object.assign(cfg,{bar_transparent:true,color_mode:'multi',pill_style:'filled',idle_has_bg:true,active_underline:false,active_border:true,mono_idle_bg:'#18181f',mono_idle_text:'#b4b4be'});
    else if(n==='floating_dark')Object.assign(cfg,{bar_transparent:true,color_mode:'mono',pill_style:'filled',idle_has_bg:true,active_underline:false,active_border:true,mono_idle_bg:'#18181f',mono_idle_text:'#b4b4be',mono_active_bg:'#27272a',mono_active_text:'#ffffff',mono_accent:'#38bdf8'});
    else if(n==='obsidian')Object.assign(cfg,{bar_transparent:false,bg_color:'#0d0d10',border_color:'#222226',pill_style:'filled',idle_has_bg:true,mono_idle_bg:'#16161a',mono_idle_text:'#9ca3af',mono_active_bg:'#0284c7',mono_active_text:'#ffffff',mono_accent:'#38bdf8'});
    else if(n==='catppuccin')Object.assign(cfg,{bar_transparent:false,bg_color:'#11111b',border_color:'#1e1e2e',pill_style:'filled',idle_has_bg:true,mono_idle_bg:'#181825',mono_idle_text:'#a6adc8',mono_active_bg:'#cba6f7',mono_active_text:'#11111b',mono_accent:'#f5c2e7'});
    else if(n==='emerald')Object.assign(cfg,{bar_transparent:true,pill_style:'outline',idle_has_bg:true,active_underline:false,mono_idle_bg:'#0f1f1b',mono_idle_text:'#6ee7b7',mono_active_bg:'#059669',mono_active_text:'#ffffff',mono_accent:'#34d399'});
    else if(n==='light')Object.assign(cfg,{bar_transparent:false,bg_color:'#f4f4f5',border_color:'#e4e4e7',pill_style:'filled',idle_has_bg:true,mono_idle_bg:'#e4e4e7',mono_idle_text:'#52525b',mono_active_bg:'#0284c7',mono_active_text:'#ffffff',mono_accent:'#0369a1'});
    syncUI();postJSON('/api/save_config',cfg);
  }
  function renderNamesList(){document.getElementById('desktop-names-list').innerHTML=desktops.map(d=>`<input class="text-input" data-num="${d.num}" value="${d.name}" placeholder="Tên màn hình ${d.num}">`).join('')}
  async function saveDesktopNames(){const p=[];document.querySelectorAll('#desktop-names-list input').forEach(i=>p.push({num:parseInt(i.dataset.num),name:i.value.trim()}));await postJSON('/api/rename_desktops',p);const t=document.getElementById('save-toast');t.style.display='block';setTimeout(()=>t.style.display='none',2000)}
  window.addEventListener('DOMContentLoaded',async()=>{const r=await fetch('/api/init'),d=await r.json();cfg=d.config;desktops=d.desktops;syncUI();renderNamesList()});
</script>
</body>
</html>
"""

class StudioRequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(SETTINGS_HTML.encode("utf-8"))
        elif self.path == "/api/init":
            desktops = []
            try:
                for d in get_virtual_desktops():
                    n = d.number
                    name = d.name if (d.name and d.name.strip()) else f"Desktop {n}"
                    desktops.append({"num": n, "name": name})
            except Exception:
                desktops = [{"num": 1, "name": "Desktop 1"}]
            payload = json.dumps({"config": load_config_data(), "desktops": desktops}, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(payload)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        data = json.loads(self.rfile.read(length).decode("utf-8"))
        if self.path == "/api/save_config":
            if "autostart" in data:
                set_autostart(bool(data["autostart"]))
            try:
                with open(get_config_path(), "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
            except Exception:
                pass
            if hasattr(self.server, "on_config_saved"):
                self.server.on_config_saved()
        elif self.path == "/api/rename_desktops":
            for item in data:
                if item.get("name"):
                    try:
                        VirtualDesktop(item["num"]).rename(item["name"])
                    except Exception:
                        pass
            if hasattr(self.server, "on_config_saved"):
                self.server.on_config_saved()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok":true}')

class SystemWorkspacesBar:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title(f"{APP_NAME} ({APP_AUTHOR})")
        self.running = True
        self.manual_hidden = False
        self.fullscreen_hidden = False
        self.last_state = None
        self.force_redraw = False
        self.appbar_registered = False
        self.last_reserved_rect = None
        self.pill_hitboxes = []
        self.optimistic_active_num = None
        self.optimistic_ticks = 0
        self.studio_port = None
        self.hover_x = None
        self.hover_scales = {}
        self.is_animating = False
        self._last_sys_check = 0
        self._cached_curr = 1
        self._cached_desktops = ((1, "Desktop 1"),)
        self._config_str = ""
        self._dib_cache = None

        self.config = load_config_data()
        self._config_str = json.dumps(self.config, sort_keys=True)

        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.bind("<Button-1>", self.on_bar_click)
        self.root.bind("<Button-3>", lambda e: self.open_settings_popup())
        self.root.bind("<Motion>", self.on_mouse_move)
        self.root.bind("<Leave>", self.on_mouse_leave)

        self.root.update_idletasks()
        self.setup_layered_window()
        self.start_local_studio_server()
        self.update_loop()

    def get_hwnd(self):
        hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
        return hwnd if hwnd != 0 else self.root.winfo_id()

    def setup_layered_window(self):
        user32 = ctypes.windll.user32
        hwnd = self.get_hwnd()
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, (style | WS_EX_LAYERED | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE) & ~0x20)

    def _ensure_dib(self, w, h):
        if self._dib_cache and self._dib_cache[0] == w and self._dib_cache[1] == h:
            return self._dib_cache
        if self._dib_cache:
            _, _, mem_dc, h_bitmap, old_bmp, _ = self._dib_cache
            ctypes.windll.gdi32.SelectObject(mem_dc, old_bmp)
            ctypes.windll.gdi32.DeleteObject(h_bitmap)
            ctypes.windll.gdi32.DeleteDC(mem_dc)

        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32
        screen_dc = user32.GetDC(0)
        mem_dc = gdi32.CreateCompatibleDC(screen_dc)
        user32.ReleaseDC(0, screen_dc)

        bmi = BITMAPINFOHEADER()
        bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.biWidth = w
        bmi.biHeight = -h
        bmi.biPlanes = 1
        bmi.biBitCount = 32
        bmi.biCompression = 0

        bits_ptr = ctypes.c_void_p()
        h_bitmap = gdi32.CreateDIBSection(mem_dc, ctypes.byref(bmi), 0, ctypes.byref(bits_ptr), None, 0)
        old_bmp = gdi32.SelectObject(mem_dc, h_bitmap)
        self._dib_cache = (w, h, mem_dc, h_bitmap, old_bmp, bits_ptr)
        return self._dib_cache

    def push_rgba_to_layered_window(self, pil_rgba_img, left, top):
        w, h = pil_rgba_img.size
        r, g, b, a = pil_rgba_img.split()
        global_alpha = self.config.get("opacity", 0.94)
        if global_alpha < 0.99:
            a = a.point(lambda p: int(p * global_alpha))
        black = Image.new("L", (w, h), 0)
        r = Image.composite(r, black, a)
        g = Image.composite(g, black, a)
        b = Image.composite(b, black, a)
        bgra_premul = Image.merge("RGBA", (b, g, r, a)).tobytes()

        _, _, mem_dc, _, _, bits_ptr = self._ensure_dib(w, h)
        ctypes.memmove(bits_ptr, bgra_premul, len(bgra_premul))

        user32 = ctypes.windll.user32
        hwnd = self.get_hwnd()
        screen_dc = user32.GetDC(0)
        pt_dst = POINT(left, top)
        sz = SIZE(w, h)
        pt_src = POINT(0, 0)
        blend = BLENDFUNCTION(AC_SRC_OVER, 0, 255, AC_SRC_ALPHA)

        user32.UpdateLayeredWindow(hwnd, screen_dc, ctypes.byref(pt_dst), ctypes.byref(sz),
                                   mem_dc, ctypes.byref(pt_src), 0, ctypes.byref(blend), ULW_ALPHA)
        user32.ReleaseDC(0, screen_dc)

    def on_mouse_move(self, event):
        if not self.config.get("hover_zoom", True):
            return
        was_idle = (self.hover_x is None and not self.is_animating)
        self.hover_x = event.x
        if was_idle:
            self.tick_now()

    def on_mouse_leave(self, event):
        if self.hover_x is not None:
            self.hover_x = None
            self.tick_now()

    def enforce_topmost_pin(self):
        if self.manual_hidden or self.fullscreen_hidden:
            return
        user32 = ctypes.windll.user32
        hwnd = self.get_hwnd()
        if not user32.IsWindowVisible(hwnd):
            user32.ShowWindow(hwnd, 4)
        user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW)

    def is_foreground_fullscreen(self):
        if not self.config.get("auto_hide_fullscreen", False):
            return False
        user32 = ctypes.windll.user32
        fg_hwnd = user32.GetForegroundWindow()
        if not fg_hwnd or fg_hwnd == self.get_hwnd():
            return False
        class_buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(fg_hwnd, class_buf, 256)
        if class_buf.value in ("Progman", "WorkerW", "Shell_TrayWnd"):
            return False
        rect = wintypes.RECT()
        if not user32.GetWindowRect(fg_hwnd, ctypes.byref(rect)):
            return False
        return rect.left <= 0 and rect.top <= 0 and rect.right >= user32.GetSystemMetrics(0) and rect.bottom >= user32.GetSystemMetrics(1)

    def start_local_studio_server(self):
        server = HTTPServer(("127.0.0.1", 0), StudioRequestHandler)
        server.on_config_saved = self.reload_config_immediately
        self.studio_port = server.server_address[1]
        threading.Thread(target=server.serve_forever, daemon=True).start()

    def reload_config_immediately(self):
        def _apply():
            self.config = load_config_data()
            self._config_str = json.dumps(self.config, sort_keys=True)
            TEXT_BBOX_CACHE.clear()
            self.force_redraw = True
        self.root.after(150, _apply)

    def reserve_screen_space(self, left, top, width, height):
        rect_tuple = (left, top, width, height)
        if rect_tuple == self.last_reserved_rect and self.appbar_registered:
            return
        hwnd = self.get_hwnd()
        abd = APPBARDATA()
        abd.cbSize = ctypes.sizeof(APPBARDATA)
        abd.hWnd = hwnd
        abd.uEdge = ABE_TOP
        if not self.appbar_registered:
            ctypes.windll.shell32.SHAppBarMessage(ABM_NEW, ctypes.byref(abd))
            self.appbar_registered = True
        abd.rc.left, abd.rc.top, abd.rc.right, abd.rc.bottom = left, top, left + width, top + height
        ctypes.windll.shell32.SHAppBarMessage(ABM_QUERYPOS, ctypes.byref(abd))
        abd.rc.bottom = abd.rc.top + height
        ctypes.windll.shell32.SHAppBarMessage(ABM_SETPOS, ctypes.byref(abd))
        self.last_reserved_rect = rect_tuple
        self.root.geometry(f"{width}x{height}+{abd.rc.left}+{abd.rc.top}")

    def release_screen_space(self):
        if self.appbar_registered:
            hwnd = self.get_hwnd()
            abd = APPBARDATA(cbSize=ctypes.sizeof(APPBARDATA), hWnd=hwnd)
            ctypes.windll.shell32.SHAppBarMessage(ABM_REMOVE, ctypes.byref(abd))
            self.appbar_registered = False
            self.last_reserved_rect = None

    def get_primary_monitor_info(self):
        user32 = ctypes.windll.user32
        width = user32.GetSystemMetrics(0)
        try:
            scale = user32.GetDpiForSystem() / 96.0
        except Exception:
            scale = 1.0
        return 0, 0, width, scale

    def toggle_visibility(self, icon=None, item=None):
        def _toggle():
            self.manual_hidden = not self.manual_hidden
            if self.manual_hidden:
                self.release_screen_space()
                self.root.withdraw()
            else:
                self.root.deiconify()
                self.enforce_topmost_pin()
                self.force_redraw = True
        self.root.after(150, _toggle)

    def listen_hotkey(self):
        user32 = ctypes.windll.user32
        if not user32.RegisterHotKey(None, HOTKEY_ID, MOD_CONTROL | MOD_ALT, VK_H):
            return
        try:
            msg = wintypes.MSG()
            while self.running:
                if user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                    if msg.message == 0x0312 and msg.wParam == HOTKEY_ID:
                        self.toggle_visibility()
                ctypes.windll.kernel32.Sleep(50)
        finally:
            user32.UnregisterHotKey(None, HOTKEY_ID)

    def get_all_desktops_data(self):
        try:
            curr_num = VirtualDesktop.current().number
            items = [(d.number, d.name if (d.name and d.name.strip()) else f"Desktop {d.number}") for d in get_virtual_desktops()]
            return curr_num, tuple(items)
        except Exception:
            return 1, ((1, "Desktop 1"),)

    def on_bar_click(self, event):
        for x1, y1, x2, y2, target_num in self.pill_hitboxes:
            if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                self.optimistic_active_num = target_num
                self.optimistic_ticks = 4
                self.force_redraw = True
                self.tick_now()
                threading.Thread(target=lambda num=target_num: VirtualDesktop(num).go(), daemon=True).start()
                break

    def open_settings_popup(self):
        url = f"http://127.0.0.1:{self.studio_port}/"
        edge_paths = [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            shutil.which("msedge")
        ]
        edge_exe = next((p for p in edge_paths if p and os.path.exists(p)), None)
        if edge_exe:
            profile_dir = os.path.join(get_app_dir(), "studio_profile")
            subprocess.Popen([
                edge_exe,
                f"--app={url}",
                "--window-size=600,660",
                f"--user-data-dir={profile_dir}",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-extensions",
                "--disable-sync",
                "--disable-default-apps",
                "--disable-features=msEdgeAccountConsistency,msEdgeSidebarV2",
                "--disable-background-mode"
            ], creationflags=0x00000008, close_fds=True)
        else:
            os.startfile(url)

    def resolve_font(self, size, is_active):
        cfg = self.config
        w = cfg.get("font_weight", "bold")
        it = cfg.get("font_italic", False)
        if is_active and w == "light":
            w = "bold"
        key = (size, w, it)
        if key in FONT_CACHE:
            return FONT_CACHE[key], key
        if it and w == "bold":
            path = FONTS["bold_italic"]
        elif it:
            path = FONTS["italic"]
        elif w == "light":
            path = FONTS["light"]
        elif w == "bold":
            path = FONTS["bold"]
        else:
            path = FONTS["regular"]
        try:
            f = ImageFont.truetype(path, size)
        except Exception:
            f = ImageFont.load_default()
        FONT_CACHE[key] = f
        return f, key

    def get_cached_bbox(self, draw, text, font, font_key):
        k = (text, font_key)
        res = TEXT_BBOX_CACHE.get(k)
        if res is None:
            res = draw.textbbox((0, 0), text, font=font)
            TEXT_BBOX_CACHE[k] = res
        return res

    def apply_text_case(self, text):
        c = self.config.get("text_case", "normal")
        return text.upper() if c == "upper" else (text.lower() if c == "lower" else text)

    def get_pill_visuals(self, d_num, is_active):
        cfg = self.config
        style = cfg.get("pill_style", "filled")
        idle_bg_on = cfg.get("idle_has_bg", True)

        if is_active:
            if cfg["color_mode"] == "mono":
                bg, fg, accent = hex_to_rgba(cfg["mono_active_bg"], 245), hex_to_rgba(cfg["mono_active_text"], 255), hex_to_rgba(cfg["mono_accent"], 255)
            else:
                p = cfg["multi_pills"].get(str(d_num), LUXURY_MULTI_PALETTE[(d_num - 1) % len(LUXURY_MULTI_PALETTE)])
                bg, fg, accent = hex_to_rgba(p["bg"], 245), hex_to_rgba(p["fg"], 255), hex_to_rgba(p.get("accent", p["fg"]), 255)
            outline = accent if cfg.get("active_border", True) else None
            if style == "minimal":
                return None, accent, accent, None
            elif style == "outline":
                return (bg[0], bg[1], bg[2], 45), accent, accent, accent
            return bg, fg, accent, outline
        else:
            bg = hex_to_rgba(cfg["mono_idle_bg"], 215) if idle_bg_on else None
            fg = hex_to_rgba(cfg["mono_idle_text"], 255)
            outline = hex_to_rgba(cfg["border_color"], 180) if idle_bg_on else None
            if style == "minimal":
                return None, fg, fg, None
            elif style == "outline":
                return None, fg, fg, outline
            return bg, fg, fg, outline

    def render_workspaces_bar(self, curr_num, desktops_list, mon_left, mon_top, mon_width, scale):
        cfg = self.config
        is_trans = cfg.get("bar_transparent", True)
        bar_height = int(cfg["height"] * scale)
        base_font_size = max(10, int((cfg["height"] * 0.44) * scale))

        canvas_bg = (0, 0, 0, 0) if is_trans else hex_to_rgba(cfg["bg_color"], 245)
        img = Image.new("RGBA", (mon_width, bar_height), canvas_bg)
        draw = ImageDraw.Draw(img)

        if not is_trans:
            draw.line([(0, bar_height - 1), (mon_width, bar_height - 1)], fill=hex_to_rgba(cfg["border_color"], 255), width=1)

        pad_x = int(14 * scale)
        cy = bar_height // 2
        avail_width = mon_width - (pad_x * 2)

        size_map = {"compact": 10, "normal": 16, "wide": 30}
        base_pad_x = int(size_map.get(cfg["pill_size"], 16) * scale)
        active_extra_pad = int(cfg.get("active_pop_padding", 6) * scale)
        pill_gap = int(cfg.get("pill_gap", 10) * scale)
        pill_v_margin = int(4 * scale)
        pill_radius = int(cfg.get("pill_radius", 9) * scale)
        show_dot = cfg.get("show_dot", False)
        dot_r = max(2.5, 3.0 * scale) if show_dot else 0
        dot_space = int(dot_r * 2 + 7 * scale) if show_dot else 0

        pills_meta = []
        total_base_w = 0
        for d_num, d_name in desktops_list:
            is_active = (d_num == curr_num)
            f_base, fk_base = self.resolve_font(base_font_size, is_active)
            label_str = self.apply_text_case(d_name)
            bbox_l = self.get_cached_bbox(draw, label_str, f_base, fk_base)
            lw = bbox_l[2] - bbox_l[0]
            this_pad = base_pad_x + (active_extra_pad if is_active else 0)
            pw = this_pad + dot_space + lw + this_pad
            pills_meta.append({"num": d_num, "label": label_str, "active": is_active, "base_pw": pw, "base_pad": this_pad})
            total_base_w += pw

        if len(pills_meta) > 1:
            total_base_w += pill_gap * (len(pills_meta) - 1)

        layout_mode = cfg.get("layout_mode", "center")
        est_x = max(pad_x, (mon_width // 2) - (total_base_w // 2)) if layout_mode == "center" else pad_x
        still_animating = False

        for pm in pills_meta:
            d_num = pm["num"]
            est_cx = est_x + pm["base_pw"] / 2.0
            est_x += pm["base_pw"] + pill_gap

            target_zoom = 1.0
            if False and self.hover_x is not None:
                dist = abs(self.hover_x - est_cx)
                radius = 85.0 * scale
                if dist < radius:
                    zoom_amp = float(cfg.get("hover_zoom_scale", 0.45))
                    target_zoom = 1.0 + zoom_amp * (0.5 * (1.0 + math.cos(math.pi * dist / radius)))
            cur_zoom = self.hover_scales.get(d_num, 1.0)
            smooth_speed = float(cfg.get("hover_smoothness", 0.28))
            new_zoom = cur_zoom + (target_zoom - cur_zoom) * smooth_speed
            if abs(target_zoom - new_zoom) < 0.002:
                new_zoom = target_zoom
            self.hover_scales[d_num] = new_zoom
            pm["zoom"] = new_zoom

            z_font_size = max(10, int(round(base_font_size * (1.0 + (new_zoom - 1.0) * 0.65))))
            f_use, fk_use = self.resolve_font(z_font_size, pm["active"])
            bbox_z = self.get_cached_bbox(draw, pm["label"], f_use, fk_use)
            lw_z = bbox_z[2] - bbox_z[0]
            lh_z = bbox_z[3] - bbox_z[1]
            pad_z = int(round(pm["base_pad"] * new_zoom))
            pm.update({"font": f_use, "lw": lw_z, "lh": lh_z, "bbox": bbox_z, "pad": pad_z,
                       "pw": pad_z + dot_space + lw_z + pad_z})

        self.is_animating = still_animating

        total_pills_width = sum(p["pw"] for p in pills_meta) + (pill_gap * max(0, len(pills_meta) - 1))
        equal_pw = 0
        if layout_mode == "stretch" and len(pills_meta) > 0:
            equal_pw = max(int(40 * scale), (avail_width - pill_gap * (len(pills_meta) - 1)) // len(pills_meta))
            cur_x = pad_x
        elif layout_mode == "center":
            cur_x = max(pad_x, (mon_width // 2) - (total_pills_width // 2))
        else:
            cur_x = pad_x

        new_hitboxes = []
        for pm in pills_meta:
            pw = equal_pw if layout_mode == "stretch" else pm["pw"]
            if cur_x + pw > mon_width - pad_x and layout_mode != "stretch":
                break

            z = pm["zoom"]
            v_shrink = max(1, int(round(pill_v_margin * (1.0 - (z - 1.0) * 3.5))))
            pill_top = v_shrink
            pill_bottom = bar_height - v_shrink - 1

            x1, x2 = cur_x, cur_x + pw
            fill_bg, fill_fg, fill_accent, fill_outline = self.get_pill_visuals(pm["num"], pm["active"])

            if fill_bg is not None or fill_outline is not None:
                draw.rounded_rectangle(
                    [x1, pill_top, x2, pill_bottom],
                    radius=pill_radius,
                    fill=fill_bg,
                    outline=fill_outline,
                    width=max(1, int(1.6 * scale)) if pm["active"] else 1
                )

            if pm["active"] and cfg.get("active_underline", False):
                ind_w = min(pw - int(12 * scale), int(26 * scale))
                if ind_w > 6:
                    ix1 = x1 + (pw - ind_w) // 2
                    iy = pill_bottom - max(1, int(1.5 * scale))
                    draw.line([(ix1, iy), (ix1 + ind_w, iy)], fill=fill_accent, width=max(2, int(2.2 * scale)))

            content_w = dot_space + pm["lw"]
            content_start_x = (x1 + max(int(6 * scale), (pw - content_w) // 2)) if layout_mode == "stretch" else (x1 + pm["pad"])

            if show_dot:
                dot_cx = content_start_x + dot_r
                draw.ellipse([dot_cx - dot_r, cy - dot_r, dot_cx + dot_r, cy + dot_r], fill=fill_accent)
                text_x = dot_cx + dot_r + int(7 * scale)
            else:
                text_x = content_start_x

            text_y = cy - (pm["lh"] // 2) - pm["bbox"][1]
            draw.text((text_x, text_y), pm["label"], font=pm["font"], fill=fill_fg)

            new_hitboxes.append((x1, pill_top, x2, pill_bottom, pm["num"]))
            cur_x = x2 + pill_gap

        self.pill_hitboxes = new_hitboxes
        self.reserve_screen_space(mon_left, mon_top, mon_width, bar_height)
        self.push_rgba_to_layered_window(img, mon_left, mon_top)

    def tick_now(self):
        if self.manual_hidden:
            return
        now_ms = int(ctypes.windll.kernel32.GetTickCount64())
        is_hovering = (self.hover_x is not None or self.is_animating)

        if not is_hovering or (now_ms - self._last_sys_check >= 200):
            self._last_sys_check = now_ms
            is_fs = self.is_foreground_fullscreen()
            if is_fs and not self.fullscreen_hidden:
                self.fullscreen_hidden = True
                self.release_screen_space()
                self.root.withdraw()
                return
            elif not is_fs and self.fullscreen_hidden:
                self.fullscreen_hidden = False
                self.root.deiconify()
                self.force_redraw = True
            if self.fullscreen_hidden:
                return

            self.enforce_topmost_pin()
            real_curr, desktops_list = self.get_all_desktops_data()
            if self.optimistic_ticks > 0:
                curr_num = self.optimistic_active_num
                self.optimistic_ticks -= 1
            else:
                curr_num = real_curr
            self._cached_curr = curr_num
            self._cached_desktops = desktops_list
        else:
            curr_num = self._cached_curr
            desktops_list = self._cached_desktops

        mon_left, mon_top, mon_width, scale = self.get_primary_monitor_info()
        current_state = (curr_num, desktops_list, mon_left, mon_top, mon_width, scale,
                         self.hover_x, self._config_str)
        if current_state != self.last_state or self.force_redraw or self.is_animating:
            self.last_state = current_state
            self.force_redraw = False
            self.render_workspaces_bar(curr_num, desktops_list, mon_left, mon_top, mon_width, scale)

    def update_loop(self):
        if not self.running:
            return
        self.tick_now()
        delay = 8 if (self.hover_x is not None or self.is_animating) else 50
        self.root.after(delay, self.update_loop)

    def quit_app(self, icon=None, item=None):
        self.running = False
        self.release_screen_space()
        if icon:
            icon.stop()
        self.root.after(150, self.root.destroy)

    def show_bar_context_menu(self, event):
        try:
            m = tk.Menu(self.root, tearoff=0, bg="#18181b", fg="#f4f4f5", activebackground="#2563eb", activeforeground="#ffffff", bd=0)
            m.add_command(label="Mở Bảng Tùy Chỉnh (Pro Studio)", command=self.open_settings_popup)
            m.add_separator()
            m.add_command(label="Thoát thanh bar", command=self.quit_app)
            m.tk_popup(event.x_root, event.y_root)
        except Exception:
            self.open_settings_popup()

    def run(self):
        threading.Thread(target=self.listen_hotkey, daemon=True).start()
        try:
            self.root.bind_all("<Button-3>", self.show_bar_context_menu)
        except Exception:
            pass
        self.root.mainloop()

if __name__ == "__main__":
    app = SystemWorkspacesBar()
    app.run()