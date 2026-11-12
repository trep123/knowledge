import { Layout, Menu, Dropdown, Avatar, Space, Typography } from "antd";
import {
  DashboardOutlined,
  DatabaseOutlined,
  FileTextOutlined,
  SearchOutlined,
  MessageOutlined,
  KeyOutlined,
  BarChartOutlined,
  UserOutlined,
  LogoutOutlined,
  TeamOutlined,
  LockOutlined,
} from "@ant-design/icons";
import { useState } from "react";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../store/auth";
import ChangePasswordModal from "../components/ChangePasswordModal";

const { Header, Sider, Content } = Layout;

const menuItems = [
  { key: "/", icon: <DashboardOutlined />, label: "总览" },
  { key: "/kbs", icon: <DatabaseOutlined />, label: "知识库管理" },
  { key: "/documents", icon: <FileTextOutlined />, label: "文档管理" },
  { key: "/retrieval", icon: <SearchOutlined />, label: "检索测试" },
  { key: "/chat", icon: <MessageOutlined />, label: "智能问答" },
  { key: "/users", icon: <TeamOutlined />, label: "用户管理", adminOnly: true },
  { key: "/api-keys", icon: <KeyOutlined />, label: "API Key 管理", adminOnly: true },
  { key: "/api-usage", icon: <BarChartOutlined />, label: "API 调用统计", adminOnly: true },
];

export default function MainLayout() {
  const navigate = useNavigate();
  const location = useLocation();
  const { username, role, logout } = useAuth();
  const [pwdOpen, setPwdOpen] = useState(false);
  const visibleItems = menuItems
    .filter((m) => !m.adminOnly || role === "admin")
    .map(({ adminOnly, ...m }) => m);

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Sider theme="dark" breakpoint="lg" collapsedWidth="0">
        <div style={{ color: "#fff", padding: 16, fontWeight: 600, fontSize: 15 }}>
          本地知识库平台
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[location.pathname]}
          items={visibleItems}
          onClick={(e) => navigate(e.key)}
        />
      </Sider>
      <Layout>
        <Header style={{ background: "#fff", display: "flex", justifyContent: "flex-end", paddingRight: 24 }}>
          <Dropdown
            menu={{
              items: [
                {
                  key: "password",
                  icon: <LockOutlined />,
                  label: "修改密码",
                  onClick: () => setPwdOpen(true),
                },
                {
                  key: "logout",
                  icon: <LogoutOutlined />,
                  label: "退出登录",
                  onClick: () => {
                    logout();
                    navigate("/login");
                  },
                },
              ],
            }}
          >
            <Space style={{ cursor: "pointer" }}>
              <Avatar icon={<UserOutlined />} />
              <Typography.Text>
                {username}（{role === "admin" ? "管理员" : "普通用户"}）
              </Typography.Text>
            </Space>
          </Dropdown>
        </Header>
        <Content style={{ margin: 16, padding: 24, background: "#fff", borderRadius: 8, overflow: "auto" }}>
          <Outlet />
        </Content>
        <ChangePasswordModal open={pwdOpen} onClose={() => setPwdOpen(false)} />
      </Layout>
    </Layout>
  );
}
