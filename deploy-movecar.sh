#!/bin/bash
# ============================================================
#  挪车通知 —— 4gwifi 部署脚本 (轮询器)
# ============================================================
#  在 4gwifi 上执行:
#    curl -sL https://raw.githubusercontent.com/zhgj/zhgj.github.io/main/deploy-movecar.sh | bash
#
#  作用: 下载并启动 movecar-poller.py
#        轮询 ntfy.sh 队列 → 转发到本机 5281 Apprise → 企微/钉钉/ntfy
#
#  不改动现有 5281 服务, 不改 ufw, 只新增一个独立进程。
# ============================================================
set -e

TOPIC="${NTFY_TOPIC:-movecar-zh-gj}"
POLLER=/root/movecar_poller.py
LOG=/tmp/movecar.log

echo "=== 挪车通知轮询器部署 ==="
echo "topic: $TOPIC"

# 1. 下载
echo "[1/4] 下载轮询器..."
curl -sL --max-time 30 \
  https://raw.githubusercontent.com/zhgj/zhgj.github.io/main/movecar-poller.py \
  -o "$POLLER"
chmod +x "$POLLER"
echo "  -> $POLLER ($(wc -c < "$POLLER") bytes)"

# 2. 停掉旧的
echo "[2/4] 停止旧实例..."
pkill -f movecar_poller.py 2>/dev/null || true
sleep 1

# 3. 启动
echo "[3/4] 启动..."
export NTFY_TOPIC="$TOPIC"
export MOVE_LOG="$LOG"
nohup python3 "$POLLER" >> "$LOG" 2>&1 &
NEWPID=$!
echo "  PID: $NEWPID"

# 4. 验证
echo "[4/4] 验证..."
sleep 4
if kill -0 "$NEWPID" 2>/dev/null; then
    echo "[OK] 轮询器运行中 (PID $NEWPID)"
    echo ""
    echo "--- 日志 ---"
    tail -12 "$LOG" || true
else
    echo "[FAIL] 启动失败，日志:"
    tail -30 "$LOG" || true
    exit 1
fi

echo ""
echo "=== 部署完成 ==="
echo "自测: curl -X POST -H 'Content-Type: text/plain' \\"
echo "  -d 'MOVECAR|测试消息' https://ntfy.sh/$TOPIC"
