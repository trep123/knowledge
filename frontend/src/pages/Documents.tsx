import { useEffect, useState } from "react";
import { Button, Drawer, List, message, Modal, Popconfirm, Select, Space, Table, Tag, Typography, Upload } from "antd";
import { UploadOutlined, ReloadOutlined, DeleteOutlined, RedoOutlined } from "@ant-design/icons";
import client from "../api/client";
import { useAuth } from "../store/auth";

const statusColor: Record<string, string> = {
  pending: "default",
  processing: "blue",
  ready: "green",
  failed: "red",
};

export default function Documents() {
  const canDelete = useAuth((s) => s.role) === "admin"; // 普通用户角色没有 kb:documents:delete
  const [kbs, setKbs] = useState<any[]>([]);
  const [kbId, setKbId] = useState<string>();
  const [docs, setDocs] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [chunks, setChunks] = useState<any[] | null>(null);
  const [uploading, setUploading] = useState(false);
  const [selected, setSelected] = useState<React.Key[]>([]);

  useEffect(() => {
    client.get("/api/v1/knowledge-bases").then((r) => {
      setKbs(r.data);
      if (r.data.length) setKbId(r.data[0].id);
    });
  }, []);

  const load = async () => {
    if (!kbId) return;
    setLoading(true);
    try {
      const { data } = await client.get(`/api/v1/knowledge-bases/${kbId}/documents`);
      setDocs(data);
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { setSelected([]); load(); }, [kbId]);

  // 有处理中的文档时自动刷新
  useEffect(() => {
    if (docs.some((d) => d.status === "processing" || d.status === "pending")) {
      const t = setTimeout(load, 3000);
      return () => clearTimeout(t);
    }
  }, [docs]);

  const uploadBatch = async (fileList: File[]) => {
    if (!kbId || !fileList.length) return;
    const form = new FormData();
    fileList.forEach((f) => form.append("files", f));
    setUploading(true);
    try {
      const { data } = await client.post(`/api/v1/knowledge-bases/${kbId}/documents/batch`, form);
      const dup = data.results.filter((r: any) => r.action === "duplicate").length;
      if (data.failed) {
        const firstErr = data.results.find((r: any) => !r.ok)?.error || "";
        message.warning(`成功 ${data.succeeded} 个，失败 ${data.failed} 个${firstErr ? `（${firstErr}）` : ""}`);
      } else {
        message.success(`上传 ${data.succeeded} 个文件${dup ? `，其中 ${dup} 个重复已跳过` : ""}`);
      }
      load();
    } catch (e: any) {
      message.error(e.response?.data?.detail || "上传失败");
    } finally {
      setUploading(false);
    }
  };

  const batchAction = (kind: "delete" | "reprocess") => {
    if (!selected.length) return;
    const isDelete = kind === "delete";
    const run = async () => {
      const url = isDelete ? "/api/v1/documents/batch-delete" : "/api/v1/documents/batch-reprocess";
      try {
        const { data } = await client.post(url, { ids: selected });
        const verb = isDelete ? "删除" : "重新提交处理";
        if (data.failed) message.warning(`${verb}：成功 ${data.succeeded} 个，失败 ${data.failed} 个`);
        else message.success(`已${verb} ${data.succeeded} 个文档`);
        setSelected([]);
        load();
      } catch (e: any) {
        message.error(e.response?.data?.detail || "批量操作失败");
      }
    };
    if (isDelete) {
      Modal.confirm({
        title: `批量删除 ${selected.length} 个文档？`,
        content: "将同时删除其向量数据与文件，且不可恢复。",
        okText: "删除",
        okButtonProps: { danger: true },
        cancelText: "取消",
        onOk: run,
      });
    } else {
      run();
    }
  };

  const showChunks = async (docId: string) => {
    const { data } = await client.get(`/api/v1/documents/${docId}/chunks?limit=200`);
    setChunks(data);
  };

  return (
    <div>
      <Space style={{ marginBottom: 16 }} wrap>
        <Select
          style={{ width: 260 }}
          placeholder="选择知识库"
          value={kbId}
          onChange={setKbId}
          options={kbs.map((k) => ({ value: k.id, label: k.name }))}
        />
        <Upload
          beforeUpload={(file, fileList) => {
            if (file === fileList[0]) uploadBatch(fileList as unknown as File[]);
            return false;
          }}
          showUploadList={false}
          multiple
        >
          <Button type="primary" icon={<UploadOutlined />} loading={uploading} disabled={!kbId}>
            上传文档（可多选）
          </Button>
        </Upload>
        <Button icon={<RedoOutlined />} disabled={!selected.length} onClick={() => batchAction("reprocess")}>
          批量重处理{selected.length ? `（${selected.length}）` : ""}
        </Button>
        {canDelete && (
          <Button danger icon={<DeleteOutlined />} disabled={!selected.length} onClick={() => batchAction("delete")}>
            批量删除{selected.length ? `（${selected.length}）` : ""}
          </Button>
        )}
        <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
        <Typography.Text type="secondary">支持 PDF / DOCX / MD / TXT / 图片（扫描版自动 OCR）</Typography.Text>
      </Space>
      <Table
        rowKey="id"
        loading={loading}
        dataSource={docs}
        rowSelection={{ selectedRowKeys: selected, onChange: setSelected }}
        columns={[
          { title: "文件名", dataIndex: "filename", ellipsis: true },
          { title: "类型", dataIndex: "file_type", width: 70 },
          { title: "大小", dataIndex: "file_size", width: 100, render: (s) => `${(s / 1024).toFixed(1)} KB` },
          { title: "页数", dataIndex: "page_count", width: 70 },
          { title: "切片", dataIndex: "chunk_count", width: 70 },
          {
            title: "状态", dataIndex: "status", width: 110,
            render: (s, r) => <Tag color={statusColor[s]}>{s}{s === "failed" && r.error_message ? `: ${r.error_message.slice(0, 40)}` : ""}</Tag>,
          },
          {
            title: "操作", width: 240,
            render: (_, r) => (
              <Space>
                <Button size="small" onClick={() => showChunks(r.id)} disabled={r.status !== "ready"}>切片</Button>
                <Button size="small" onClick={async () => { await client.post(`/api/v1/documents/${r.id}/reprocess`); message.success("已重新提交处理"); load(); }}>
                  重处理
                </Button>
                {canDelete && (
                  <Popconfirm title="删除文档及其向量？" onConfirm={async () => { await client.delete(`/api/v1/documents/${r.id}`); load(); }}>
                    <Button size="small" danger>删除</Button>
                  </Popconfirm>
                )}
              </Space>
            ),
          },
        ]}
      />
      <Drawer title="文档切片" width={640} open={chunks !== null} onClose={() => setChunks(null)}>
        <List
          dataSource={chunks || []}
          renderItem={(c: any) => (
            <List.Item>
              <List.Item.Meta
                title={`#${c.chunk_index} ${c.page_number ? `· 第${c.page_number}页` : ""}`}
                description={<div style={{ whiteSpace: "pre-wrap" }}>{c.content}</div>}
              />
            </List.Item>
          )}
        />
      </Drawer>
    </div>
  );
}
