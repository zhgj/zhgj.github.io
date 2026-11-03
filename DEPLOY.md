# 一键部署指南

## 在 4gwifi 上执行

### 方案 1：nginx 加 CORS（最简单）

SSH 到 4gwifi 后执行以下命令：

```bash
# 查看当前 nginx 配置
cat /etc/nginx/nginx.conf
# 或在 conf.d 目录下添加 cors.conf
cat > /etc/nginx/conf.d/cors.conf << 'EOF'
# CORS support for apprise API
server {
    listen 5282;  # 用新端口避免冲突
    server_name _;
    
    add_header 'Access-Control-Allow-Origin' '*' always;
    add_header 'Access-Control-Allow-Methods' 'GET, POST, OPTIONS' always;
    add_header 'Access-Control-Allow-Headers' 'Content-Type' always;
    
    if ($request_method = 'OPTIONS') {
        add_header 'Access-Control-Allow-Origin' '*';
        add_header 'Access-Control-Allow-Methods' 'GET, POST, OPTIONS';
        add_header 'Access-Control-Allow-Headers' 'Content-Type';
        add_header 'Access-Control-Max-Age' 86400;
        add_header 'Content-Length' 0;
        return 204;
    }
    
    location / {
        proxy_pass http://127.0.0.1:5281;
    }
}
EOF

nginx -t && nginx -s reload
```

然后修改 `move-car.html` 中的 API_URL 为 `http://myres.freemyip.com:5282/apprise`

### 方案 2：直接修改 apprise 脚本

```bash
# 查看正在运行的 Python 进程
ps aux | grep apprise

# 找到源文件路径（可能是 /root/ 下某个 .py）

# 编辑文件，在 HTTPRequestHandler 类里添加：
def do_OPTIONS(self):
    self.send_response(200)
    self.send_header('Access-Control-Allow-Origin', '*')
    self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
    self.send_header('Access-Control-Allow-Headers', 'Content-Type')
    self.send_header('Access-Control-Max-Age', 86400)
    self.end_headers()

# 重启服务
pkill -f apprise_ntfy
nohup python3 /path/to/your/apprise_script.py >> /tmp/apprise_ntfy.log 2>&1 &
```

## 验证 CORS 生效

```bash
# 本地测试
curl -I -X OPTIONS \
  -H "Origin: https://zhgj.github.io" \
  -H "Access-Control-Request-Method: POST" \
  http://localhost:5281/apprise | grep -i "access-control"

# 应该看到：
# Access-Control-Allow-Origin: *
# Access-Control-Allow-Methods: GET, POST, OPTIONS
```
