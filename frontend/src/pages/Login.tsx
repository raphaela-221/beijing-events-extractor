import { useEffect, useState } from 'react'
import { Card, Form, Input, Button, App as AntdApp, Typography } from 'antd'
import { useNavigate, useLocation } from 'react-router-dom'
import { useAuthStore } from '../stores/useAuthStore'

export function Login() {
  const login = useAuthStore((s) => s.login)
  const user = useAuthStore((s) => s.user)
  const nav = useNavigate()
  const loc = useLocation()
  const { message } = AntdApp.useApp()
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (user) {
      const from = (loc.state as { from?: string } | null)?.from || '/step1'
      nav(from, { replace: true })
    }
  }, [user, nav, loc.state])

  const onFinish = async (v: { username: string; password: string }) => {
    setLoading(true)
    try {
      await login(v.username, v.password)
      message.success('登录成功')
    } catch (e) {
      message.error((e as Error).message || '登录失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: '#F5F6F8',
      }}
    >
      <Card style={{ width: 380, boxShadow: '0 1px 6px rgba(0,0,0,0.06)' }}>
        <Typography.Title level={4} style={{ marginBottom: 4 }}>
          北京大事件操作台
        </Typography.Title>
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          Beijing Events Console
        </Typography.Text>
        <Form layout="vertical" onFinish={onFinish} style={{ marginTop: 20 }} size="middle">
          <Form.Item label="用户名" name="username" rules={[{ required: true }]}>
            <Input placeholder="admin / operator" autoFocus />
          </Form.Item>
          <Form.Item label="密码" name="password" rules={[{ required: true }]}>
            <Input.Password placeholder="change-me" />
          </Form.Item>
          <Button type="primary" htmlType="submit" block loading={loading}>
            登录
          </Button>
        </Form>
        <Typography.Text type="secondary" style={{ fontSize: 11 }}>
          首次部署后请用 <code>python -m backend.cli set-password &lt;user&gt;</code> 改密码。
        </Typography.Text>
      </Card>
    </div>
  )
}
