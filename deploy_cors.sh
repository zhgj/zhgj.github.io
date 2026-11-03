#!/bin/bash
# 一键部署 CORS 支持到 4gwifi 的 apprise_ntfy 服务
# 在 4gwifi 上执行: bash -c "$(curl -s https://raw.githubusercontent.com/zhgj/zhgj.github.io/main/deploy_cors.sh)"

echo "[deploy_cors] Applying CORS support to /root/apprise_ntfy.py..."

# 备份原始文件
cp /root/apprise_ntfy.py /root/apprise_ntfy.py.bak.$(date +%Y%m%d)

# 检查是否已有 CORS 支持
if grep -q "add_cors_headers" /root/apprise_ntfy.py; then
    echo "[deploy_cors] CORS support already exists, skipping..."
    exit 0
fi

# 临时 Python 脚本：读取原文件，在合适位置插入 CORS 代码
cat > /tmp/patch_cors.py << 'PYEOF'
import re
import sys

filepath = '/root/apprise_ntfy.py'

with open(filepath, 'r') as f:
    content = f.read()

cors_code = '''
# ===== CORS Support =====
@app.after_request
def add_cors_headers(response):
    """为所有响应添加 CORS 头"""
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Accept, Authorization'
    response.headers['Access-Control-Max-Age'] = '86400'
    return response

@app.before_request
def handle_preflight():
    """处理 OPTIONS 预检请求"""
    if request.method == 'OPTIONS':
        resp = Response(status=204)
        resp.headers['Access-Control-Allow-Origin'] = '*'
        resp.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
        resp.headers['Access-Control-Allow-Headers'] = 'Content-Type, Accept, Authorization'
        resp.headers['Access-Control-Max-Age'] = '86400'
        return resp
# ===== End CORS =====

'''

# 1. 确保 from flask import 包含 Response
if 'Response' not in content:
    content = content.replace(
        'from flask import Flask, request',
        'from flask import Flask, request, Response'
    )
    content = content.replace(
        'from flask import Flask, Request',
        'from flask import Flask, request, Response'
    )
    content = content.replace(
        'from flask import',
        'from flask import Flask, request, Response'
    )

# 2. 在 Flask(__name__) 之后插入 CORS 代码
if 'app = Flask(__name__)' in content:
    content = content.replace(
        'app = Flask(__name__)\n',
        'app = Flask(__name__)\n' + cors_code
    )
elif 'app = Flask(__name__)' in content:
    # 可能在行末有空格
    lines = content.split('\n')
    for i, line in enumerate(lines):
        if 'Flask(__name__)' in line:
            lines.insert(i + 1, cors_code)
            content = '\n'.join(lines)
            break
# 3. 检查是否 Flask 实例化用其他变量名
    content = re.sub(
    r'(app\s*=\s*Flask\(__name__\)')',
    r'\1\n' + cors_code,
    content,
    flags=re.MULTILINE
)

# 4. 如果以上都没匹配，尝试在第一个 @app.route 前插入
if 'add_cors_headers' not in content:
    insert_point = content.find('@app.route')
    if insert_point > 0:
        content = content[:insert_point] + cors_code + content[insert_point:]

with open(filepath, 'w') as f:
    f.write(content)

if 'add_cors_headers' in content:
    print('[patch_cors] CORS support inserted successfully!')
    sys.exit(0)
else:
    print('[patch_cors] WARNING: Could not insert CORS code, please check manually')
    sys.exit(1)
PYEOF

python3 /tmp/patch_cors.py
RESULT=$?

if [ $RESULT -eq 0 ]; then
    echo "[deploy_cors] Reloading apprise_ntfy service..."
    # 杀掉旧进程并重启
    PIDS=$(pgrep -f apprise_ntfy.py)
    if [ -n "$PIDS" ]; then
        echo "[deploy_cors] Stopping old process(es): $PIDS"
        kill $PIDS
        sleep 2
    fi
    echo "[deploy_cors] Starting new process..."
    nohup python3 /root/apprise_ntfy.py >> /tmp/apprise_ntfy.log 2>&1 &
    echo "[deploy_cors] Done! You can test with:"
    echo "  curl -I http://localhost:5281/apprise -H 'Origin: https://zhgj.github.io' | grep Access-Control"
else
    echo"[deploy_cors] Failed! Please check /tmp/patch_cors.py output."
fi

rm -f /tmp/patch_cors.py
