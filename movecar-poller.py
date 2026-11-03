#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
挪车通知轮询器 (部署在 4gwifi)
==================================================
链路:
  路人扫码 → https://zhgj.github.io/move-car.html   (GitHub Pages, HTTPS)
          → POST https://ntfy.sh/<topic>             (匿名, CORS 开放, HTTPS)
          → 本进程轮询 ntfy.sh 拉取新消息
          → 校验前缀 MOVECAR|
          → 调用本机 5281 Apprise 接口
          → Apprise → 企微 / 钉钉 / ntfy

为什么这样设计:
  ① GitHub Pages 强制 HTTPS, 而 5281 只有 HTTP → 浏览器混合内容(mixed content)会直接拦截
     浏览器 → 5281 的 fetch, 加 CORS 也没用。所以浏览器不能直连 5281。
  ② 4gwifi 的 ufw 只放行特定来源 IP → 路人手机 IP 直连 5281 不可靠。
  ③ ntfy.sh 免鉴权 + CORS 开放 + HTTPS → 路人无需任何凭证, 点一下即可。
  ④ 本进程在 4gwifi 本机, 走回环调用 5281, 完全不碰 ufw 入站规则, 且不动现有服务。

部署 (4gwifi 上执行, 一条命令):
  curl -sL https://raw.githubusercontent.com/zhgj/zhgj.github.io/main/movecar-poller.py \
    -o /root/movecar_poller.py && chmod +x /root/movecar_poller.py && \
    nohup python3 /root/movecar_poller.py >> /tmp/movecar.log 2>&1 &

环境变量:
  NTFY_TOPIC     默认 movecar-zh-gj      (必须与 move-car.html 里的 TOPIC 一致)
  NTFY_BASE      默认 https://ntfy.sh
  APPRISE_URL    默认 http://127.0.0.1:5281/apprise
  POLL_INTERVAL  默认 3 秒
  MOVE_LOG       默认 /tmp/movecar.log
"""
import os
import sys
import time
import json
import logging
import urllib.request
import urllib.parse
import urllib.error
from logging.handlers import RotatingFileHandler

# ---------------- 配置 ----------------
NTFY_BASE = os.environ.get('NTFY_BASE', 'https://ntfy.sh').rstrip('/')
NTFY_TOPIC = os.environ.get('NTFY_TOPIC', 'movecar-zh-gj')
PREFIX = os.environ.get('MOVE_PREFIX', 'MOVECAR|')
APPRISE_URL = os.environ.get('APPRISE_URL', 'http://127.0.0.1:5281/apprise')
POLL_INTERVAL = int(os.environ.get('POLL_INTERVAL', '3'))
LOG_PATH = os.environ.get('MOVE_LOG', '/tmp/movecar.log')
START_TS = int(time.time())

logger = logging.getLogger('movecar')


def setup_logging():
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')

    fh = RotatingFileHandler(LOG_PATH, maxBytes=2 * 1024 * 1024, backupCount=3,
                             encoding='utf-8')
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(sh)


def http_get(url, timeout=15):
    req = urllib.request.Request(url, headers={'User-Agent': 'movecar-poller/1.0'})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode('utf-8', errors='replace')


def http_post_form(url, data, timeout=20):
    """用 GET + query 调用 5281 (与仓库 remind.yml 已验证的调用方式一致)"""
    qs = urllib.parse.urlencode(data)
    sep = '&' if '?' in url else '?'
    return http_get(url + sep + qs, timeout=timeout)


def poll_once(since_id):
    """拉取 ntfy 新消息, 返回 (新消息列表, 最新 id)"""
    url = f'{NTFY_BASE}/{NTFY_TOPIC}/json?poll=1'
    if since_id:
        url += '&since=' + urllib.parse.quote(since_id)
    raw = http_get(url, timeout=20)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning('ntfy 返回非 JSON: %s', raw[:120])
        return [], since_id
    if isinstance(data, dict):
        data = [data]
    msgs, last = [], since_id
    for m in data:
        if not isinstance(m, dict):
            continue
        if m.get('id'):
            last = m['id']
        if m.get('event') != 'message':
            continue
        msgs.append(m)
    return msgs, last


def deliver(title, body):
    """转发到 5281 Apprise"""
    try:
        resp = http_post_form(APPRISE_URL, {'title': title, 'body': body})
        logger.info('已投递 5281 <- %s | %s | resp=%s', title, body, resp[:120])
        return True
    except Exception as e:
        logger.error('投递 5281 失败: %s', e)
        return False


def main():
    setup_logging()
    logger.info('=' * 50)
    logger.info('挪车轮询器启动 topic=%s interval=%ds apprise=%s',
                NTFY_TOPIC, POLL_INTERVAL, APPRISE_URL)
    logger.info('=' * 50)

    since_id = ''
    first = True
    fail = 0

    while True:
        try:
            msgs, since_id = poll_once(since_id)
            fail = 0
            if first and msgs:
                # 首次拉取: 只记住游标, 不处理历史消息
                logger.info('首次同步, 历史消息 %d 条已跳过', len(msgs))
                first = False
            elif first:
                first = False

            for m in msgs:
                text = m.get('message', '') or ''
                ts = int(m.get('time', 0) or 0)
                # 启动前的旧消息不处理
                if ts and ts < START_TS - 60:
                    continue
                if not text.startswith(PREFIX):
                    logger.info('忽略非挪车消息: %s', text[:80])
                    continue
                body = text[len(PREFIX):].strip()
                if not body:
                    continue
                deliver('🚙 挪车通知', body)

        except urllib.error.HTTPError as e:
            fail += 1
            logger.warning('ntfy HTTP %s (第 %d 次)', e.code, fail)
            time.sleep(min(60, 5 * fail))
            continue
        except Exception as e:
            fail += 1
            logger.error('轮询异常: %s (第 %d 次)', e, fail)
            time.sleep(min(60, 5 * fail))
            continue

        time.sleep(POLL_INTERVAL)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        logger.info('收到中断, 退出')
    except Exception as e:
        logger.exception('致命错误: %s', e)
        sys.exit(1)
