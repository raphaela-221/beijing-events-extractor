import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { App as AntdApp, Button, Checkbox, Empty, Pagination, Popconfirm, Select, Spin } from 'antd'
import {
  runsApi,
  type CompareResult,
  type PurgeFilters,
  type Run,
  type RunStatus,
  type TrashRun,
} from '../api/runs'
import { jobsApi } from '../api/jobs'
import { useAuthStore } from '../stores/useAuthStore'
import { fmtDateTime, fmtDuration } from '../utils/format'
import { errorKindMeta } from '../utils/errorKind'
import { PurgePreviewModal } from '../components/run/PurgePreviewModal'

type Tab = 'all' | 'trash'

const STATUS_OPTS = [
  { value: 'success', label: '成功' },
  { value: 'failed', label: '失败' },
  { value: 'cancelled', label: '已取消' },
  { value: 'running', label: '运行中' },
  { value: 'queued', label: '排队中' },
]
const RANGE_PRESETS = [
  { value: '', label: '全部时间' },
  { value: '7', label: '最近 7 天' },
  { value: '30', label: '最近 30 天' },
  { value: '90', label: '最近 90 天' },
]

function statusBadgeClass(s: RunStatus): string {
  if (s === 'success') return 'badge success'
  if (s === 'failed') return 'badge error'
  if (s === 'running') return 'badge running'
  return 'badge idle'
}
function statusLabel(s: RunStatus): string {
  return ({ success: '成功', failed: '失败', cancelled: '已取消', running: '运行中', queued: '排队中' } as const)[s]
}

function fmtParams(json: string | null): string {
  if (!json) return '-'
  try {
    const p = JSON.parse(json)
    if (typeof p !== 'object' || !p) return '-'
    const entries = Object.entries(p).filter(
      ([k, v]) => k !== 'input_files' && v !== '' && v !== null && v !== undefined,
    )
    return entries.map(([k, v]) => `${k}=${String(v)}`).join(' · ') || '-'
  } catch {
    return '-'
  }
}

function fmtResult(run: Run): string {
  try {
    const s = JSON.parse(run.summary_json || '{}')
    const parts: string[] = []
    if (s?.concert?.final != null) parts.push(`采集到 ${s.concert.final} 条演唱会`)
    if (s?.pipeline?.extract?.['事件数'] != null) parts.push(`抽取 ${s.pipeline.extract['事件数']} 事件`)
    if (s?.pipeline?.themes?.['生成'] != null) parts.push(`生成 ${s.pipeline.themes['生成']} 个月度主题`)
    if (s?.pipeline?.package?.['文件数'] != null) parts.push(`打包 ${s.pipeline.package['文件数']} 个文件`)
    if (parts.length) return parts.join(' · ')
  } catch {
    /* ignore */
  }
  return run.error_summary || (run.status === 'success' ? '完成' : '-')
}

function signed(n: number, unit: string): string {
  if (n === 0) return `0${unit}`
  return `${n > 0 ? '+' : ''}${n}${unit}`
}
function fmtCompare(c: CompareResult | undefined): string {
  if (!c || !c.has_previous) return '无上次同类运行'
  const parts = [signed(Math.round((c.duration_ms_delta || 0) / 1000), '秒')]
  if (c.events_delta) parts.push(`事件数 ${signed(c.events_delta, '')}`)
  if (c.tokens_delta) parts.push(`token ${signed(c.tokens_delta, '')}`)
  return parts.join(' · ')
}

function RunRow({
  run,
  onRerun,
  onDelete,
  onPin,
}: {
  run: Run
  onRerun: (r: Run) => void
  onDelete: (r: Run) => void
  onPin: (r: Run) => void
}) {
  const [opened, setOpened] = useState(false)
  const { data: logData } = useQuery({
    queryKey: ['run-log-tail', run.run_id],
    queryFn: () => runsApi.log(run.run_id, 0, 6),
    enabled: opened,
  })
  const { data: compare } = useQuery({
    queryKey: ['run-compare', run.run_id],
    queryFn: () => runsApi.compare(run.run_id),
    enabled: opened,
  })

  return (
    <details className="run-row" open={opened} onToggle={(e) => setOpened(e.currentTarget.open)}>
      <summary>
        <span className="chev">▸</span>
        <span className={`pin-icon${run.pinned ? ' pinned' : ''}`}>📌</span>
        <span className={statusBadgeClass(run.status)}>
          <span className="bdot" />
          {statusLabel(run.status)}
        </span>
        <span className="rr-title">
          {fmtDateTime(run.started_at)} · {run.op_label}
        </span>
        <span className="rr-meta">
          {fmtDuration(run.duration_ms)} · {run.operator}
        </span>
        <span className="rr-actions">
          <button className="btn ghost sm" onClick={(e) => { e.preventDefault(); onRerun(run) }}>
            用同参数再跑
          </button>
          <button className="btn ghost sm" onClick={(e) => { e.preventDefault(); onDelete(run) }}>
            删除
          </button>
        </span>
      </summary>
      <div className="rr-body">
        {run.status === 'failed' && run.error_summary && (
          <div className="banner error" style={{ marginBottom: 10 }}>
            <span className="ic">⚠</span>
            <div>
              <b>{errorKindMeta(run.error_kind).title}</b>：{run.error_summary}
            </div>
          </div>
        )}
        <div className="kv-list">
          <div className="row">
            <span className="l">运行编号</span>
            <span className="r">{run.run_id}</span>
          </div>
          <div className="row">
            <span className="l">参数</span>
            <span className="r">{fmtParams(run.params_json)}</span>
          </div>
          <div className="row">
            <span className="l">结果</span>
            <span className="r">{fmtResult(run)}</span>
          </div>
          <div className="row">
            <span className="l">与上次同类运行对比</span>
            <span className="r">{fmtCompare(compare)}</span>
          </div>
        </div>
        {logData && logData.lines.length > 0 && (
          <div className="mini-log">
            {logData.lines.map((l) => (
              <div
                key={l.seq}
                className={
                  l.level === 'success' ? 'l-success' : l.level === 'warn' ? 'l-warn' : l.level === 'error' ? 'l-error' : ''
                }
              >
                {l.ts}  {l.text}
              </div>
            ))}
          </div>
        )}
        <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
          <a className="btn ghost sm" href={runsApi.logDownloadUrl(run.run_id)} download>
            下载完整日志
          </a>
          <button className="btn ghost sm" onClick={() => onPin(run)}>
            {run.pinned ? '取消置顶' : '置顶'}
          </button>
        </div>
      </div>
    </details>
  )
}

function TrashRow({
  run,
  onRestore,
  onPurge,
  canPurge,
}: {
  run: TrashRun
  onRestore: (r: TrashRun) => void
  onPurge: (r: TrashRun) => void
  canPurge: boolean
}) {
  const [opened, setOpened] = useState(false)
  return (
    <details className="run-row" open={opened} onToggle={(e) => setOpened(e.currentTarget.open)}>
      <summary>
        <span className="chev">▸</span>
        <span className="badge idle">
          <span className="bdot" />
          已删除
        </span>
        <span className="rr-title">
          {fmtDateTime(run.started_at)} · {run.op_label}（{statusLabel(run.status)}）
        </span>
        <span className="rr-meta">
          剩 {run.days_left} 天 · {fmtDateTime(run.deleted_at)}删除
        </span>
        <span className="rr-actions">
          <button className="btn ghost sm" onClick={(e) => { e.preventDefault(); onRestore(run) }}>
            恢复
          </button>
          {canPurge && (
            <Popconfirm
              title="彻底删除"
              description="此操作不可恢复，日志与目录将被删除（.bak 保留）。"
              okText="彻底删除"
              okButtonProps={{ danger: true }}
              cancelText="取消"
              onConfirm={() => onPurge(run)}
            >
              <button className="btn ghost sm" onClick={(e) => e.preventDefault()}>
                彻底删除
              </button>
            </Popconfirm>
          )}
        </span>
      </summary>
      <div className="rr-body">
        <div className="kv-list">
          <div className="row">
            <span className="l">运行编号</span>
            <span className="r">{run.run_id}</span>
          </div>
          <div className="row">
            <span className="l">参数</span>
            <span className="r">{fmtParams(run.params_json)}</span>
          </div>
        </div>
      </div>
    </details>
  )
}

export function Runs() {
  const nav = useNavigate()
  const qc = useQueryClient()
  const { message, notification } = AntdApp.useApp()
  const user = useAuthStore((s) => s.user)
  const isAdmin = user?.role === 'admin'

  const [tab, setTab] = useState<Tab>('all')
  const [fOp, setFOp] = useState<string[]>([])
  const [fStatus, setFStatus] = useState<string[]>([])
  const [fOperator, setFOperator] = useState('')
  const [fRange, setFRange] = useState('')
  const [fPinned, setFPinned] = useState(false)
  const [pageNum, setPageNum] = useState(1)
  const [purgeOpen, setPurgeOpen] = useState(false)
  const [purgeFilters, setPurgeFilters] = useState<PurgeFilters>({})
  const freeSpace90 = new Date(Date.now() - 90 * 86400000).toISOString().slice(0, 10)
  const openPurge = (f: PurgeFilters) => {
    setPurgeFilters(f)
    setPurgeOpen(true)
  }

  const { data: jobs } = useQuery({ queryKey: ['jobs'], queryFn: jobsApi.list })
  const opOpts = (jobs || []).map((j) => ({ value: j.id, label: j.label }))

  const startedFrom = fRange
    ? new Date(Date.now() - Number(fRange) * 86400000).toISOString().slice(0, 10)
    : undefined

  // 筛选条件变化时回到第 1 页（数组依赖用 JSON 稳定引用）
  const filterKey = JSON.stringify([fOp, fStatus, fOperator, fRange, fPinned])
  useEffect(() => { setPageNum(1) }, [filterKey])

  const listParams = {
    op_id: fOp.length ? fOp : undefined,
    status: fStatus.length ? fStatus : undefined,
    operator: fOperator || undefined,
    started_from: startedFrom,
    pinned: fPinned ? true : undefined,
    sort: 'started_at:desc',
    page: pageNum,
    page_size: 50,
  }
  const purgeFiltersCurrent: PurgeFilters = {
    op_id: fOp.length ? fOp : undefined,
    status: fStatus.length ? fStatus : undefined,
    operator: fOperator || undefined,
    started_from: startedFrom,
    keep_pinned: true,
  }

  const { data: page, isLoading } = useQuery({
    queryKey: ['runs-list', listParams],
    queryFn: () => runsApi.listRuns(listParams),
    enabled: tab === 'all',
  })
  const { data: trashData, isLoading: trashLoading } = useQuery({
    queryKey: ['runs-trash'],
    queryFn: () => runsApi.trash(),
    enabled: tab === 'trash',
  })

  const rerun = (r: Run) => nav(`/runs/${r.run_id}?rerun=1`)
  const pin = async (r: Run) => {
    await runsApi.pin(r.run_id, !r.pinned)
    qc.invalidateQueries({ queryKey: ['runs-list'] })
  }
  const softDelete = async (r: Run) => {
    await runsApi.remove(r.run_id, 'trash')
    qc.invalidateQueries({ queryKey: ['runs-list'] })
    qc.invalidateQueries({ queryKey: ['runs-trash'] })
    notification.open({
      message: '已移入回收站',
      description: '30 天内可恢复',
      btn: (
        <Button
          size="small"
          onClick={async () => {
            await runsApi.restore(r.run_id)
            qc.invalidateQueries({ queryKey: ['runs-list'] })
            qc.invalidateQueries({ queryKey: ['runs-trash'] })
            notification.destroy()
          }}
        >
          撤销
        </Button>
      ),
      duration: 10,
    })
  }
  const restore = async (r: TrashRun) => {
    await runsApi.restore(r.run_id)
    qc.invalidateQueries({ queryKey: ['runs-trash'] })
    qc.invalidateQueries({ queryKey: ['runs-list'] })
    message.success('已恢复')
  }
  const purgeOne = async (r: TrashRun) => {
    await runsApi.remove(r.run_id, 'purge')
    qc.invalidateQueries({ queryKey: ['runs-trash'] })
    message.success('已彻底删除')
  }
  const exportXlsx = () => window.open(runsApi.exportUrl(listParams), '_blank')

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="page-title">运行记录</div>
          <div className="page-sub">每次调用都留痕，可查、可复用参数、可对比、可删除</div>
        </div>
        <button className="btn ghost sm" onClick={() => nav('/')}>
          ← 返回总览
        </button>
      </div>

      <div className="pill-tabs" style={{ marginBottom: 14 }}>
        <div className={`pill${tab === 'all' ? ' active' : ''}`} onClick={() => setTab('all')}>
          全部运行（{page?.total ?? 0}）
        </div>
        <div className={`pill${tab === 'trash' ? ' active' : ''}`} onClick={() => setTab('trash')}>
          回收站（{trashData?.items.length ?? 0}）
        </div>
      </div>

      {tab === 'all' ? (
        <div className="card">
          <div className="runs-toolbar">
            <Select
              mode="multiple"
              allowClear
              placeholder="全部操作类型"
              style={{ minWidth: 180 }}
              value={fOp}
              onChange={setFOp}
              options={opOpts}
              maxTagCount="responsive"
            />
            <Select
              mode="multiple"
              allowClear
              placeholder="全部状态"
              style={{ minWidth: 140 }}
              value={fStatus}
              onChange={setFStatus}
              options={STATUS_OPTS}
              maxTagCount="responsive"
            />
            <input
              className="rr-input"
              placeholder="操作人"
              value={fOperator}
              onChange={(e) => setFOperator(e.target.value)}
              style={{ width: 120 }}
            />
            <Select
              placeholder="时间范围"
              style={{ width: 140 }}
              value={fRange}
              onChange={setFRange}
              options={RANGE_PRESETS}
              allowClear
            />
            <label className="rr-check">
              <Checkbox checked={fPinned} onChange={(e) => setFPinned(e.target.checked)} /> 只看置顶
            </label>
            <button
              className="btn ghost sm"
              style={{ marginLeft: 'auto' }}
              onClick={() => openPurge(purgeFiltersCurrent)}
            >
              按条件批量删除…
            </button>
            <button
              className="btn ghost sm"
              onClick={() => openPurge({ started_from: freeSpace90, keep_pinned: true })}
            >
              一键腾空间
            </button>
            <button className="btn ghost sm" onClick={exportXlsx}>
              导出 xlsx
            </button>
          </div>

          {isLoading ? (
            <Spin />
          ) : !page?.items.length ? (
            <Empty description="还没有运行记录。从总览页或 Step 1 / Step 2 发起第一次运行。" />
          ) : (
            page.items.map((r) => (
              <RunRow key={r.run_id} run={r} onRerun={rerun} onDelete={softDelete} onPin={pin} />
            ))
          )}
          {page && page.items.length > 0 && (
            <Pagination
              current={pageNum}
              total={page.total}
              pageSize={50}
              onChange={setPageNum}
              showTotal={(t) => `共 ${t} 条`}
              style={{ marginTop: 16, textAlign: 'right' }}
            />
          )}
        </div>
      ) : (
        <div className="card">
          <div className="banner warn">
            <span className="ic">🗑</span>
            <div>回收站中的记录 30 天后自动彻底删除。彻底删除前可随时恢复。</div>
          </div>
          {trashLoading ? (
            <Spin />
          ) : !trashData?.items.length ? (
            <Empty description="回收站是空的。删除的运行记录会在这里保留 30 天。" />
          ) : (
            trashData.items.map((r) => (
              <TrashRow
                key={r.run_id}
                run={r}
                onRestore={restore}
                onPurge={purgeOne}
                canPurge={isAdmin}
              />
            ))
          )}
        </div>
      )}

      <PurgePreviewModal
        open={purgeOpen}
        onClose={() => setPurgeOpen(false)}
        filters={purgeFilters}
        // key 随 filters 变，切换「一键腾空间」时重新预览
        key={JSON.stringify(purgeFilters)}
      />
    </div>
  )
}
