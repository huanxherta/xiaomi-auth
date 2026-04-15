# 小米账号登录/注册自动化工具

基于 Playwright 的小米账号 (aistudio.xiaomimimo.com) 登录/注册自动化工具。

## 功能特性

- ✅ 支持登录和注册流程
- ✅ 自动处理 Cookie 持久化存储
- ✅ 验证码人工介入处理
- ✅ 反检测浏览器配置
- ✅ 完整的日志记录

## 安装

```bash
cd xiaomi-auth
pip install -r requirements.txt
playwright install chromium
```

## 使用方法

### 登录

```bash
python -m src.main login -a your@email.com -p yourpassword
```

### 注册

```bash
python -m src.main register -e new@email.com -p yourpassword
```

### 列出已保存账号

```bash
python -m src.main list
```

## 配置

编辑 `config.yaml` 文件进行自定义配置:

```yaml
browser:
  headless: false    # 是否无头模式
  slow_mo: 100       # 操作延迟(ms)

captcha:
  wait_timeout: 300  # 验证码等待超时(秒)
```

## 验证码处理

当遇到验证码时, 工具会暂停并提示您在浏览器中手动完成验证码操作。

支持的验证码类型:
- 滑块验证码
- 图片验证码  
- 极验验证码
- 邮箱验证码

## Cookie 存储

登录/注册成功后, Cookies 会自动保存到 `cookies/` 目录。

```
cookies/
├── your_email.json
└── another_account.json
```

## 项目结构

```
xiaomi-auth/
├── src/
│   ├── auth/          # 认证相关
│   ├── browser/       # 浏览器管理
│   ├── storage/       # Cookie存储
│   └── utils/         # 工具函数
├── cookies/           # Cookie存储目录
├── logs/              # 日志目录
├── config.yaml        # 配置文件
└── requirements.txt   # 依赖列表
```

## API 使用

```python
from src.main import XiaomiAuthClient
import asyncio

async def example():
    client = XiaomiAuthClient()
    
    # 登录
    success = await client.login("your@email.com", "password")
    if success:
        print("登录成功!")
    
    # 加载已保存的cookies
    cookies = client.load_cookies("your@email.com")

asyncio.run(example())
```

## 注意事项

1. 首次使用需要安装 Playwright 浏览器: `playwright install chromium`
2. 建议在登录/注册时不要开启无头模式, 方便处理验证码
