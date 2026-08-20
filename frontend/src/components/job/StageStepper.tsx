import { Fragment } from 'react'

// 照 mockups/shared.css 的 .step 配色。currentIndex 为当前阶段，超过的为 done。
export function StageStepper({
  stages,
  currentIndex,
  failedIndex,
}: {
  stages: string[]
  currentIndex: number | null
  failedIndex?: number | null
}) {
  const cur = currentIndex ?? -1
  return (
    <div style={{ display: 'flex', alignItems: 'center' }}>
      {stages.map((s, i) => {
        const done = i < cur
        const current = i === cur
        const failed = i === failedIndex
        const dotBg = failed
          ? '#DC2626'
          : done
          ? '#16A34A'
          : current
          ? '#EFF6FF'
          : '#fff'
        const dotColor = failed
          ? '#fff'
          : done
          ? '#fff'
          : current
          ? '#2563EB'
          : '#9CA3AF'
        const dotBorder = failed
          ? '#DC2626'
          : done
          ? '#16A34A'
          : current
          ? '#2563EB'
          : '#E5E7EB'
        const labelColor = failed
          ? '#DC2626'
          : done || current
          ? '#1F2937'
          : '#9CA3AF'
        return (
          <Fragment key={s}>
            <div style={{ display: 'flex', alignItems: 'center', flex: 1, minWidth: 0 }}>
              <div
                style={{
                  width: 26,
                  height: 26,
                  borderRadius: '50%',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: 12,
                  fontWeight: 600,
                  flexShrink: 0,
                  border: `2px solid ${dotBorder}`,
                  background: dotBg,
                  color: dotColor,
                }}
              >
                {done ? '✓' : i + 1}
              </div>
              <div
                style={{
                  marginLeft: 8,
                  fontSize: 12.5,
                  color: current ? '#2563EB' : labelColor,
                  fontWeight: current || failed ? 600 : 400,
                  whiteSpace: 'nowrap',
                }}
              >
                {s}
              </div>
            </div>
            {i < stages.length - 1 && (
              <div
                style={{
                  flex: 1,
                  height: 2,
                  background: i < cur ? '#16A34A' : '#E5E7EB',
                  margin: '0 10px',
                  minWidth: 16,
                }}
              />
            )}
          </Fragment>
        )
      })}
    </div>
  )
}
