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
} from "@ant-design/icons";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../store/auth";

const { Header, Sider, Content } = Layout;

const menuItems = [
  { key: "/", icon: <DashboardOutlined />, label: "总览" },
  { key: "/kbs", icon: <DatabaseOutlined />, label: "知识库管理" },
  { key: "/documents", icon: <FileTextOutlined />, label: "文档管理" },
  { key: "/retrieval", icon: <SearchOutlined />, label: "检索测试" },
  { key: "/chat", icon: <MessageOutlined />, label: "智能问答" },
  { key: "/api-keys", icon: <KeyOutlined />, label: "API Key 管理" },
  { key: "/api-usage", icon: <BarChartOutlined />, label: "API 调用统计" },
];

export default function MainLayout() {
  const navigate = useNavigate();
  const location = useLocation();
  const { username, role, logout } = useAuth();

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
          items={menuItems}
          onClick={(e) => navigate(e.key)}
        />
      </Sider>
      <Layout>
        <Header style={{ background: "#fff", display: "flex", justifyContent: "flex-end", paddingRight: 24 }}>
          <Dropdown
            menu={{
              items: [
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
                {username} ({role})
              </Typography.Text>
            </Space>
          </Dropdown>
        </Header>
        <Content style={{ margin: 16, padding: 24, background: "#fff", borderRadius: 8, overflow: "auto" }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}
