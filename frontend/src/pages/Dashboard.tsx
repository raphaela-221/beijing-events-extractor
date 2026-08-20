import { Spin } from 'antd'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { pipelineApi } from '../api/pipeline'
import { runsApi } from '../api/runs'
import { HealthStrip } from '../components/dashboard/HealthStrip'
import { NextActionCard } from '../components/dashboard/NextActionCard'
import { FlowCards } from '../components/dashboard/FlowCards'
import { StatBox } from '../components/dashboard/StatBox'
import { MiniRunList } from '../components/dashboard/MiniRunList'

// 总览仪表盘：健康检查条 + 下一步建议 + 4 步入口卡 + 统计 + 最近运行/发布
// 把 SOP 从文档变成界面（指南 §5.4）：系统告诉用户「现在该做什么」
export function Dashboard() {
  const nav = useNavigate()
  const { data: state, isLoading } = useQuery({
    queryKey: ['pipeline'],
    queryFn: pipelineApi.state,
  })
  const { data: runsPage } = useQuery({
    queryKey: ['runs', 'recent'],
    queryFn: () => runsApi.listRuns({ page: 1, page_size: 5 }),
  })

  if (isLoading || !state) {
    return <Spin />
  }
  const runs = runsPage?.items || []

  return (
    <>
      <div className="page-header">
        <div>
          <div className="page-title">总览仪表盘</div>
          <div className="page-sub">现在是什么状态、下一步该干什么，一眼看清</div>
        </div>
      </div>

      <HealthStrip checks={state.checks} />
      <NextActionCard action={state.next_action} />
      <FlowCards runs={runs} />
      <StatBox stats={state.stats} />

      <div className="two-col">
        <div className="card" style={{ margin: 0 }}>
          <div className="card-title">
            最近发布 <span className="hint">对外分享链接不变</span>
          </div>
          <div style={{ color: 'var(--text-tertiary)', fontSize: 13 }}>
            暂无发布记录（预览发布页 P1.6 上线后显示）
          </div>
          <a
            className="btn ghost sm"
            style={{ marginTop: 10 }}
            onClick={() => nav('/publish')}
          >
            前往预览与发布
          </a>
        </div>

        <div className="card" style={{ margin: 0 }}>
          <div className="card-title">
            最近运行{' '}
            <span className="hint">
              <a onClick={() => nav('/runs')}>查看全部</a>
            </span>
          </div>
          <MiniRunList runs={runs} />
        </div>
      </div>
    </>
  )
}
