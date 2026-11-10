import { useEffect, useState } from "react";
import { Alert, Button, Form, Input, InputNumber, message, Modal, Popconfirm, Select, Space, Table, Tag, Typography } from "antd";
import { CopyOutlined, PlusOutlined } from "@ant-design/icons";
import client from "../api/client";

const ALL_SCOPES = [
  "kb:read", "kb:search", "kb:chat",
  "kb:documents:read", "kb:documents:upload", "kb:documents:delete", "kb:admin",
];

export default function ApiKeys() {
  const [keys, setKeys] = useState<any[]>([]);
  const [kbs, setKbs] = useState<any[]>([]);
  const [modalOpen, setModalOpen] = useState(false);
  const [plainKey, setPlainKey] = useState<string | null>(null);
  const [form] = Form.useForm();

  const load = async () => {
    const { data } = await client.get("/api/v1/admin/api-keys");
    setKeys(data);
  };
  useEffect(() => {
    load();
    client.get("/api/v1/knowledge-bases").then((r) => setKbs(r.data)).catch(() => {});
  }, []);

  const create = async () => {
    const values = await form.validateFields();
    try {
      const { data } = await client.post("/api/v1/admin/api-keys", values);
      setPlainKey(data.api_key);
      setModalOpen(false);
      form.resetFields();
      load();
    } catch (e: any) {
      message.error(e.response?.data?.detail || "创建失败");
    }
  };

  const rotate = async (id: string) => {
    const { data } = await client.post(`/api/v1/admin/api-keys/${id}/rotate`);
    setPlainKey(data.api_key);
    load();
  };

  const toggleStatus = async (record: any) => {
    await client.put(`/api/v1/admin/api-keys/${record.id}`, {
      status: record.status === "active" ? "disabled" : "active",
    });
    load();
  };

  const remove = async (id: string) => {
    await client.delete(`/api/v1/admin/api-keys/${id}`);
    message.success("已删除");
    load();
  };

  return (
    <div>
      <Space style={{ marginBottom: 16 }}>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalOpen(true)}>创建 API Key</Button>
        <Typography.Text type="secondary">外部程序通过 Authorization: Bearer &lt;API Key&gt; 调用 /api/v1 与 /v1 接口</Typography.Text>
      </Space>

      <Table
        rowKey="id"
        dataSource={keys}
        columns={[
          { title: "名称", dataIndex: "name" },
          { title: "密钥前缀", dataIndex: "key_prefix", width: 120, render: (p) => <code>{p}…</code> },
          {
            title: "权限范围", dataIndex: "scopes", width: 260,
            render: (scopes: string[]) => scopes.map((s) => <Tag key={s}>{s}</Tag>),
          },
          {
            title: "授权知识库", dataIndex: "knowledge_base_ids", width: 200,
            render: (ids: string[]) =>
              ids.map((id) => <Tag key={id} color="blue">{kbs.find((k) => k.id === id)?.name || id.slice(0, 8)}</Tag>),
          },
          { title: "限流/分", dataIndex: "rate_limit", width: 90 },
          { title: "限额/日", dataIndex: "daily_limit", width: 90 },
          {
            title: "状态", dataIndex: "status", width: 90,
            render: (s) => <Tag color={s === "active" ? "green" : "red"}>{s}</Tag>,
          },
          { title: "最后使用", dataIndex: "last_used_at", width: 170, render: (t) => t ? new Date(t).toLocaleString() : "-" },
          {
            title: "操作", width: 220,
            render: (_, r) => (
              <Space>
                <Popconfirm title="轮换后旧密钥立即失效，确认？" onConfirm={() => rotate(r.id)}>
                  <Button size="small">轮换</Button>
                </Popconfirm>
                <Button size="small" onClick={() => toggleStatus(r)}>{r.status === "active" ? "禁用" : "启用"}</Button>
                <Popconfirm title="确认删除？" onConfirm={() => remove(r.id)}>
                  <Button size="small" danger>删除</Button>
                </Popconfirm>
              </Space>
            ),
          },
        ]}
      />

      <Modal title="创建 API Key" open={modalOpen} onOk={create} onCancel={() => setModalOpen(false)} destroyOnClose width={560}>
        <Form
          form={form}
          layout="vertical"
          initialValues={{ scopes: ["kb:read", "kb:search", "kb:chat"], rate_limit: 60, daily_limit: 10000 }}
        >
          <Form.Item name="name" label="名称" rules={[{ required: true }]}>
            <Input placeholder="例如：OA 系统接入" />
          </Form.Item>
          <Form.Item name="scopes" label="权限范围">
            <Select mode="multiple" options={ALL_SCOPES.map((s) => ({ value: s, label: s }))} />
          </Form.Item>
          <Form.Item name="knowledge_base_ids" label="授权知识库" rules={[{ required: true, message: "至少绑定一个知识库" }]}>
            <Select mode="multiple" options={kbs.map((k) => ({ value: k.id, label: k.name }))} />
          </Form.Item>
          <Form.Item name="default_kb_ids" label="默认知识库（OpenAI 兼容接口未传 kb_ids 时使用）">
            <Select mode="multiple" allowClear options={kbs.map((k) => ({ value: k.id, label: k.name }))} />
          </Form.Item>
          <Space>
            <Form.Item name="rate_limit" label="每分钟请求限制"><InputNumber min={1} max={10000} /></Form.Item>
            <Form.Item name="daily_limit" label="每日请求限制"><InputNumber min={1} /></Form.Item>
            <Form.Item name="expires_in_days" label="有效期（天，留空为永久）"><InputNumber min={1} max={3650} /></Form.Item>
          </Space>
        </Form>
      </Modal>

      <Modal title="API Key 已生成" open={plainKey !== null} onCancel={() => setPlainKey(null)} footer={null}>
        <Alert
          type="warning"
          showIcon
          message="明文密钥仅此一次展示，数据库只保存哈希。请立即复制并妥善保管。"
          style={{ marginBottom: 12 }}
        />
        <Space.Compact style={{ width: "100%" }}>
          <Input readOnly value={plainKey || ""} />
          <Button icon={<CopyOutlined />} onClick={() => { navigator.clipboard.writeText(plainKey || ""); message.success("已复制"); }} />
        </Space.Compact>
      </Modal>
    </div>
  );
}
