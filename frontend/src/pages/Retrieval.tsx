import { useEffect, useState } from "react";
import { Button, Card, Input, InputNumber, List, Select, Space, Switch, Tag, Typography } from "antd";
import client from "../api/client";

export default function Retrieval() {
  const [kbs, setKbs] = useState<any[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [query, setQuery] = useState("");
  const [topK, setTopK] = useState(5);
  const [rerank, setRerank] = useState(true);
  const [results, setResults] = useState<any[] | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    client.get("/api/v1/knowledge-bases").then((r) => {
      setKbs(r.data);
      setSelected(r.data.map((k: any) => k.id));
    });
  }, []);

  const search = async () => {
    if (!query.trim()) return;
    setLoading(true);
    try {
      const { data } = await client.post("/api/v1/search/hybrid", {
        knowledge_base_ids: selected,
        query,
        top_k: topK,
        rerank,
      });
      setResults(data.results);
    } catch (e: any) {
      setResults([]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <Card style={{ marginBottom: 16 }}>
        <Space direction="vertical" style={{ width: "100%" }}>
          <Space wrap>
            <Select
              mode="multiple"
              style={{ minWidth: 320 }}
              placeholder="选择知识库"
              value={selected}
              onChange={setSelected}
              options={kbs.map((k) => ({ value: k.id, label: k.name }))}
            />
            <InputNumber min={1} max={50} value={topK} onChange={(v) => setTopK(v || 5)} addonBefore="Top-K" />
            <Space><Typography.Text>Rerank</Typography.Text><Switch checked={rerank} onChange={setRerank} /></Space>
          </Space>
          <Space.Compact style={{ width: "100%" }}>
            <Input
              placeholder="输入检索问题，例如：虚拟化平台有哪些安全要求？"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onPressEnter={search}
            />
            <Button type="primary" loading={loading} onClick={search}>混合检索</Button>
          </Space.Compact>
        </Space>
      </Card>

      {results && (
        <List
          header={<Typography.Text strong>共 {results.length} 条结果（Dense + Sparse → RRF{rerank ? " → Reranker" : ""}）</Typography.Text>}
          dataSource={results}
          renderItem={(r, i) => (
            <List.Item>
              <List.Item.Meta
                title={
                  <Space>
                    <Tag color="blue">#{i + 1}</Tag>
                    <Typography.Text strong>{r.filename}</Typography.Text>
                    {r.page_number ? <Tag>第{r.page_number}页</Tag> : null}
                    <Tag color="green">score {r.score.toFixed(4)}</Tag>
                  </Space>
                }
                description={<div style={{ whiteSpace: "pre-wrap" }}>{r.content}</div>}
              />
            </List.Item>
          )}
        />
      )}
    </div>
  );
}
