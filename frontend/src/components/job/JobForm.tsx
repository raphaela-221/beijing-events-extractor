import { useEffect, useState } from 'react'
import { Alert, Button, Collapse, Form, Modal, Spin, Typography, App as AntdApp } from 'antd'
import { useQuery } from '@tanstack/react-query'
import { jobsApi, type JobSchema } from '../../api/jobs'
import { filesApi } from '../../api/files'
import { useLockStore } from '../../stores/useLockStore'
import { ParamField } from './ParamField'

export function JobForm({
  jobId,
  preset,
  onSubmitted,
  submitLabel = '开始抽取',
  initialParams,
}: {
  jobId: string
  preset?: string
  onSubmitted: (runId: string) => void
  submitLabel?: string
  initialParams?: Record<string, unknown>
}) {
  const { message } = AntdApp.useApp()
  const lock = useLockStore()
  const { data: job, isLoading } = useQuery({
    queryKey: ['job', jobId],
    queryFn: () => jobsApi.get(jobId),
  })
  const [params, setParams] = useState<Record<string, unknown>>({})
  const [confirming, setConfirming] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)

  useEffect(() => {
    if (job) {
      const init: Record<string, unknown> = {}
      // files 类型不预填：旧 upload_id 无法还原成 File，需重新上传
      job.params.forEach((p) => {
        if (p.type === 'files') return
        init[p.name] = p.default
      })
      if (initialParams) {
        job.params.forEach((p) => {
          if (p.type === 'files') return
          const v = initialParams[p.name]
          if (v !== null && v !== undefined && v !== '') init[p.name] = v
        })
      }
      setParams(init)
    }
    // initialParams 仅在 schema 首次加载时用于预填，不进依赖
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job])

  if (isLoading || !job) {
    return <Spin />
  }

  const lockByOther = !!job.needs_lock && lock.held && !lock.is_me
  const set = (name: string, v: unknown) => setParams((p) => ({ ...p, [name]: v }))

  const doRun = async () => {
    setConfirming(false)
    setSubmitting(true)
    setSubmitError(null)
    try {
      // files 类型参数：提交前先上传拿 upload_id（File 对象不能进 JSON）
      const submitParams: Record<string, unknown> = { ...params }
      for (const p of job.params) {
        if (
          p.type === 'files' &&
          Array.isArray(submitParams[p.name]) &&
          (submitParams[p.name] as File[]).length
        ) {
          const files = submitParams[p.name] as File[]
          const { upload_id } = await filesApi.upload(files)
          submitParams[p.name] = upload_id
        }
      }
      const { run_id } = await jobsApi.run(jobId, submitParams, preset)
      lock.refresh()
      onSubmitted(run_id)
    } catch (e) {
      const msg = (e as Error).message
      setSubmitError(msg)
      message.error(msg)
    } finally {
      setSubmitting(false)
    }
  }

  const onSubmit = () => {
    if (job.danger !== 'none') {
      setConfirming(true)
      return
    }
    doRun()
  }

  const advanced = job.params.filter((p) => p.advanced)
  const basic = job.params.filter((p) => !p.advanced)

  return (
    <div>
      {basic.length > 0 && (
        <Form layout="vertical" style={{ marginBottom: 12 }}>
          {basic.map((p) => (
            <Form.Item key={p.name} label={p.label} help={p.help || undefined}>
              <ParamField param={p} value={params[p.name]} onChange={(v) => set(p.name, v)} />
            </Form.Item>
          ))}
        </Form>
      )}
      {advanced.length > 0 && (
        <Collapse
          items={[
            {
              key: 'adv',
              label: '高级选项',
              children: (
                <Form layout="vertical">
                  {advanced.map((p) => (
                    <Form.Item key={p.name} label={p.label} help={p.help || undefined}>
                      <ParamField param={p} value={params[p.name]} onChange={(v) => set(p.name, v)} />
                    </Form.Item>
                  ))}
                </Form>
              ),
            },
          ]}
          style={{ marginBottom: 16 }}
        />
      )}
      <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
        <Button
          type="primary"
          size="large"
          onClick={onSubmit}
          loading={submitting}
          disabled={lockByOther}
          title={
            lockByOther
              ? `编辑锁被 ${lock.holder} 占用（${lock.since} 起），请等其释放`
              : undefined
          }
        >
          {submitLabel}
        </Button>
        {lockByOther ? (
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            编辑锁被 {lock.holder} 占用（{lock.since} 起）
          </Typography.Text>
        ) : null}
      </div>
      {submitError && (
        <Alert
          type="error"
          showIcon
          style={{ marginTop: 12 }}
          message="未能发起运行"
          description={submitError}
          closable
          onClose={() => setSubmitError(null)}
        />
      )}
      <DangerConfirm job={job} open={confirming} onOk={doRun} onCancel={() => setConfirming(false)} />
    </div>
  )
}

function DangerConfirm({
  job,
  open,
  onOk,
  onCancel,
}: {
  job: JobSchema
  open: boolean
  onOk: () => void
  onCancel: () => void
}) {
  const text =
    job.danger === 'write_canonical'
      ? '将修改人工审核清单（Events List.xlsx），已自动备份。确认继续？'
      : job.danger === 'destructive'
      ? '此操作不可恢复，已自动备份。确认继续？'
      : '确认继续？'
  return (
    <Modal
      open={open}
      title="操作确认"
      okText="确认运行"
      cancelText="取消"
      onOk={onOk}
      onCancel={onCancel}
      okButtonProps={{ danger: job.danger === 'destructive' }}
    >
      <Typography.Paragraph>{text}</Typography.Paragraph>
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        {job.desc}
      </Typography.Text>
    </Modal>
  )
}
