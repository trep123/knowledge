import { useEffect, useState } from "react";
import { Card, Col, Row, Statistic, Table, Typography } from "antd";
import client from "../api/client";

export default function ApiUsage() {
  const [summary, setSummary] = useState<any>(null);
  const [daily, setDaily] = useState<any[]>([]);
  const [logs, setLogs] = useState<any[]>([]);

  useEffect(() => {
    client.get("/api/v1/admin/api-usage?days=7").then((r) => setSummary(r.data)).catch(() => {});
    client.get("/api/v1/admin/api-usage/daily?days=30").then((r) => setDaily(r.data)).catch(() => {});
    client.get("/api/v1/admin/api-logs?limit=100").then((r) => setLogs(r.data)).catch(() => {});
  }, []);

  return (
    <div>
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}><Card><Statistic title="近7日请求数" value={summary?.total_requests ?? "-"} /></Card></Col>
        <Col span={6}><Card><Statistic title="平均耗时(ms)" value={summary?.avg_duration_ms ?? "-"} /></Card></Col>
        <Col span={6}><Card><Statistic title="错误数" value={summary?.error_count ?? "-"} /></Card></Col>
        <Col span={6}><Card><Statistic title="错误率" value={summary ? (summary.error_rate * 100).toFixed(2) + "%" : "-"} /></Card></Col>
      </Row>

      <Typography.Title level={5}>每日调用量（近30天）</Typography.Title>
      <Table
        rowKey="day"
        size="small"
        dataSource={daily}
        pagination={false}
        style={{ marginBottom: 24 }}
        columns={[
          { title: "日期", dataIndex: "day" },
          { title: "请求数", dataIndex: "count" },
          { title: "错误数", dataIndex: "errors" },
        ]}
      />

      <Typography.Title level={5}>最近调用日志（不含密钥明文）</Typography.Title>
      <Table
        rowKey="id"
        size="small"
        dataSource={logs}
        columns={[
          { title: "时间", dataIndex: "created_at", width: 180, render: (t) => t ? new Date(t).toLocaleString() : "-" },
          { title: "方法", dataIndex: "method", width: 70 },
          { title: "路径", dataIndex: "path", ellipsis: true },
          { title: "状态码", dataIndex: "status_code", width: 80 },
          { title: "耗时(ms)", dataIndex: "duration_ms", width: 90 },
          { title: "来源IP", dataIndex: "request_ip", width: 130 },
        ]}
      />
    </div>
  );
}
