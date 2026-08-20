// error_kind -> 友好文案映射（JobRunner 结束态 + Runs 列表共用）。
// error_kind 由后端 runner.py 赋值：no_new_data / cancelled / interrupted / unknown。
export type ErrorSeverity = 'info' | 'warning' | 'error'

export interface ErrorKindMeta {
  title: string
  desc: string
  severity: ErrorSeverity
}

export const ERROR_KIND_META: Record<string, ErrorKindMeta> = {
  no_new_data: {
    title: '本次无新数据采集',
    desc: '站点可达，列表已抓取，但无新演唱会。属正常空结果。',
    severity: 'info',
  },
  cancelled: {
    title: '已取消',
    desc: '任务被手动取消。',
    severity: 'warning',
  },
  interrupted: {
    title: '服务重启中断',
    desc: '任务运行中遇到后端重启被中断，数据可能不完整。用同参数重跑即可。',
    severity: 'warning',
  },
  unknown: {
    title: '运行失败',
    desc: '查看完整日志定位原因。',
    severity: 'error',
  },
}

export function errorKindMeta(kind: string | null | undefined): ErrorKindMeta {
  return (kind && ERROR_KIND_META[kind]) || ERROR_KIND_META.unknown
}
