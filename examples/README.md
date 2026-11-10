# 客户端调用示例（API Key）

外部程序调用本平台**只需 API Key，无需登录账户**。API Key 在 Web 管理端「API Key 管理」创建，明文只展示一次。

所有示例统一用下列环境变量配置：

| 变量 | 必填 | 默认 | 说明 |
|------|------|------|------|
| `KB_API_KEY` | ✅ | — | `kb-` 开头的 API Key |
| `KB_BASE_URL` | | `http://localhost:8080` | 网关地址 |
| `KB_ID` | | 空 | 知识库 UUID；留空则用 API Key 绑定的默认知识库 |
| `KB_QUERY` | | 内置示例问题 | 提问内容 |

每个示例都覆盖 4 类调用：`GET /v1/models`、非流式问答、SSE 流式问答、`POST /api/v1/search` 混合检索。

## cURL / Bash

```bash
export KB_API_KEY="kb-xxxx"
./api_key_curl.sh            # 全部；或 models|chat|stream|search
```

## Python

```bash
pip install requests
export KB_API_KEY="kb-xxxx"
python3 python_example.py    # 另含可选的 OpenAI SDK 用法
```

## JavaScript（Node.js 18+，内置 fetch）

```bash
export KB_API_KEY="kb-xxxx"
node js_example.js
```

浏览器中同样可用：把 `BASE_URL`/`API_KEY` 直接写死或改为输入，去掉 `process.env` 读取即可（注意跨域与密钥暴露风险，生产建议经后端代理）。

## Java（JDK 11+，零第三方依赖）

```bash
export KB_API_KEY="kb-xxxx"
java JavaExample.java        # 单文件源码启动，无需先 javac
```

生产代码建议用 Jackson / Gson 解析 JSON；示例为零依赖直接打印原始响应，并用正则从 SSE 流中提取正文增量。

## 鉴权与错误码

- 请求头统一为 `Authorization: Bearer <API Key>`。
- `401` Key 无效/缺失；`403` scope 不足或无权访问该知识库；`429` 触发限流（Key 的每分钟/每日阈值）。
- 完整接口与字段见 [../docs/API.md](../docs/API.md)。
