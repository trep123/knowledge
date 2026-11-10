import { useEffect, useState } from "react";
import { Button, Form, Input, InputNumber, message, Modal, Popconfirm, Space, Table, Tag } from "antd";
import { PlusOutlined, DeleteOutlined } from "@ant-design/icons";
import client from "../api/client";
import { useAuth } from "../store/auth";

export default function KnowledgeBases() {
  const [data, setData] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [selected, setSelected] = useState<React.Key[]>([]);
  const [form] = Form.useForm();
  const role = useAuth((s) => s.role);

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await client.get("/api/v1/knowledge-bases");
      setData(data);
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { load(); }, []);

  const create = async () => {
    const values = await form.validateFields();
    try {
      await client.post("/api/v1/knowledge-bases", values);
      message.success("知识库已创建");
      setModalOpen(false);
      form.resetFields();
      load();
    } catch (e: any) {
      message.error(e.response?.data?.detail || "创建失败");
    }
  };

  const remove = async (id: string) => {
    try {
      await client.delete(`/api/v1/knowledge-bases/${id}`);
      message.success("已删除（含向量与文档文件）");
      load();
    } catch (e: any) {
      message.error(e.response?.data?.detail || "删除失败");
    }
  };

  const batchDelete = () => {
    if (!selected.length) return;
    Modal.confirm({
      title: `批量删除 ${selected.length} 个知识库？`,
      content: "将同时删除其全部文档、向量与文件，且不可恢复。",
      okText: "删除",
      okButtonProps: { danger: true },
      cancelText: "取消",
      onOk: async () => {
        try {
          const { data } = await client.post("/api/v1/knowledge-bases/batch-delete", { ids: selected });
          if (data.failed) {
            message.warning(`成功 ${data.succeeded} 个，失败 ${data.failed} 个`);
          } else {
            message.success(`已删除 ${data.succeeded} 个知识库`);
          }
          setSelected([]);
          load();
        } catch (e: any) {
          message.error(e.response?.data?.detail || "批量删除失败");
        }
      },
    });
  };

  const isAdmin = role === "admin";

  return (
    <div>
      <Space style={{ marginBottom: 16 }}>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalOpen(true)}>新建知识库</Button>
        {isAdmin && (
          <Button danger icon={<DeleteOutlined />} disabled={!selected.length} onClick={batchDelete}>
            批量删除{selected.length ? `（${selected.length}）` : ""}
          </Button>
        )}
      </Space>
      <Table
        rowKey="id"
        loading={loading}
        dataSource={data}
        rowSelection={isAdmin ? { selectedRowKeys: selected, onChange: setSelected } : undefined}
        columns={[
          { title: "名称", dataIndex: "name" },
          { title: "描述", dataIndex: "description", ellipsis: true },
          { title: "文档数", dataIndex: "document_count", width: 90 },
          { title: "向量模型", dataIndex: "embedding_model", width: 120 },
          { title: "维度", dataIndex: "embedding_dimension", width: 80 },
          { title: "切片(字符)", width: 110, render: (_, r) => `${r.chunk_size}/${r.chunk_overlap}` },
          { title: "状态", dataIndex: "status", width: 90, render: (s) => <Tag color={s === "active" ? "green" : "default"}>{s}</Tag> },
          {
            title: "操作", width: 100,
            render: (_, r) =>
              role === "admin" ? (
                <Popconfirm title="删除知识库及其全部文档、向量？" onConfirm={() => remove(r.id)}>
                  <Button danger size="small">删除</Button>
                </Popconfirm>
              ) : null,
          },
        ]}
      />
      <Modal title="新建知识库" open={modalOpen} onOk={create} onCancel={() => setModalOpen(false)} destroyOnClose>
        <Form form={form} layout="vertical" initialValues={{ chunk_size: 800, chunk_overlap: 120 }}>
          <Form.Item name="name" label="名称" rules={[{ required: true }]}>
            <Input placeholder="例如：运维知识库" />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Space>
            <Form.Item name="chunk_size" label="切片长度（字符）">
              <InputNumber min={100} max={4000} />
            </Form.Item>
            <Form.Item name="chunk_overlap" label="重叠（字符）">
              <InputNumber min={0} max={1000} />
            </Form.Item>
          </Space>
        </Form>
      </Modal>
    </div>
  );
}
