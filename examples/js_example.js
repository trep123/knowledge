// 外部 API 调用示例（JavaScript / Node.js 18+，使用内置 fetch）——使用 API Key，无需登录。
//
// 运行:
//   export KB_API_KEY="kb-你的APIKey"
//   node examples/js_example.js
//
// 可选环境变量:
//   KB_BASE_URL  默认 http://localhost:8080
//   KB_ID        知识库 UUID；不填则用 API Key 绑定的默认知识库
//   KB_QUERY     提问内容
//
// 浏览器里同样可用：把 BASE_URL/API_KEY 换成你的值，去掉 process.env 读取即可。

const BASE_URL = (process.env.KB_BASE_URL || "http://localhost:8080").replace(/\/$/, "");
const API_KEY = process.env.KB_API_KEY || "";
const KB_ID = process.env.KB_ID || "";
const QUERY = process.env.KB_QUERY || "删除文档时需要注意什么？";

if (!API_KEY) {
  console.error('请先设置环境变量 KB_API_KEY，例如 export KB_API_KEY="kb-xxxx"');
  process.exit(1);
}

const HEADERS = { Authorization: `Bearer ${API_KEY}`, "Content-Type": "application/json" };
// KB_ID 为空则省略，走 API Key 的默认知识库/授权范围
const kbIds = KB_ID ? { knowledge_base_ids: [KB_ID] } : {};

const hr = (t) => console.log(`\n\x1b[1;36m== ${t} ==\x1b[0m`);

async function post(path, body) {
  const res = await fetch(`${BASE_URL}${path}`, { method: "POST", headers: HEADERS, body: JSON.stringify(body) });
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res;
}

// 1) 列出模型
async function listModels() {
  hr("1) GET /v1/models —— 列出可用模型");
  const res = await fetch(`${BASE_URL}/v1/models`, { headers: HEADERS });
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  console.log(JSON.stringify(await res.json(), null, 2));
}

// 2) 非流式问答
async function chat() {
  hr("2) POST /v1/chat/completions —— 非流式问答（OpenAI 兼容）");
  const res = await post("/v1/chat/completions", {
    model: "knowledge-base",
    messages: [{ role: "user", content: QUERY }],
    top_k: 5,
    rerank: true,
    return_citations: true,
    ...kbIds,
  });
  const data = await res.json();
  console.log("回答:", data.choices[0].message.content);
  for (const c of data.kb_citations || []) {
    console.log(`  引用[${c.score.toFixed(4)}] ${c.filename} p${c.page_number}: ${c.content.slice(0, 50)}…`);
  }
}

// 3) SSE 流式问答
async function chatStream() {
  hr("3) POST /v1/chat/completions —— SSE 流式问答（逐字打印）");
  const res = await post("/v1/chat/completions", {
    model: "knowledge-base",
    stream: true,
    messages: [{ role: "user", content: QUERY }],
    return_citations: true,
    ...kbIds,
  });
  process.stdout.write("回答: ");
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    // SSE 以空行分隔事件；逐行处理 data:
    const lines = buf.split("\n");
    buf = lines.pop(); // 留下不完整的最后一行
    for (const line of lines) {
      const s = line.trim();
      if (!s.startsWith("data:")) continue;
      const payload = s.slice(5).trim();
      if (payload === "[DONE]") { console.log(); return; }
      const obj = JSON.parse(payload);
      if (obj.kb_citations) {
        const names = obj.kb_citations.map((c) => c.filename).join(", ");
        process.stdout.write(`\n[引用来源: ${names}]\n回答: `);
        continue;
      }
      const delta = obj.choices?.[0]?.delta?.content;
      if (delta) process.stdout.write(delta);
    }
  }
  console.log();
}

// 4) 混合检索
async function search() {
  hr("4) POST /api/v1/search —— 混合检索（只返回证据片段）");
  const res = await post("/api/v1/search", { query: QUERY, top_k: 5, rerank: true, ...kbIds });
  const data = await res.json();
  console.log(`命中 ${data.total} 条:`);
  for (const item of data.results) {
    console.log(`  [${item.score.toFixed(4)}] ${item.filename} p${item.page_number}: ${item.content.slice(0, 60)}…`);
  }
}

(async () => {
  try {
    await listModels();
    await chat();
    await chatStream();
    await search();
    hr("完成");
    console.log("提示: 401=Key 无效/缺失, 403=scope 不足或无权访问知识库, 429=触发限流");
  } catch (e) {
    console.error("调用失败:", e.message);
    process.exit(1);
  }
})();
