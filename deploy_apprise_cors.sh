#!/bin/bash
# 一键部署: 在 4gwifi 上执行此脚本替换 apprise_ntfy.py 并重启服务
# 用法: bash <(curl -sL https://raw.githubusercontent.com/zhgj/zhgj.github.io/main/deploy_apprise_cors.sh)

set -e

echo "=== Apprise 通知服务部署脚本 ==="
echo "时间: $(date '+%Y-%m-%d %H:%M:%S')"

# 备份原文件
echo "[1/5] 备份原文件..."
cp /root/apprise_ntfy.py /root/apprise_ntfy.py.bak.$(date +%Y%m%d%H%M%S)
echo "  已备份到 /root/apprise_ntfy.py.bak.*"

# 下载新脚本
echo "[2/5] 下载带 CORS 的新脚本..."
wget -q -O /root/apprise_ntfy.py.new \
  https://raw.githubusercontent.com/zhgj/zhgj.github.io/main/apprise_ntfy.py

echo "[3/5] 替换原文件..."
mv /root/apprise_ntfy.py.new /root/apprise_ntfy.py
chmod +x /root/apprise_ntfy.py

# 杀掉旧进程
echo "[4/5] 停止旧服务..."
PIDS=$(ps aux | grep '[a]pprise_ntfy' | awk '{print $2}' | tr '\n' ' ')
if [ -n "$PIDS" ]; then
    echo "  杀掉 PID: $PIDS"
    kill $PIDS
    sleep 1
    # 确认已死
    for pid in $PIDS; do
        kill -9 $pid 2>/dev/null || true
    done
else
    echo "  没有找到 apprise_ntfy 进程"
fi

# 启动新服务
echo "[5/5] 启动新服务..."
nohup python3 /root/apprise_ntfy.py >> /tmp/apprise_ntfy.log 2>&1 &
NEW_PID=$!
echo "  新服务 PID: $NEW_PID"

# 等待启动
sleep 2

# 验证
echo ""
echo "=== 验证 ==="
if curl -s --connect-timeout 3 http://localhost:5281/apprise -X GET > /dev/null 2>&1; then
    echo "[OK] 服务已启动"

    # 测试 CORS
    CORS=$(curl -s -I -X OPTIONS -H "Origin: https://zhgj.github.io" http://localhost:5281/apprise 2>&1 | grep -i "access-control" || echo "none")
    if [ "$CORS" != "none" ]; then
        echo "[OK] CORS 头已生效:"
        echo "$CORS"
    else
        echo "[WARN] CORS 头未检测到"
    fi

    # 测试通知
    curl -s -H "Content-Type: application/json" \
      -d '{"title":"部署测试","body":"apprise_ntfy 已更新到带 CORS 的版本"}' \
      http://localhost:5281/apprise
    echo ""
else
    echo "[FAIL] 服务启动失败, 查看日志:"
    tail -20 /tmp/apprise_ntfy.log
    exit 1
fi

echo ""
echo "=== 部署完成 ==="
