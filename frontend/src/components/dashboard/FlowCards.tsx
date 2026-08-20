import { useNavigate } from 'react-router-dom'
import type { Run } from '../../api/runs'
import { fmtDateTime } from '../../utils/format'

const STEPS = [
  { n: 1, title: 'Step 1 上传与抽取', link: '/step1', groups: ['抽取'] },
  { n: 2, title: '人工核对', link: '/review', groups: [] },
  { n: 3, title: 'Step 2 生成日历', link: '/step2', groups: ['日历生成'] },
  { n: 4, title: '预览与发布', link: '/publish', groups: ['发布'] },
]

function lastRunFor(runs: Run[], groups: string[]): Run | undefined {
  if (!groups.length) return undefined
  return runs.find((r) => groups.includes(r.op_group))
}

function stateOf(last: Run | undefined): { cls: string; badge: string } {
  if (!last) return { cls: '', badge: '待开始' }
  if (last.status === 'running' || last.status === 'queued') return { cls: 'current', badge: '进行中' }
  if (last.status === 'success') return { cls: 'done', badge: '已完成' }
  return { cls: '', badge: '待开始' }
}

const BADGE_CLS: Record<string, string> = {
  已完成: 'success',
  进行中: 'running',
  待开始: 'idle',
}

// 流程四步入口卡：每卡显示编号 + 标题 + 最近运行状态（指南附录 C FlowCards）
export function FlowCards({ runs }: { runs: Run[] }) {
  const nav = useNavigate()
  return (
    <div className="flow-cards">
      {STEPS.map((s) => {
        const last = lastRunFor(runs, s.groups)
        const st = stateOf(last)
        const num = st.cls === 'done' ? '✓' : s.n
        const sub = last
          ? `最近：${fmtDateTime(last.started_at)} · ${last.op_label}`
          : s.n === 2
          ? '下载清单核对后上传回传'
          : '尚未运行'
        return (
          <div key={s.n} className={`flow-card ${st.cls}`} onClick={() => nav(s.link)}>
            <span className="fc-tag">
              <span className={`badge ${BADGE_CLS[st.badge]}`}>
                <span className="bdot" />
                {st.badge}
              </span>
            </span>
            <div className="fc-num">{num}</div>
            <div className="fc-title">{s.title}</div>
            <div className="fc-sub">{sub}</div>
          </div>
        )
      })}
    </div>
  )
}
