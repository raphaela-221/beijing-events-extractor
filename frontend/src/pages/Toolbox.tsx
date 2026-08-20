import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { jobsApi } from '../api/jobs'
import { useAuthStore } from '../stores/useAuthStore'
import { JobCard } from '../components/job/JobCard'

const GROUP_ORDER = ['抽取', 'canonical 维护', '生成日历']

export function Toolbox() {
  const nav = useNavigate()
  const isAdmin = useAuthStore((s) => s.user)?.role === 'admin'
  const { data: jobs } = useQuery({ queryKey: ['jobs'], queryFn: jobsApi.list })
  const { data: lastRuns } = useQuery({ queryKey: ['jobs-last-runs'], queryFn: jobsApi.lastRuns })

  const visible = (jobs || []).filter((j) => !j.admin_only || isAdmin)
  const groups: string[] = []
  GROUP_ORDER.forEach((g) => {
    if (visible.some((j) => j.group === g)) groups.push(g)
  })
  visible.forEach((j) => {
    if (!groups.includes(j.group)) groups.push(j.group)
  })

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="page-title">工具箱</div>
          <div className="page-sub">
            流程卡住时的自救入口——覆盖全部可运行操作，参数全暴露。取代原来的终端兜底
          </div>
        </div>
        <button className="btn ghost sm" onClick={() => nav('/')}>
          ← 返回总览
        </button>
      </div>

      {!isAdmin && (
        <div className="banner info" style={{ marginBottom: 14 }}>
          <span className="ic">🔒</span>
          <div>破坏性操作（去重写入、用源 Excel 铺底）仅管理员可见。当前为操作员账号。</div>
        </div>
      )}

      {groups.map((g) => (
        <div key={g}>
          <div className="toolbox-group-title">{g}</div>
          <div className="job-grid">
            {visible
              .filter((j) => j.group === g)
              .map((j) => (
                <JobCard key={j.id} job={j} lastRun={lastRuns?.[j.id]} />
              ))}
          </div>
        </div>
      ))}
    </div>
  )
}
