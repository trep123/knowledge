import { useEffect, useState } from "react";
import {
  Button, Form, Input, message, Modal, Popconfirm, Select, Space, Table, Tag, Tooltip, Typography,
} from "antd";
import { PlusOutlined, ReloadOutlined } from "@ant-design/icons";
import dayjs from "dayjs";
import client from "../api/client";
import { useAuth } from "../store/auth";

interface UserRow {
  id: string;
  username: string;
  email: string | null;
  role: "admin" | "user";
  status: "active" | "disabled";
  last_login_at: string | null;
  locked_until: string | null;
  created_at: string;
}

const PASSWORD_RULES = [
  { required: true, message: "请输入密码" },
  { min: 8, max: 128, message: "密码长度需为 8-128 位" },
  { pattern: /^(?=.*[A-Za-z])(?=.*\d).+$/, message: "密码需同时包含字母和数字" },
];

const ROLE_OPTIONS = [
  { value: "user", label: "普通用户" },
  { value: "admin", label: "管理员" },
];

const fmt = (t: string | null) => (t ? dayjs(t).format("YYYY-MM-DD HH:mm") : "—");
const errMsg = (e: any, fallback: string) => {
  const d = e.response?.data?.detail;
  if (Array.isArray(d)) return d.map((x: any) => x.msg).join("；");
  return d || fallback;
};

export default function Users() {
  const myName = useAuth((s) => s.username);
  const [rows, setRows] = useState<UserRow[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [query, setQuery] = useState({ q: "", role: undefined as string | undefined, status: undefined as string | undefined, page: 1, pageSize: 20 });
  const [createOpen, setCreateOpen] = useState(false);
  const [editing, setEditing] = useState<UserRow | null>(null);
  const [resetting, setResetting] = useState<UserRow | null>(null);
  const [createForm] = Form.useForm();
  const [editForm] = Form.useForm();
  const [resetForm] = Form.useForm();

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await client.get("/api/v1/admin/users", {
        params: {
          q: query.q || undefined,
          role: query.role,
          status: query.status,
          skip: (query.page - 1) * query.pageSize,
          limit: query.pageSize,
        },
      });
      setRows(data.items);
      setTotal(data.total);
    } catch (e: any) {
      message.error(errMsg(e, "加载用户失败"));
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { load(); }, [query]);

  const create = async () => {
    const values = await createForm.validateFields();
    try {
      await client.post("/api/v1/admin/users", values);
      message.success("用户已创建");
      setCreateOpen(false);
      createForm.resetFields();
      load();
    } catch (e: any) {
      message.error(errMsg(e, "创建失败"));
    }
  };

  const saveEdit = async () => {
    if (!editing) return;
    const values = await editForm.validateFields();
    try {
      await client.put(`/api/v1/admin/users/${editing.id}`, values);
      message.success("已保存");
      setEditing(null);
      load();
    } catch (e: any) {
      message.error(errMsg(e, "保存失败"));
    }
  };

  const resetPassword = async () => {
    if (!resetting) return;
    const { new_password } = await resetForm.validateFields();
    try {
      await client.post(`/api/v1/admin/users/${resetting.id}/reset-password`, { new_password });
      message.success(`已重置 ${resetting.username} 的密码，其已登录会话已失效`);
      setResetting(null);
      resetForm.resetFields();
      load();
    } catch (e: any) {
      message.error(errMsg(e, "重置失败"));
    }
  };

  const toggleStatus = async (r: UserRow) => {
    try {
      await client.put(`/api/v1/admin/users/${r.id}`, { status: r.status === "active" ? "disabled" : "active" });
      load();
    } catch (e: any) {
      message.error(errMsg(e, "操作失败"));
    }
  };

  const unlock = async (r: UserRow) => {
    try {
      await client.post(`/api/v1/admin/users/${r.id}/unlock`);
      message.success("已解锁");
      load();
    } catch (e: any) {
      message.error(errMsg(e, "解锁失败"));
    }
  };

  const remove = async (r: UserRow) => {
    try {
      await client.delete(`/api/v1/admin/users/${r.id}`);
      message.success("已删除");
      load();
    } catch (e: any) {
      message.error(errMsg(e, "删除失败"));
    }
  };

  const isLocked = (r: UserRow) => !!r.locked_until && dayjs(r.locked_until).isAfter(dayjs());

  return (
    <div>
      <Space style={{ marginBottom: 16 }} wrap>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>新建用户</Button>
        <Input.Search
          allowClear
          placeholder="搜索用户名或邮箱"
          style={{ width: 220 }}
          onSearch={(q) => setQuery({ ...query, q, page: 1 })}
        />
        <Select allowClear placeholder="角色" style={{ width: 120 }} options={ROLE_OPTIONS}
          onChange={(role) => setQuery({ ...query, role, page: 1 })} />
        <Select allowClear placeholder="状态" style={{ width: 120 }}
          options={[{ value: "active", label: "启用" }, { value: "disabled", label: "禁用" }]}
          onChange={(status) => setQuery({ ...query, status, page: 1 })} />
        <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
      </Space>

      <Table<UserRow>
        rowKey="id"
        loading={loading}
        dataSource={rows}
        pagination={{
          current: query.page,
          pageSize: query.pageSize,
          total,
          showTotal: (t) => `共 ${t} 个用户`,
          onChange: (page, pageSize) => setQuery({ ...query, page, pageSize }),
        }}
        columns={[
          {
            title: "用户名", dataIndex: "username",
            render: (name: string) => (name === myName ? <Space>{name}<Tag>我</Tag></Space> : name),
          },
          { title: "邮箱", dataIndex: "email", render: (e) => e || "—" },
          {
            title: "角色", dataIndex: "role", width: 100,
            render: (r) => <Tag color={r === "admin" ? "gold" : "blue"}>{r === "admin" ? "管理员" : "普通用户"}</Tag>,
          },
          {
            title: "状态", dataIndex: "status", width: 110,
            render: (_, r) => (
              <Space size={4}>
                <Tag color={r.status === "active" ? "green" : "default"}>{r.status === "active" ? "启用" : "禁用"}</Tag>
                {isLocked(r) && (
                  <Tooltip title={`锁定至 ${fmt(r.locked_until)}`}><Tag color="red">锁定</Tag></Tooltip>
                )}
              </Space>
            ),
          },
          { title: "最近登录", dataIndex: "last_login_at", width: 150, render: fmt },
          { title: "创建时间", dataIndex: "created_at", width: 150, render: fmt },
          {
            title: "操作", width: 300,
            render: (_, r) => {
              const self = r.username === myName;
              return (
                <Space size="small" wrap>
                  <Button size="small" onClick={() => { setEditing(r); editForm.setFieldsValue({ email: r.email, role: r.role }); }}>
                    编辑
                  </Button>
                  <Button size="small" onClick={() => setResetting(r)}>重置密码</Button>
                  {isLocked(r) && <Button size="small" onClick={() => unlock(r)}>解锁</Button>}
                  {!self && (
                    <Button size="small" onClick={() => toggleStatus(r)}>{r.status === "active" ? "禁用" : "启用"}</Button>
                  )}
                  {!self && (
                    <Popconfirm title={`删除用户 ${r.username}？`} description="拥有知识库或 API Key 的用户需先转移，或改为禁用。" onConfirm={() => remove(r)}>
                      <Button size="small" danger>删除</Button>
                    </Popconfirm>
                  )}
                </Space>
              );
            },
          },
        ]}
      />

      <Modal title="新建用户" open={createOpen} onOk={create} onCancel={() => setCreateOpen(false)} destroyOnClose>
        <Form form={createForm} layout="vertical" initialValues={{ role: "user" }} preserve={false}>
          <Form.Item name="username" label="用户名"
            rules={[{ required: true, message: "请输入用户名" }, { pattern: /^[A-Za-z0-9_.-]{3,50}$/, message: "3-50 位字母、数字、_ . -" }]}>
            <Input autoComplete="off" />
          </Form.Item>
          <Form.Item name="password" label="初始密码" rules={PASSWORD_RULES}>
            <Input.Password autoComplete="new-password" />
          </Form.Item>
          <Form.Item name="email" label="邮箱" rules={[{ type: "email", message: "邮箱格式不正确" }]}>
            <Input />
          </Form.Item>
          <Form.Item name="role" label="角色">
            <Select options={ROLE_OPTIONS} />
          </Form.Item>
          <Typography.Text type="secondary">普通用户只能访问被授权的知识库，可检索、问答、上传文档；管理员拥有全部权限。</Typography.Text>
        </Form>
      </Modal>

      <Modal title={`编辑用户 ${editing?.username ?? ""}`} open={!!editing} onOk={saveEdit} onCancel={() => setEditing(null)} destroyOnClose>
        <Form form={editForm} layout="vertical">
          <Form.Item name="email" label="邮箱" rules={[{ type: "email", message: "邮箱格式不正确" }]}>
            <Input allowClear />
          </Form.Item>
          <Form.Item name="role" label="角色" extra={editing?.username === myName ? "不能修改自己的角色" : "修改角色会使该用户重新登录"}>
            <Select options={ROLE_OPTIONS} disabled={editing?.username === myName} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal title={`重置 ${resetting?.username ?? ""} 的密码`} open={!!resetting} onOk={resetPassword}
        onCancel={() => { setResetting(null); resetForm.resetFields(); }} destroyOnClose>
        <Form form={resetForm} layout="vertical">
          <Form.Item name="new_password" label="新密码" rules={PASSWORD_RULES}>
            <Input.Password autoComplete="new-password" />
          </Form.Item>
          <Typography.Text type="secondary">重置后该用户的锁定会解除，已登录的会话会全部失效。</Typography.Text>
        </Form>
      </Modal>
    </div>
  );
}
