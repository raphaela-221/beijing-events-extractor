import { Card, Empty, Typography } from 'antd'

export function Placeholder({ title }: { title: string }) {
  return (
    <Card>
      <div style={{ marginBottom: 8 }}>
        <Typography.Text style={{ fontSize: 18, fontWeight: 600 }}>{title}</Typography.Text>
      </div>
      <Empty description={`${title} · P1 阶段上线`} />
    </Card>
  )
}
