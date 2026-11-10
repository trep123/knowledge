import { Button, Card, Form, Input, message, Typography } from "antd";
import { LockOutlined, UserOutlined } from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import client from "../api/client";
import { useAuth } from "../store/auth";

export default function Login() {
  const navigate = useNavigate();
  const login = useAuth((s) => s.login);

  const onFinish = async (values: { username: string; password: string }) => {
    try {
      const { data } = await client.post("/api/v1/auth/login", values);
      login(data.access_token, data.username, data.role);
      message.success("登录成功");
      navigate("/");
    } catch (e: any) {
      message.error(e.response?.data?.detail || "登录失败");
    }
  };

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "#f0f2f5",
      }}
    >
      <Card style={{ width: 380 }}>
        <Typography.Title level={3} style={{ textAlign: "center" }}>
          本地知识库平台
        </Typography.Title>
        <Form onFinish={onFinish} size="large">
          <Form.Item name="username" rules={[{ required: true, message: "请输入用户名" }]}>
            <Input prefix={<UserOutlined />} placeholder="用户名" />
          </Form.Item>
          <Form.Item name="password" rules={[{ required: true, message: "请输入密码" }]}>
            <Input.Password prefix={<LockOutlined />} placeholder="密码" />
          </Form.Item>
          <Button type="primary" htmlType="submit" block>
            登录
          </Button>
        </Form>
      </Card>
    </div>
  );
}
