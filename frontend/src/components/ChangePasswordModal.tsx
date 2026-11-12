import { Form, Input, message, Modal } from "antd";
import client from "../api/client";
import { useAuth } from "../store/auth";

export default function ChangePasswordModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [form] = Form.useForm();
  const login = useAuth((s) => s.login);

  const submit = async () => {
    const { old_password, new_password } = await form.validateFields();
    try {
      const { data } = await client.put("/api/v1/auth/me/password", { old_password, new_password });
      // 旧 Token 已失效，换成新 Token
      login(data.access_token, data.username, data.role);
      message.success("密码已修改，其他设备上的登录已失效");
      form.resetFields();
      onClose();
    } catch (e: any) {
      const d = e.response?.data?.detail;
      message.error(Array.isArray(d) ? d.map((x: any) => x.msg).join("；") : d || "修改失败");
    }
  };

  return (
    <Modal title="修改密码" open={open} onOk={submit} onCancel={() => { form.resetFields(); onClose(); }} destroyOnClose>
      <Form form={form} layout="vertical">
        <Form.Item name="old_password" label="原密码" rules={[{ required: true, message: "请输入原密码" }]}>
          <Input.Password autoComplete="current-password" />
        </Form.Item>
        <Form.Item
          name="new_password"
          label="新密码"
          rules={[
            { required: true, message: "请输入新密码" },
            { min: 8, max: 128, message: "密码长度需为 8-128 位" },
            { pattern: /^(?=.*[A-Za-z])(?=.*\d).+$/, message: "密码需同时包含字母和数字" },
          ]}
        >
          <Input.Password autoComplete="new-password" />
        </Form.Item>
        <Form.Item
          name="confirm"
          label="确认新密码"
          dependencies={["new_password"]}
          rules={[
            { required: true, message: "请再次输入新密码" },
            ({ getFieldValue }) => ({
              validator: (_, v) =>
                !v || v === getFieldValue("new_password") ? Promise.resolve() : Promise.reject(new Error("两次输入不一致")),
            }),
          ]}
        >
          <Input.Password autoComplete="new-password" />
        </Form.Item>
      </Form>
    </Modal>
  );
}
