import { DatePicker, Input, InputNumber, Select, Switch, Upload } from 'antd'
import type { UploadFile } from 'antd'
import dayjs from 'dayjs'
import { useQuery } from '@tanstack/react-query'
import { canonicalApi } from '../../api/canonical'
import type { Param } from '../../api/jobs'

// Param.type -> AntD 控件，前端唯一需维护的映射（指南 §2.4）
export function ParamField({
  param,
  value,
  onChange,
}: {
  param: Param
  value: unknown
  onChange: (v: unknown) => void
}) {
  switch (param.type) {
    case 'bool':
      return <Switch checked={!!value} onChange={(c) => onChange(c)} />
    case 'enum':
      return (
        <Select
          value={value as string}
          style={{ width: 260 }}
          options={(param.choices || []).map((c) => ({ label: c, value: c }))}
          onChange={onChange}
        />
      )
    case 'date':
      return (
        <DatePicker
          value={value ? dayjs(value as string) : null}
          style={{ width: 260 }}
          onChange={(_, str) => onChange(str as string)}
        />
      )
    case 'int':
      return (
        <InputNumber
          value={value as number}
          style={{ width: 200 }}
          onChange={(n) => onChange(n)}
        />
      )
    case 'text':
      return (
        <Input.TextArea
          value={value as string}
          rows={3}
          style={{ width: '100%' }}
          onChange={(e) => onChange(e.target.value)}
        />
      )
    case 'month':
      return (
        <DatePicker
          picker="month"
          value={value ? dayjs(value as string) : null}
          style={{ width: 260 }}
          onChange={(_, str) => onChange(str as string)}
        />
      )
    case 'files': {
      // 受控：value 是 File[]，转 UploadFile[] 给 fileList；提交时由 JobForm 上传拿 upload_id
      const fileList: UploadFile[] = ((value as File[] | undefined) || []).map((f) => ({
        uid: `${f.name}-${f.size}`,
        name: f.name,
        status: 'done',
        originFileObj: f as unknown as UploadFile['originFileObj'],
      }))
      return (
        <Upload.Dragger
          multiple
          fileList={fileList}
          beforeUpload={() => false}
          onChange={(info) => {
            const files = info.fileList
              .map((f) => f.originFileObj)
              .filter(Boolean) as File[]
            onChange(files)
          }}
        >
          <p className="ant-upload-text">拖拽文件到此处，或点击选择文件</p>
          <p className="ant-upload-hint">支持 xlsx/xls/csv/txt/json，可同时选择多个</p>
        </Upload.Dragger>
      )
    }
    case 'row_ref':
      return <RowRefField value={value as number | undefined} onChange={onChange} />
    default:
      return (
        <Input
          value={value as string}
          style={{ width: 260 }}
          onChange={(e) => onChange(e.target.value)}
        />
      )
  }
}

// row_ref：行号输入 + 下方实时回显该行内容（No./标题/日期/已有 Dates），防填错行
function RowRefField({
  value,
  onChange,
}: {
  value: number | undefined
  onChange: (v: unknown) => void
}) {
  const n = value as number | undefined
  const enabled = !!n && n >= 2
  const { data, isLoading } = useQuery({
    queryKey: ['canonical-row', n],
    queryFn: () => canonicalApi.getRow(n as number),
    enabled,
  })
  return (
    <div>
      <InputNumber
        value={n}
        min={2}
        style={{ width: 200 }}
        onChange={(v) => onChange(v ?? undefined)}
      />
      {enabled && (
        <div className="row-ref-hint">
          {isLoading ? (
            <span className="muted">读取中…</span>
          ) : data?.exists === false ? (
            <span className="warn">第 {n} 行无数据（超出范围或空行）</span>
          ) : data ? (
            <span>
              第 {n} 行 · No.{data.no} · {data.headline || '(无标题)'}
              {data.start_date
                ? ` · ${data.start_date}${data.end_date ? '~' + data.end_date : ''}`
                : ''}
              {data.dates
                ? ` · 已有 Dates: ${data.dates}`
                : ` · Dates 空（按 ${data.start_date ? data.start_date.slice(0, 4) : 'Start Date'} 年解析）`}
            </span>
          ) : null}
        </div>
      )}
    </div>
  )
}
