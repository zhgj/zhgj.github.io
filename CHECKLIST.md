# 挪车二维码系统 - 完整部署清单

## ✅ 已完成

| 步骤 | 状态 | 说明 |
|---|---|---|
| 1. 创建移动页面 | ✅ | `https://zhgj.github.io/move-car.html` |
| 2. 推送到 GitHub | ✅ | 含 QR 码按钮，点击可发送挪车通知 |
| 3. GitHub Pages 启用 | ✅ | 已确认返回 200 |
| 4. 部署文档 | ✅ | `DEPLOY.md` + `deploy_cors.sh` |

## ⚠️ 待完成

### 4gwifi (root@myres.freemyip.com) 上的最后一步

需要在 4gwifi 的 5281 端口的 Apprise 服务加 CORS 支持。

#### 方法 1：修改 Python 脚本（推荐，最简单）

SSH 到 4gwifi，编辑 `/root/apprise_ntfy.py`（或其他实际运行的脚本），在类定义里加：

```python
# 在 HTTPRequestHandler 类中添加这些方法：
def do_OPTIONS(self):
    self.send_response(200)
    self.send_header('Access-Control-Allow-Origin', '*')
    self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
    self.send_header('Access-Control-Allow-Headers', 'Content-Type')
    self.send_header('Access-Control-Max-Age', 86400)
    self.end_headers()

def end_headers(self):
    self.send_header('Access-Control-Allow-Origin', '*')
    self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
    self.send_header('Access-Control-Allow-Headers', 'Content-Type')
    super().end_headers()
```

然后重启服务：
```bash
pkill -f apprise_ntfy
nohup python3 /path/to/your/script.py >> /tmp/apprise_ntfy.log 2>&1 &
```

#### 方法 2：使用 deploy_cors.sh

```bash
bash <(curl https://raw.githubusercontent.com/zhgj/zhgj.github.io/main/deploy_cors.sh)
```

## 测试验证

SSH 到 4gwifi 后执行：
```bash
curl -v -X OPTIONS \
  -H "Origin: https://zhgj.github.io" \
  -H "Access-Control-Request-Method: POST" \
  http://localhost:5281/apprise 2>&1 | grep -i "access-control"
```

应该看到：
```
< Access-Control-Allow-Origin: *
< Access-Control-Allow-Methods: GET, POST, OPTIONS
< Access-Control-Allow-Headers: Content-Type
```

## 访问地址

- **页面**：https://zhgj.github.io/move-car.html
- **GitHub 仓库**：https://github.com/zhgj/zhgj.github.io
- **Apprise 测试**：http://res.freemyip.com:5281/apprise

## 工作原理

```
┌───────扫码者──────┐     ┌───────────────┐     ┌─────────────┐
│  微信/支付宝扫 QR 码 │ →   │  GitHub Pages  │ →   │   4gwifi    │
│   打开 HTML 页面    │     │  move-car.html │ →   │  5281/Apprise│
│                    │     │     │         │     │     │       │
│   点击"发送挪车通知"  │     │   JS fetch()  │ →   │     ↓       │
└────────────────────┘     └───────────────┘     │ 企微/ntfy/dingtalk│
                                                 └─────────────┘
```
