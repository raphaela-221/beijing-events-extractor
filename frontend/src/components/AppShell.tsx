import { useEffect } from 'react'
import { Layout, Menu, Avatar, Typography, theme as antdTheme } from 'antd'
import { useLocation, useNavigate, Outlet } from 'react-router-dom'
import { useAuthStore } from '../stores/useAuthStore'
import { useLockStore } from '../stores/useLockStore'
import { fmtDateTime } from '../utils/format'

const { Sider, Header, Content } = Layout

const NAV_FLOW = [
  { key: '/', label: '总览仪表盘' },
  { key: '/step1', label: 'Step 1 上传与抽取' },
  { key: '/review', label: '人工核对' },
  { key: '/step2', label: 'Step 2 生成日历' },
  { key: '/publish', label: '预览与发布' },
]
const NAV_ADMIN = [
  { key: '/toolbox', label: '工具箱' },
  { key: '/runs', label: '运行记录' },
  { key: '/settings', label: '设置' },
]

export function AppShell() {
  const nav = useNavigate()
  const loc = useLocation()
  const user = useAuthStore((s) => s.user)
  const logout = useAuthStore((s) => s.logout)
  const { held, holder, since, is_me, refresh } = useLockStore()
  const { token } = antdTheme.useToken()

  useEffect(() => {
    refresh()
    const t = setInterval(refresh, 5000)
    return () => clearInterval(t)
  }, [refresh])

  // 当前选中：取路径首段
  const selected =
    NAV_FLOW.concat(NAV_ADMIN).find((n) => loc.pathname.startsWith(n.key) && n.key !== '/')?.key ||
        (loc.pathname === '/' ? '/' : '')

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider width={220} style={{ background: '#1E1B3A' }}>
        <div
          style={{
            padding: '12px 20px 18px',
            color: '#fff',
            fontSize: 14,
            fontWeight: 600,
            borderBottom: '1px solid rgba(255,255,255,0.08)',
            marginBottom: 8,
          }}
        >
          北京大事件操作台
          <div style={{ fontSize: 11, fontWeight: 400, color: '#9491C0', marginTop: 2 }}>
            Beijing Events Console
          </div>
        </div>
        <div style={{ padding: '12px 20px 6px', fontSize: 11, color: '#726FA0', letterSpacing: '.04em' }}>
          流程
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={selected ? [selected] : []}
          style={{ background: 'transparent', borderInlineEnd: 'none' }}
          items={NAV_FLOW.map((n) => ({ key: n.key, label: n.label }))}
          onClick={({ key }) => nav(key)}
        />
        <div style={{ padding: '12px 20px 6px', fontSize: 11, color: '#726FA0', letterSpacing: '.04em' }}>
          管理
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={selected ? [selected] : []}
          style={{ background: 'transparent', borderInlineEnd: 'none' }}
          items={NAV_ADMIN.map((n) => ({ key: n.key, label: n.label }))}
          onClick={({ key }) => nav(key)}
        />
      </Sider>
      <Layout>
        <Header
          style={{
            background: '#fff',
            borderBottom: '1px solid #E5E7EB',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '0 16px 0 20px',
            height: 48,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: '#6B7280' }}>
            <span
              style={{
                width: 7,
                height: 7,
                borderRadius: '50%',
                display: 'inline-block',
                background: held ? '#2563EB' : '#6B7280',
                boxShadow: held ? '0 0 0 3px #EFF6FF' : 'none',
              }}
            />
            {held
              ? is_me
                ? `本人持有编辑锁 · ${fmtDateTime(since)} 起（跑完自动释放）`
                : `${holder} 持有编辑锁 · ${fmtDateTime(since)} 起`
              : '当前无人占用编辑锁'}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 13, color: '#6B7280' }}>
            <Typography.Text style={{ fontSize: 13, color: '#6B7280' }}>
              {user?.display_name} · {user?.role === 'admin' ? '管理员' : '操作员'}
            </Typography.Text>
            <Avatar size={26} style={{ background: '#EEF2FF', color: '#4F46E5', fontSize: 12, fontWeight: 600 }}>
              {user?.display_name?.[0] || '?'}
            </Avatar>
            <a
              onClick={async () => {
                await logout()
                nav('/login')
              }}
              style={{ fontSize: 12, color: token.colorTextTertiary }}
            >
              退出
            </a>
          </div>
        </Header>
        <Content style={{ padding: '20px 24px 40px', overflowX: 'hidden' }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  )
}
