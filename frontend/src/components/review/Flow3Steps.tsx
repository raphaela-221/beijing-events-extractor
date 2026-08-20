import { Fragment } from 'react'

export type StepState = 'idle' | 'active' | 'done'

// 三步流程：下载 -> 本地修改 -> 上传回传。descs 可动态（如「已下载，共 N 条」）。
export function Flow3Steps({
  states,
  descs,
}: {
  states: StepState[]
  descs?: string[]
}) {
  const steps = [
    { n: 1, title: '① 下载清单' },
    { n: 2, title: '② 本地修改' },
    { n: 3, title: '③ 上传回传' },
  ]
  const defaultDescs: [string, string, string] = [
    '下载当前 Events List.xlsx',
    '在桌面 Excel 中编辑，改完保存',
    '拖拽修改后的文件到下方区域',
  ]
  const ds = descs || defaultDescs
  return (
    <div className="flow3">
      {steps.map((s, i) => (
        <Fragment key={s.n}>
          <div className={`flow3-step ${states[i]}`}>
            <div className="num">{states[i] === 'done' ? '✓' : s.n}</div>
            <h4>{s.title}</h4>
            <p>{ds[i]}</p>
          </div>
          {i < 2 && <div className="flow3-arrow">→</div>}
        </Fragment>
      ))}
    </div>
  )
}
