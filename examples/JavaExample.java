// 外部 API 调用示例（Java 11+，仅用 JDK 内置 java.net.http.HttpClient，无第三方依赖）
// ——使用 API Key，无需登录账户。
//
// 运行（单文件源码启动，需 JDK 11+）:
//   export KB_API_KEY="kb-你的APIKey"
//   java examples/JavaExample.java
//
// 可选环境变量:
//   KB_BASE_URL  默认 http://localhost:8080
//   KB_ID        知识库 UUID；不填则用 API Key 绑定的默认知识库
//   KB_QUERY     提问内容
//
// 说明: 为保持零依赖，示例直接打印原始 JSON，并用正则从 SSE 流中提取正文增量。
//       生产代码建议用 Jackson / Gson 解析 JSON。

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class JavaExample {

    static final String BASE_URL = stripSlash(env("KB_BASE_URL", "http://localhost:8080"));
    static final String API_KEY = env("KB_API_KEY", "");
    static final String KB_ID = env("KB_ID", "");
    static final String QUERY = env("KB_QUERY", "删除文档时需要注意什么？");

    static final HttpClient CLIENT = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(30))
            .build();

    // 匹配 SSE 正文增量: "delta":{"content":"..."}
    static final Pattern DELTA = Pattern.compile("\"delta\"\\s*:\\s*\\{\\s*\"content\"\\s*:\\s*\"((?:[^\"\\\\]|\\\\.)*)\"");

    public static void main(String[] args) throws Exception {
        if (API_KEY.isEmpty()) {
            System.err.println("请先设置环境变量 KB_API_KEY，例如 export KB_API_KEY=\"kb-xxxx\"");
            System.exit(1);
        }
        listModels();
        chat();
        chatStream();
        search();
        hr("完成");
        System.out.println("提示: 401=Key 无效/缺失, 403=scope 不足或无权访问知识库, 429=触发限流");
    }

    // 1) 列出模型
    static void listModels() throws Exception {
        hr("1) GET /v1/models —— 列出可用模型");
        HttpRequest req = base("/v1/models").GET().build();
        HttpResponse<String> res = CLIENT.send(req, HttpResponse.BodyHandlers.ofString());
        check(res);
        System.out.println(res.body());
    }

    // 2) 非流式问答
    static void chat() throws Exception {
        hr("2) POST /v1/chat/completions —— 非流式问答（OpenAI 兼容）");
        String body = "{"
                + "\"model\":\"knowledge-base\","
                + "\"messages\":[{\"role\":\"user\",\"content\":\"" + esc(QUERY) + "\"}],"
                + "\"top_k\":5,\"rerank\":true,\"return_citations\":true"
                + kbIdsField()
                + "}";
        HttpRequest req = base("/v1/chat/completions").POST(json(body)).build();
        HttpResponse<String> res = CLIENT.send(req, HttpResponse.BodyHandlers.ofString());
        check(res);
        System.out.println(res.body());
    }

    // 3) SSE 流式问答（逐行读取，提取正文增量）
    static void chatStream() throws Exception {
        hr("3) POST /v1/chat/completions —— SSE 流式问答（逐字打印）");
        String body = "{"
                + "\"model\":\"knowledge-base\",\"stream\":true,"
                + "\"messages\":[{\"role\":\"user\",\"content\":\"" + esc(QUERY) + "\"}],"
                + "\"return_citations\":true"
                + kbIdsField()
                + "}";
        HttpRequest req = base("/v1/chat/completions").POST(json(body)).build();
        HttpResponse<java.util.stream.Stream<String>> res =
                CLIENT.send(req, HttpResponse.BodyHandlers.ofLines());
        if (res.statusCode() != 200) {
            throw new RuntimeException("HTTP " + res.statusCode());
        }
        System.out.print("回答: ");
        res.body().forEach(line -> {
            String s = line.trim();
            if (!s.startsWith("data:")) return;
            String payload = s.substring(5).trim();
            if (payload.equals("[DONE]")) { System.out.println(); return; }
            Matcher m = DELTA.matcher(payload);
            if (m.find()) System.out.print(unescape(m.group(1)));
        });
        System.out.println();
    }

    // 4) 混合检索
    static void search() throws Exception {
        hr("4) POST /api/v1/search —— 混合检索（只返回证据片段）");
        String body = "{\"query\":\"" + esc(QUERY) + "\",\"top_k\":5,\"rerank\":true" + kbIdsField() + "}";
        HttpRequest req = base("/api/v1/search").POST(json(body)).build();
        HttpResponse<String> res = CLIENT.send(req, HttpResponse.BodyHandlers.ofString());
        check(res);
        System.out.println(res.body());
    }

    // ---- 工具方法 ----

    static HttpRequest.Builder base(String path) {
        return HttpRequest.newBuilder()
                .uri(URI.create(BASE_URL + path))
                .timeout(Duration.ofSeconds(300))
                .header("Authorization", "Bearer " + API_KEY);
    }

    static HttpRequest.BodyPublisher json(String body) {
        return HttpRequest.BodyPublishers.ofString(body);
    }

    // KB_ID 为空则省略该字段，走 API Key 的默认知识库/授权范围
    static String kbIdsField() {
        return KB_ID.isEmpty() ? "" : ",\"knowledge_base_ids\":[\"" + KB_ID + "\"]";
    }

    static void check(HttpResponse<String> res) {
        if (res.statusCode() != 200) {
            throw new RuntimeException("HTTP " + res.statusCode() + ": " + res.body());
        }
    }

    static String esc(String s) {
        return s.replace("\\", "\\\\").replace("\"", "\\\"")
                .replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t");
    }

    static String unescape(String s) {
        return s.replace("\\n", "\n").replace("\\r", "\r").replace("\\t", "\t")
                .replace("\\\"", "\"").replace("\\\\", "\\");
    }

    static String env(String k, String d) {
        String v = System.getenv(k);
        return (v == null || v.isEmpty()) ? d : v;
    }

    static String stripSlash(String s) {
        return s.endsWith("/") ? s.substring(0, s.length() - 1) : s;
    }

    static void hr(String t) {
        System.out.println("\n== " + t + " ==");
    }
}
