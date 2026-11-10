import { useEffect, useRef, useState } from "react";
import { Button, Card, Input, Select, Space, Typography, Collapse, Spin, message } from "antd";
import { SendOutlined } from "@ant-design/icons";
import client from "../api/client";

interface Citation {
  document_id: string;
  filename: string;
  page_number: number | null;
  chunk_id: string;
  content: string;
  score: number;
}

interface Msg {
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
}

export default function Chat() {
  const [kbs, setKbs] = useState<any[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    client.get("/api/v1/knowledge-bases").then((r) => {
      setKbs(r.data);
      setSelected(r.data.map((k: any) => k.id));
    });
    return () => abortRef.current?.abort();
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const send = async () => {
    const query = input.trim();
    if (!query || streaming) return;
    if (!selected.length) { message.warning("请先选择知识库"); return; }
    setInput("");
    const history = messages.slice(-6).map((m) => ({ role: m.role, content: m.content }));
    setMessages((prev) => [...prev, { role: "user", content: query }, { role: "assistant", content: "" }]);
    setStreaming(true);

    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const resp = await fetch("/api/v1/chat/completions", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${localStorage.getItem("kb_token")}`,
        },
        body: JSON.stringify({
          knowledge_base_ids: selected,
          query,
          top_k: 5,
          rerank: true,
          stream: true,
          history,
        }),
        signal: controller.signal,
      });
      if (!resp.ok || !resp.body) throw new Error(`HTTP ${resp.status}`);

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const payload = line.slice(6).trim();
          if (payload === "[DONE]") continue;
          try {
            const evt = JSON.parse(payload);
            if (evt.event === "delta") {
              setMessages((prev) => {
                const next = [...prev];
                const last = next[next.length - 1];
                next[next.length - 1] = { ...last, content: last.content + evt.content };
                return next;
              });
            } else if (evt.event === "citations") {
              setMessages((prev) => {
                const next = [...prev];
                const last = next[next.length - 1];
                next[next.length - 1] = { ...last, citations: evt.citations };
                return next;
              });
            }
          } catch { /* 忽略不完整行 */ }
        }
      }
    } catch (e: any) {
      if (e.name !== "AbortError") {
        setMessages((prev) => {
          const next = [...prev];
          next[next.length - 1] = { role: "assistant", content: `请求失败: ${e.message}` };
          return next;
        });
      }
    } finally {
      setStreaming(false);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <Space style={{ marginBottom: 12 }} wrap>
        <Select
          mode="multiple"
          style={{ minWidth: 320 }}
          placeholder="选择知识库"
          value={selected}
          onChange={setSelected}
          options={kbs.map((k) => ({ value: k.id, label: k.name }))}
        />
        <Button danger size="small" onClick={() => setMessages([])}>清空对话</Button>
      </Space>

      <Card style={{ flex: 1, overflow: "auto", marginBottom: 12 }} styles={{ body: { minHeight: 300 } }}>
        {messages.length === 0 && (
          <Typography.Text type="secondary">选择知识库后提问，回答将附带文档来源与页码引用。</Typography.Text>
        )}
        {messages.map((m, i) => (
          <div key={i} style={{ marginBottom: 16, textAlign: m.role === "user" ? "right" : "left" }}>
            <div
              style={{
                display: "inline-block",
                maxWidth: "80%",
                padding: "8px 12px",
                borderRadius: 8,
                background: m.role === "user" ? "#1677ff" : "#f5f5f5",
                color: m.role === "user" ? "#fff" : undefined,
                whiteSpace: "pre-wrap",
                textAlign: "left",
              }}
            >
              {m.content || (streaming && i === messages.length - 1 ? <Spin size="small" /> : "")}
            </div>
            {m.citations && m.citations.length > 0 && (
              <Collapse
                size="small"
                style={{ maxWidth: "80%", marginTop: 4 }}
                items={[
                  {
                    key: "cites",
                    label: `引用来源 (${m.citations.length})`,
                    children: m.citations.map((c, j) => (
                      <div key={j} style={{ marginBottom: 8 }}>
                        <Typography.Text strong>
                          [{j + 1}] {c.filename} {c.page_number ? `第${c.page_number}页` : ""} (score {c.score.toFixed(3)})
                        </Typography.Text>
                        <div style={{ color: "#666", whiteSpace: "pre-wrap" }}>{c.content}</div>
                      </div>
                    )),
                  },
                ]}
              />
            )}
          </div>
        ))}
        <div ref={bottomRef} />
      </Card>

      <Space.Compact style={{ width: "100%" }}>
        <Input.TextArea
          rows={2}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onPressEnter={(e) => { if (!e.shiftKey) { e.preventDefault(); send(); } }}
          placeholder="输入问题，Enter 发送，Shift+Enter 换行"
        />
        <Button type="primary" icon={<SendOutlined />} loading={streaming} onClick={send} style={{ height: "auto" }}>
          发送
        </Button>
      </Space.Compact>
    </div>
  );
}
