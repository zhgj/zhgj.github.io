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
import socket
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


def http_get_lines(url, timeout=15, idle_timeout=1.5):
    """流式读取 ndjson, 逐行 yield。

    ntfy 的响应是 Transfer-Encoding: chunked + Connection: keep-alive,
    连接不会自动关闭 ⇒ urlopen().read() 会一直等到超时。
    ⇒ 逐行读, 并把 socket 超时调小作为「空闲」判据, 读到空闲就收工返回。
    """
    req = urllib.request.Request(url, headers={'User-Agent': 'movecar-poller/1.0'})
    resp = urllib.request.urlopen(req, timeout=timeout)
    sock = None
    try:
        sock = resp.fp.raw._sock
    except Exception:
        pass
    try:
        if sock is not None:
            sock.settimeout(idle_timeout)
        while True:
            try:
                line = resp.readline()
            except socket.timeout:
                break  # 空闲 → 本轮结束
            except OSError as e:
                # readline 过程中 socket 超时可能导致连接不可用, 视为空闲
                if 'timed out' in str(e).lower():
                    break
                raise
            if not line:
                break
            line = line.strip()
            if line:
                yield line
    finally:
        try:
            resp.close()
        except Exception:
            pass


def http_get(url, timeout=15):
    req = urllib.request.Request(url, headers={'User-Agent': 'movecar-poller/1.0'})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode('utf-8', errors='replace')


def http_post_form(url, data, timeout=20):
    """用 GET + query 调用 5281 (与仓库 remind.yml 已验证的调用方式一致)"""
    qs = urllib.parse.urlencode(data)
    sep = '&' if '?' in url else '?'
    return http_get(url + sep + qs, timeout=timeout)


def fetch_all(since_id):
    """拉取当前所有消息 (不传 since)。

    用于两种场景:
      ① 启动初始化游标 —— 取最后一条 message 的 id 作为起点
      ② 队列原本为空、期间来了新消息 —— 此时这些消息都是"新"的, 需要投递
    返回 (消息列表, 最后一条 message 的 id)
    """
    url = f'{NTFY_BASE}/{NTFY_TOPIC}/json'
    msgs, last = [], since_id
    try:
        for line in http_get_lines(url, timeout=15, idle_timeout=2.0):
            try:
                m = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(m, dict):
                continue
            if m.get('event') != 'message':
                continue
            mid = m.get('id')
            if mid:
                last = mid
            msgs.append(m)
    except socket.timeout:
        pass
    return msgs, last


def poll_once(since_id):
    """拉取 ntfy 新消息, 返回 (新消息列表, 最新 id)

    ntfy 语义 (实测):
      /<topic>/json?since=<消息id>   返回该 id 之后的所有消息 (另含一条 event=open 的空事件)
      响应是 chunked + keep-alive 流, 连接不自动关闭 ⇒ 逐行读, 靠 socket 空闲超时收工。
    """
    url = f'{NTFY_BASE}/{NTFY_TOPIC}/json?since=' + urllib.parse.quote(str(since_id))

    msgs, last = [], since_id
    try:
        for line in http_get_lines(url, timeout=15, idle_timeout=2.0):
            try:
                m = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(m, dict):
                continue
            if m.get('event') != 'message':
                continue  # 跳过 open/keepalive 等事件
            mid = m.get('id')
            if mid:
                last = mid       # ★ 游标只取 message 事件的 id
            msgs.append(m)
    except socket.timeout:
        pass
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
    fail = 0

    # 初始化游标: 无 since 拉一次全量, 取最后一条消息 id。
    # 这样启动前的老消息不会重复投递, 启动后的新消息不会丢。
    # 若队列为空, 则用「首次成功拉到消息时的 id」作为起点 (见下方 fallback)。
    try:
        _old, since_id = fetch_all(since_id)
        logger.info('游标初始化: %s', since_id or '(队列为空, 等待首条消息)')
    except Exception as e:
        logger.warning('初始化游标失败(将继续重试): %s', e)

    while True:
        try:
            if not since_id:
                # 队列原本为空, 期间来了新消息 => 这些都是新消息, 要投递
                msgs, since_id = fetch_all(since_id)
                if msgs:
                    logger.info('队列收到首批消息 %d 条, 游标=%s', len(msgs), since_id)
            else:
                msgs, new_id = poll_once(since_id)
                if new_id:
                    since_id = new_id
            fail = 0

            for m in msgs:
                text = m.get('message', '') or ''
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
