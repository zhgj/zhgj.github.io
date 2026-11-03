# 挪车通知二维码系统

## 部署说明

### 1. 4gwifi 服务端 (5281 端口)

需要在 4gwifi 的 Apprise 服务上增加 CORS 支持，GitHub Pages 端才能调用它。

#### 方法 A：通过 nginx 加 CORS（推荐）

在 4gwifi 的 nginx 配置中添加 CORS 头：

```nginx
# /etc/nginx/conf.d/apprise.conf 或类似位置
server {
    listen 5281;
    
    # CORS headers
    add_header 'Access-Control-Allow-Origin' '*' always;
    add_header 'Access-Control-Allow-Methods' 'GET, POST, OPTIONS' always;
    add_header 'Access-Control-Allow-Headers' 'Content-Type' always;
    
    # Handle preflight
    if ($request_method = 'OPTIONS') {
        add_header 'Access-Control-Allow-Origin' '*';
        add_header 'Access-Control-Allow-Methods' 'GET, POST, OPTIONS';
        add_header 'Access-Control-Allow-Headers' 'Content-Type';
        add_header 'Access-Control-Max-Age' 86400;
        add_header 'Content-Length' 0;
        return 204;
    }
    
    # Proxy to apprise service
    location / {
        proxy_pass http://127.0.0.1:8080;  # 根据实际 apprise 端口调整
    }
}
```

然后 `nginx -t && nginx -s reload`

#### 方法 B：直接修改 Python 源码

编辑 4gwifi 上的 `/root/apprise_ntfy.py`（或实际运行的 Python 脚本），在导入 `http.server` 后添加 CORS 支持：

```python
# 在 BaseHTTPRequestHandler 类中添加
def end_headers(self):
    self.send_header('Access-Control-Allow-Origin', '*')
    self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
    self.send_header('Access-Control-Allow-Headers', 'Content-Type')
    super().end_headers()

def do_OPTIONS(self):
    self.send_response(204)
    self.end_headers()
```

### 2. GitHub Pages 前端

已经部署在：https://zhgj.github.io/move-car.html

包含：
- 动态生成的 QR 码（指向页面自身）
- 点击按钮触发挪车通知
- 调用 4gwifi Apprise 服务推送通知

### 3. 测试验证

在部署后，从 GitHub Pages 打开页面测试：
1. 打开 https://zhgj.github.io/move-car.html
2. 点击"发送挪车通知"按钮
3. 应该在手机/企微/钉钉上收到挪车通知

## 文件列表

- `move-car.html` - 挪车通知页面
- `README.md` - 本文件
- `DEPLOY.md` - 详细部署文档
