#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Apprise 通知中转服务 (port 5281)
- POST /apprise  接收 {"title":"..","body":"..","type":"info"} 发送通知
- 支持 CORS (Access-Control-Allow-Origin: *) 供 GitHub Pages 跨域调用
- 使用 BaseHTTPServer (无需 Flask)
部署: nohup python3 /root/apprise_ntfy.py >> /tmp/apprise_ntfy.log 2>&1 &
"""
import os
import sys
import time
import json
import uuid
import socket
import hashlib
import threading
import subprocess
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from datetime import datetime

# ---------- 配置 ----------
SERVER_NAME = os.environ.get('SERVER_NAME', 'apprise_ntfy_server')
SERVER_PORT = int(os.environ.get('SERVER_PORT', '5281'))
APPRISE_STATELESS_URLS = os.environ.get('APPRISE_STATELESS_URLS', '')
APPRISE_CONFIG_DIR = os.environ.get('APPRISE_CONFIG_DIR', '/root/.apprise')
NTFY_SERVER = os.environ.get('NTFY_SERVER', 'http://myres.freemyip.com:5380/midgard')

# 去重: 相同 body 在此时间内不重复发送
CLIP_DEDUP_SECONDS = int(os.environ.get('CLIP_DEDUP_SECONDS', '1800'))
_dedup_cache = {}

# Apprise CLI 路径 (pip install apprise 后为 'apprise')
APPRISE_CMD = os.environ.get('APPRISE_CMD', 'apprise')

# ---------- 工具函数 ----------
def get_apprise_urls():
    """从配置目录读取通知渠道 URL"""
    urls = APPRISE_STATELESS_URLS
    if not urls:
        config_file = os.path.join(APPRISE_CONFIG_DIR, 'apprise.conf.default')
        if os.path.exists(config_file):
            with open(config_file, 'r') as f:
                urls = f.read().strip()
    return urls

def send_notify(title, body, notif_type='info'):
    """通过 Apprise CLI 发送通知 (异步线程)"""
    def _task():
        try:
            urls = get_apprise_urls()
            if not urls:
                log(f"[WARN] No notification URLs configured")
                return
            cmd = [APPRISE_CMD, '-t', title or '', '-b', body or '', urls]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                log(f"[OK] Sent: {title}")
            else:
                log(f"[FAIL] rc={result.returncode}: {result.stderr.strip()}")
        except Exception as e:
            log(f"[ERROR] {e}")
    threading.Thread(target=_task, daemon=True).start()

def dedup_check(value, ttl=CLIP_DEDUP_SECONDS):
    """简单内存去重"""
    key = hashlib.md5(value.encode('utf-8', errors='replace')).hexdigest()
    now = time.time()
    if key in _dedup_cache:
        old_val, old_ts = _dedup_cache[key]
        if old_val == value and now - old_ts < ttl:
            return True
    _dedup_cache[key] = (value, now)
    return False

def log(msg):
    ts = datetime.now().strftime('%H:%M:%S')
    print(f"[{ts}] {msg}", flush=True)

# ---------- 请求处理 ----------
class NotifyHandler(BaseHTTPRequestHandler):
    """HTTP 请求处理器 - 带 CORS 支持"""

    # ====== CORS 支持: 所有响应加 CORS 头 ======
    def _add_cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Accept, Authorization')
        self.send_header('Access-Control-Max-Age', '86400')

    def _send_json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self._add_cors()
        self.end_headers()
        self.wfile.write(body)

    def _parse_body(self):
        """解析 POST body (JSON 或 form)"""
        length = int(self.headers.get('Content-Length', 0))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            try:
                from urllib.parse import parse_qs
                return parse_qs(raw.decode('utf-8', errors='replace'))
            except:
                return {}

    # ====== OPTIONS 预检 (CORS) ======
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header('Content-Length', '0')
        self._add_cors()
        self.end_headers()

    # ====== GET ======
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip('/')
        params = parse_qs(parsed.query)

        if path in ('/health', '/ping', ''):
            self._send_json(200, {
                'status': 'ok',
                'server': SERVER_NAME,
                'time': datetime.now().isoformat(),
            })
            return

        # GET /apprise 也支持 (用 query string)
        if path == '/apprise':
            title = params.get('title', ['通知'])[0]
            body = params.get('body', [''])[0]
            notif_type = params.get('type', ['info'])[0]
            self._handle_notify(title, body, notif_type)
            return

        self._send_json(404, {'error': f'Not Found: {self.path}'})

    # ====== POST ======
    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip('/')

        if path in ('/apprise', '/notify', '/ntfy'):
            data = self._parse_body()
            title = data.get('title', '通知')
            if isinstance(title, list):
                title = title[0] if title else '通知'
            body = data.get('body', '')
            if isinstance(body, list):
                body = body[0] if body else ''
            notif_type = data.get('type', data.get('priority', 'info'))
            if isinstance(notif_type, list):
                notif_type = notif_type[0] if notif_type else 'info'
            self._handle_notify(title, body, notif_type)
            return

        self._send_json(404, {'error': f'Not Found: {self.path}'})

    def _handle_notify(self, title, body, notif_type):
        """处理通知请求"""
        # 去重
        key = hashlib.md5(str(body).encode()).hexdigest()
        now = time.time()
        if key in _dedup_cache:
            old_val, old_ts = _dedup_cache[key]
            if old_val == str(body) and now - old_ts < CLIP_DEDUP_SECONDS:
                self._send_json(200, {'status': 'duplicate', 'message': 'Deduplicated within TTL'})
                return
        _dedup_cache[key] = (str(body), now)

        # 异步发送
        send_notify(title=title, body=body, notif_type=notif_type)

        log(f"POST {title!r} -> {body!r} (type={notif_type})")
        self._send_json(200, {
            'status': 'queued',
            'message': 'Notification queued for delivery',
        })

    # ====== 日志抑制 (减少控制台噪音) ======
    def log_message(self, fmt, *args):
        log(fmt % args)

# ---------- 启动 ----------
def main():
    server = HTTPServer(('0.0.0.0', SERVER_PORT), NotifyHandler)
    log(f"Apprise notify server starting on 0.0.0.0:{SERVER_PORT}")
    log(f"API endpoints: POST /apprise, POST /notify")
    log(f"CORS enabled: Access-Control-Allow-Origin: *")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log("Shutting down...")
        server.shutdown()

if __name__ == '__main__':
    main()
