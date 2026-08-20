import { useState } from 'react'
import { Alert, Button, Card, Spin, Tag, Typography, App as AntdApp } from 'antd'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { canonicalApi } from '../../api/canonical'
import { jobsApi } from '../../api/jobs'
import { runsApi, type LogLine, type Run } from '../../api/runs'

// 解析 dry 日志的 "✓ row N: dates   (desc...)" 行
function parseDryPlan(lines: LogLine[]): { row: number; dates: string; desc: string }[] {
  const out: { row: number; dates: string; desc: string }[] = []
  for (const l of lines) {
    const m = l.text.match(/✓ row (\d+):\s+(.+?)\s{2,}\((.*)\)/)
    if (m) out.push({ row: Number(m[1]), dates: m[2], desc: m[3] })
  }
  return out
}

/**
 * Dates 列相关操作的运行后面板（放在 JobRunner 顶部，显眼）：
 * - dates_enrich_dry 成功：清单 + 「确认写入」按钮
 * - dates_enrich_write 成功：结构徽章
 * - dates_add_row 成功：写入摘要 + 该行标题/描述原文对照，供核对 Dates 正确性
 * 其他 op_id 返回 null。
 */
export function DatesEnrichResult({ run }: { run: Run }) {
  const nav = useNavigate()
  const { message } = AntdApp.useApp()
  const [submitting, setSubmitting] = useState(false)

  const isDry = run.op_id === 'dates_enrich_dry' && run.status === 'success'
  const isWrite = run.op_id === 'dates_enrich_write' && run.status === 'success'
  const isAddRow = run.op_id === 'dates_add_row' && run.status === 'success'

  const { data: logPage, isLoading: logLoading } = useQuery({
    queryKey: ['run-log', run.run_id],
    queryFn: () => runsApi.log(run.run_id, 0, 5000),
    enabled: isDry,
  })
  const plan = isDry ? parseDryPlan(logPage?.lines || []) : []

  const { data: verifyResult } = useQuery({
    queryKey: ['canonical-verify', run.run_id],
    queryFn: () => canonicalApi.verify(),
    enabled: isWrite,
  })

  // add_row：从 params_json 取 row/value
  let addRowInfo: { row: number; value: string } | null = null
  if (isAddRow) {
    try {
      const p = JSON.parse(run.params_json || '{}')
      if (p.row != null && p.value != null)
        addRowInfo = { row: Number(p.row), value: String(p.value) }
    } catch {
      /* ignore */
    }
  }

  const onConfirmWrite = async () => {
    setSubmitting(true)
    try {
      const { run_id } = await jobsApi.run('dates_enrich_write', {})
      nav(`/runs/${run_id}`)
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setSubmitting(false)
    }
  }

  if (!isDry && !isWrite && !isAddRow) return null

  const title = isAddRow ? 'Dates 手动补单行 · 核对' : 'Dates 列抽取'

  return (
    <Card title={title}>
      {isAddRow && addRowInfo && <AddRowVerify row={addRowInfo.row} value={addRowInfo.value} />}
      {isDry && (
        <div>
          <Typography.Paragraph type="secondary" style={{ fontSize: 12.5, marginBottom: 10 }}>
            试运行清单：以下 {plan.length} 行将写入 Dates 列。核对无误后点「确认写入」。
          </Typography.Paragraph>
          {logLoading ? (
            <Spin />
          ) : plan.length === 0 ? (
            <Alert
              type="info"
              showIcon
              message="无新增需抽取的行"
              description="可能都已有 Dates，或本次没有含日期线索的演唱会事件。"
            />
          ) : (
            <div className="dry-plan-table">
              <div className="dpt-row dpt-head">
                <span>行号</span>
                <span>将写入 Dates</span>
                <span>描述</span>
              </div>
              <div className="dpt-body">
                {plan.map((p) => (
                  <div key={p.row} className="dpt-row">
                    <span className="mono">{p.row}</span>
                    <span className="mono">{p.dates}</span>
                    <span className="dpt-desc" title={p.desc}>
                      {p.desc}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
          <div style={{ marginTop: 14, display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
            <Button
              type="primary"
              loading={submitting}
              onClick={onConfirmWrite}
              disabled={plan.length === 0}
            >
              确认写入 Dates 列
            </Button>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              写入将重新调用 LLM 抽取（temperature=0，结果应与试运行一致）；写前已自动备份
            </Typography.Text>
          </div>
        </div>
      )}
      {isWrite && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <Typography.Text>Dates 列已写入，结构确认：</Typography.Text>
          {verifyResult ? (
            verifyResult.code === 0 ? (
              <Tag color="green">✓ {verifyResult.detail}</Tag>
            ) : (
              <Tag color="red">✗ {verifyResult.detail}</Tag>
            )
          ) : (
            <Spin size="small" />
          )}
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            可前往人工核对页查看 Dates 列实际值
          </Typography.Text>
        </div>
      )}
    </Card>
  )
}

// add_row 写入后的核对面板：显示 Dates 值 + 该行标题 + 描述原文，供对照正确性
function AddRowVerify({ row, value }: { row: number; value: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ['canonical-row', row],
    queryFn: () => canonicalApi.getRow(row),
  })
  return (
    <div>
      <Typography.Text style={{ fontSize: 14 }}>
        已写入第 {row} 行 Dates ={' '}
        <span className="mono" style={{ color: '#4F46E5', fontWeight: 600 }}>
          {value}
        </span>
      </Typography.Text>
      {isLoading ? (
        <Spin size="small" style={{ marginLeft: 12 }} />
      ) : data?.exists ? (
        <div
          style={{
            marginTop: 10,
            padding: 12,
            background: '#FAFAFC',
            borderRadius: 6,
            border: '1px solid #F0F0F0',
          }}
        >
          <div style={{ fontSize: 12, color: '#9CA3AF', marginBottom: 4 }}>标题</div>
          <div style={{ fontSize: 13, marginBottom: 10 }}>{data.headline || '(无标题)'}</div>
          <div style={{ fontSize: 12, color: '#9CA3AF', marginBottom: 4 }}>
            事件描述原文（对照其中的日期与上方 Dates 值）
          </div>
          <div
            style={{
              fontSize: 13,
              color: '#374151',
              whiteSpace: 'pre-wrap',
              lineHeight: 1.6,
              maxHeight: 200,
              overflow: 'auto',
            }}
          >
            {data.desc || '(无描述)'}
          </div>
        </div>
      ) : null}
      <Typography.Paragraph type="secondary" style={{ fontSize: 12, marginTop: 10, marginBottom: 0 }}>
        <b>核对要点</b>：描述里提到的演出日期，是否与 Dates 值（{value}）一致？一致则正确。
        重跑「生成日历」后，日历按此 Dates 在对应场次日期显示该事件。
      </Typography.Paragraph>
    </div>
  )
}
