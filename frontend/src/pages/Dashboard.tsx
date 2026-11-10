import { useEffect, useState } from "react";
import { Card, Col, Row, Statistic, Tag, Typography, Alert } from "antd";
import client from "../api/client";

export default function Dashboard() {
  const [stats, setStats] = useState<any>(null);
  const [health, setHealth] = useState<any>(null);

  useEffect(() => {
    client.get("/api/v1/stats").then((r) => setStats(r.data)).catch(() => {});
    client.get("/api/health/dependencies").then((r) => setHealth(r.data)).catch(() => {});
  }, []);

  return (
    <div>
      <Typography.Title level={4}>系统总览</Typography.Title>
      {health && health.status !== "ok" && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 16 }}
          message="部分依赖服务异常，请检查模型服务是否仍在加载（首次启动加载模型需要 1-3 分钟）"
        />
      )}
      <Row gutter={[16, 16]}>
        <Col xs={12} md={6}><Card><Statistic title="知识库总数" value={stats?.knowledge_bases ?? "-"} /></Card></Col>
        <Col xs={12} md={6}><Card><Statistic title="文档总数" value={stats?.documents ?? "-"} /></Card></Col>
        <Col xs={12} md={6}><Card><Statistic title="切片总数（向量数）" value={stats?.chunks ?? "-"} /></Card></Col>
        <Col xs={12} md={6}><Card><Statistic title="外部 API 调用" value={stats?.api_calls_total ?? "-"} /></Card></Col>
        <Col xs={12} md={6}><Card><Statistic title="处理完成文档" value={stats?.documents_ready ?? "-"} /></Card></Col>
        <Col xs={12} md={6}><Card><Statistic title="处理失败文档" value={stats?.documents_failed ?? "-"} valueStyle={stats?.documents_failed ? { color: "#cf1322" } : undefined} /></Card></Col>
      </Row>

      <Typography.Title level={5} style={{ marginTop: 24 }}>依赖服务状态</Typography.Title>
      <Card>
        {health ? (
          Object.entries(health.checks || {}).map(([name, status]) => (
            <Tag key={name} color={status === "ok" ? "green" : "red"} style={{ marginBottom: 8 }}>
              {name}: {String(status)}
            </Tag>
          ))
        ) : (
          <Typography.Text type="secondary">加载中…</Typography.Text>
        )}
      </Card>
    </div>
  );
}
