import { useEffect, useState } from 'react'
import { Alert, Button, Card, Spin, Tag, Typography, App as AntdApp } from 'antd'
import { useQuery } from '@tanstack/react-query'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { jobsApi } from '../../api/jobs'
import { runsApi, type RunStatus } from '../../api/runs'
import { useJobLog } from '../../hooks/useJobLog'
import { useLockStore } from '../../stores/useLockStore'
import { StageStepper } from './StageStepper'
import { LogPanel } from './LogPanel'
import { SummaryCards } from './SummaryCards'
import { DatesEnrichResult } from '../run/DatesEnrichResult'
import { fmtDuration, fmtDateTime } from '../../utils/format'
import { errorKindMeta } from '../../utils/errorKind'

const STATUS_META: Record<RunStatus, { color: string; label: string }> = {
  queued: { color: '#6B7280', label: '排队' },
  running: { color: '#2563EB', label: '运行中' },
  success: { color: '#16A34A', label: '成功' },
  failed: { color: '#DC2626', label: '失败' },
  cancelled: { color: '#6B7280', label: '已取消' },
}

function fmtElapsed(ms: number): string {
  const s = Math.floor(ms / 1000)
  const mm = Math.floor(s / 60).toString().padStart(2, '0')
  const ss = (s % 60).toString().padStart(2, '0')
  return `${mm}:${ss}`
}

export function JobRunner({ runId }: { runId: string }) {
  const nav = useNavigate()
  const [sp] = useSearchParams()
  const from = sp.get('from') || 'step1'
  const { message } = AntdApp.useApp()
  const lock = useLockStore((s) => s.refresh)
  const { run, lines, status, stage, summary, llm, connected } = useJobLog(runId)
  const { data: job } = useQuery({
    queryKey: ['job', run?.op_id],
    queryFn: () => jobsApi.get(run!.op_id),
    enabled: !!run?.op_id,
  })
  const [now, setNow] = useState(Date.now())
  const [canceling, setCanceling] = useState(false)

  useEffect(() => {
    if (status !== 'running') return
    const t = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(t)
  }, [status])

  // 标签页标题带进度
  useEffect(() => {
    if (!run) return
    const stages = job?.stages || []
    const idx = (stage?.index ?? run.stage_index ?? 0) + 1
    const base = '北京大事件操作台'
    if (status === 'running')
      document.title = `(${idx}/${stages.length || '?'}) ${run.op_label} · ${base}`
    else if (status === 'success') document.title = `✓ 完成 · ${run.op_label} · ${base}`
    else if (status === 'failed') document.title = `✗ 失败 · ${run.op_label} · ${base}`
    else document.title = `${run.op_label} · ${base}`
    return () => {
      document.title = base
    }
  }, [run, job, status, stage])

  if (!run) {
    return <Spin style={{ display: 'block', padding: 60 }} />
  }

  const stages = job?.stages || []
  // dates 类操作结束时用 Dates 核对面板替换通用摘要（SummaryCards 对这些 op 只有"本次无摘要"）
  const isDatesOp =
    !!run &&
    (run.op_id === 'dates_enrich_dry' ||
      run.op_id === 'dates_enrich_write' ||
      run.op_id === 'dates_add_row')
  const showDatesPanel = isDatesOp && ['success', 'failed', 'cancelled'].includes(status)
  const stageIndex = stage?.index ?? run.stage_index ?? null
  const elapsed =
    status === 'running'
      ? now - new Date(run.started_at).getTime()
      : run.duration_ms || 0
  const meta = STATUS_META[status]
  const errMeta = errorKindMeta(run.error_kind)
  const fromPath = from === 'step2' ? '/step2' : from === 'toolbox' ? '/toolbox' : '/step1'
  // Step1 三类 job 的产出是独立日期文件，不是 canonical；运行详情页直接给下载入口
  const isStep1Op =
    !!run &&
    (run.op_id === 'step1_full' ||
      run.op_id === 'step1_input_only' ||
      run.op_id === 'step1_concert_only')

  const onCancel = async () => {
    setCanceling(true)
    try {
      await runsApi.cancel(runId)
      lock()
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setCanceling(false)
    }
  }

  return (
    <div>
      <Typography.Text type="secondary" style={{ fontSize: 12.5 }}>
        <a onClick={() => nav(fromPath)}>返回{from === 'step2' ? 'Step 2' : from === 'toolbox' ? '工具箱' : 'Step 1'}</a>
        <span style={{ margin: '0 6px', color: '#9CA3AF' }}>/</span>
        任务监控
      </Typography.Text>

      <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginTop: 8, marginBottom: 4 }}>
        <Tag color={meta.color} style={{ borderRadius: 999, padding: '2px 12px' }}>
          {meta.label}
        </Tag>
        <span style={{ fontSize: 16, fontWeight: 600 }}>{run.op_label}</span>
        <span className="mono" style={{ fontSize: 14, color: '#6B7280' }}>
          用时 {fmtElapsed(elapsed)}
        </span>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
          <Button onClick={() => nav(fromPath)}>返回（任务继续在后台运行）</Button>
          {status === 'running' && (
            <Button danger loading={canceling} onClick={onCancel}>
              取消任务
            </Button>
          )}
        </div>
      </div>
      <Typography.Text type="secondary" style={{ fontSize: 12.5 }}>
        发起人 {run.operator} · 开始于 {fmtDateTime(run.started_at)}
        {!connected && status === 'running' ? ' · 重新连接中…' : ''}
      </Typography.Text>

      {stages.length > 1 && (
        <Card style={{ marginTop: 16 }}>
          <StageStepper stages={stages} currentIndex={stageIndex} />
        </Card>
      )}

      <Card
        title="实时日志"
        extra={
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            共 {lines.length.toLocaleString()} 行 · {status === 'running' ? '实时' : '已结束'}
          </Typography.Text>
        }
        style={{ marginTop: 16 }}
      >
        <LogPanel lines={lines} />
      </Card>

      <div style={{ marginTop: 16 }}>
        {showDatesPanel && run ? (
          <DatesEnrichResult run={run} />
        ) : (
          <SummaryCards summary={summary} llm={llm} running={status === 'running'} />
        )}
      </div>

      <Card title="本次运行信息" style={{ marginTop: 16 }}>
        <div style={{ fontSize: 12.5, color: '#6B7280' }}>
          <Row l="运行编号" r={run.run_id} />
          <Row l="操作" r={run.op_label} />
          <Row l="发起人" r={run.operator} />
          <Row l="开始时间" r={fmtDateTime(run.started_at)} />
          {run.ended_at ? <Row l="结束时间" r={fmtDateTime(run.ended_at)} /> : null}
          {run.duration_ms ? <Row l="用时" r={fmtDuration(run.duration_ms)} /> : null}
          {run.canonical_backup_path ? (
            <Row
              l="已备份"
              r={
                isStep1Op
                  ? 'Events List.xlsx 已在运行前自动备份（本次产出在独立日期文件，清单本身未被修改）'
                  : 'Events List.xlsx 已在运行前自动备份'
              }
            />
          ) : null}
        </div>
      </Card>

      {(status === 'success' || status === 'failed' || status === 'cancelled') && (
        <Card style={{ marginTop: 16 }}>
          {status === 'success' && (
            <div>
              {run.error_kind === 'no_new_data' ? (
                <Alert
                  type="info"
                  showIcon
                  message="本次无新数据采集"
                  description={run.error_summary || '站点可达，列表已抓取，但无新演唱会。'}
                />
              ) : isStep1Op ? (
                <Alert
                  type="success"
                  showIcon
                  message="抽取完成，产出已写入独立日期文件"
                  description={
                    '新事件不在人工核对清单里，在本次运行的产出 Excel（Travel_Facilitators_and_Hindrances_Events_日期.xlsx）。' +
                    '下载后请到人工核对页合并：下载 Events List.xlsx → 把新增行粘贴到末尾 → 上传回传 → 确认提交。'
                  }
                />
              ) : (
                <Typography.Text>
                  用时 {fmtDuration(run.duration_ms)}。已合并写入 Events List.xlsx，已自动备份。
                </Typography.Text>
              )}
              <div style={{ marginTop: 12, display: 'flex', gap: 8 }}>
                {run.error_kind === 'no_new_data' ? (
                  <Button type="primary" onClick={() => nav(fromPath)}>
                    返回 Step 1
                  </Button>
                ) : (
                  <Button type="primary" onClick={() => nav('/review')}>
                    前往人工核对
                  </Button>
                )}
                {isStep1Op && run.error_kind !== 'no_new_data' && (
                  <a href={runsApi.outputDownloadUrl(runId)} target="_blank" rel="noreferrer">
                    <Button>下载本次产出 Excel</Button>
                  </a>
                )}
                <a href={runsApi.logDownloadUrl(runId)} target="_blank" rel="noreferrer">
                  <Button>下载完整日志</Button>
                </a>
              </div>
            </div>
          )}
          {status === 'failed' && (
            <div>
              <Alert
                type={errMeta.severity}
                showIcon
                message={errMeta.title}
                description={run.error_summary || errMeta.desc}
              />
              <div style={{ marginTop: 12, display: 'flex', gap: 8 }}>
                <Button type="primary" onClick={() => nav(fromPath)}>
                  用同参数重跑
                </Button>
                <a href={runsApi.logDownloadUrl(runId)} target="_blank" rel="noreferrer">
                  <Button>下载完整日志</Button>
                </a>
              </div>
            </div>
          )}
          {status === 'cancelled' && (
            <div>
              <Alert
                type={errMeta.severity}
                showIcon
                message={errMeta.title}
                description={run.error_summary || errMeta.desc}
              />
              <div style={{ marginTop: 12, display: 'flex', gap: 8 }}>
                <Button type="primary" onClick={() => nav(fromPath)}>
                  用同参数重跑
                </Button>
                <a href={runsApi.logDownloadUrl(runId)} target="_blank" rel="noreferrer">
                  <Button>下载完整日志</Button>
                </a>
              </div>
            </div>
          )}
        </Card>
      )}
    </div>
  )
}

function Row({ l, r }: { l: string; r: React.ReactNode }) {
  return (
    <div
      style={{
        display: 'flex',
        justifyContent: 'space-between',
        padding: '5px 0',
        borderBottom: '1px dashed #F0F0F0',
      }}
    >
      <span style={{ color: '#9CA3AF' }}>{l}</span>
      <span style={{ color: '#1F2937', fontWeight: 500 }}>{r}</span>
    </div>
  )
}
