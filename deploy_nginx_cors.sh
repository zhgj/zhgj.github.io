#!/bin/bash
# 一键在 4gwifi 上为 Apprise 加 CORS 支持
# 用法：通过 SSH 粘贴执行

# 1. 确认 nginx 安装
which nginx || { echo "nginx not found, please install first"; exit 1; }

# 2. 创建 nginx CORS 代理配置
cat > /etc/nginx/conf.d/apprise-cors.conf << 'NGINX_EOF'
server {
    listen 5281;
    server_name myres.freemyip.com res.freemyip.com;
    
    # CORS 跨域支持
    add_header 'Access-Control-Allow-Origin' '*' always;
    add_header 'Access-Control-Allow-Methods' 'GET, POST, PUT, DELETE, OPTIONS' always;
    add_header 'Access-Control-Allow-Headers' 'Content-Type, Accept, Authorization' always;
    add_header 'Access-Control-Max-Age' 86400 always;
    
    # 处理 OPTIONS 预检请求
    if ($request_method = 'OPTIONS') {
        add_header 'Access-Control-Allow-Origin' '*';
        add_header 'Access-Control-Allow-Methods' 'GET, POST, PUT, DELETE, OPTIONS';
        add_header 'Access-Control-Allow-Headers' 'Content-Type, Accept, Authorization';
        add_header 'Access-Control-Max-Age' 86400;
        add_header 'Content-Length' 0;
        add_header 'Content-Type' 'text/plain';
        return 204;
    }
    
    # 原 apprise 服务在 5282 端口
    location / {
        proxy_pass http://127.0.0.1:5282;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
NGINX_EOF

# 3. 修改 apprise_ntfy.py 监听 5282 端口（避免冲突）
sed -i 's/listen 5281/listen 5282/' /root/apprise_ntfy.py 2>/dev/null
sed -i 's/port=5281/port=5282/' /root/apprise_ntfy.py 2>/dev/null
sed -i 's/5281/5282/' /root/apprise_ntfy.py 2>/dev/null

# 4. 重启 nginx
nginx -t && nginx -s reload
echo "nginx CORS proxy configured on port 5281"
echo "Origin apprise service moved to port 5282"
