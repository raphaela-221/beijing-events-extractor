import { useEffect, useRef, useState } from 'react'
import VirtualList from 'rc-virtual-list'
import type { LogLine } from '../../api/runs'

const ITEM_H = 22
const HEIGHT = 380

const LEVEL_COLOR: Record<string, string> = {
  info: '#C9CCDA',
  success: '#4ADE80',
  warn: '#FBBF24',
  error: '#F87171',
}

// 深色日志面板（照 shared.css .log-panel）+ rc-virtual-list 虚拟滚动。
// 自动滚到底，手动上滚即停，浮「回到底部（新增 N 行）」。
export function LogPanel({ lines }: { lines: LogLine[] }) {
  const listRef = useRef<{ scrollTo: (o: { index: number }) => void } | null>(null)
  const [paused, setPaused] = useState(false)
  const [newWhilePaused, setNewWhilePaused] = useState(0)
  const prevLen = useRef(0)

  useEffect(() => {
    if (lines.length > prevLen.current) {
      const delta = lines.length - prevLen.current
      if (!paused) {
        // 下一帧滚到底，确保 VirtualList 已渲染新行
        requestAnimationFrame(() =>
          listRef.current?.scrollTo({ index: Math.max(0, lines.length - 1) }),
        )
      } else {
        setNewWhilePaused((n) => n + delta)
      }
    }
    prevLen.current = lines.length
  }, [lines, paused])

  const onScroll = (e: { scrollTop: number }) => {
    const max = Math.max(0, lines.length * ITEM_H - HEIGHT)
    if (e.scrollTop < max - 30) {
      if (!paused) setPaused(true)
    } else if (paused) {
      setPaused(false)
      setNewWhilePaused(0)
    }
  }

  const jumpToBottom = () => {
    setPaused(false)
    setNewWhilePaused(0)
    requestAnimationFrame(() =>
      listRef.current?.scrollTo({ index: Math.max(0, lines.length - 1) }),
    )
  }

  return (
    <div
      style={{
        position: 'relative',
        background: '#0F1117',
        borderRadius: 8,
        overflow: 'hidden',
        border: '1px solid #22252F',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          padding: '8px 12px',
          background: '#1A1D27',
          borderBottom: '1px solid #22252F',
          fontSize: 12.5,
          color: '#8B8FA3',
        }}
      >
        <span>共 {lines.length.toLocaleString()} 行</span>
        <span>·</span>
        <span>{paused ? '已暂停自动滚动' : '自动滚动中'}</span>
      </div>
      <VirtualList
        ref={listRef as never}
        data={lines}
        height={HEIGHT}
        itemHeight={ITEM_H}
        itemKey={(item: LogLine) => item.seq}
        onScroll={onScroll as never}
        style={{ padding: '10px 14px' }}
        className="log-vlist"
      >
        {(item: LogLine) => (
          <div
            style={{
              display: 'flex',
              height: ITEM_H,
              lineHeight: `${ITEM_H}px`,
              whiteSpace: 'nowrap',
              overflow: 'hidden',
              fontFamily:
                '"JetBrains Mono", "SF Mono", Consolas, "Courier New", monospace',
              fontSize: 12.5,
            }}
          >
            <span
              style={{ color: '#4B4F62', width: 34, flexShrink: 0, textAlign: 'right', marginRight: 12, userSelect: 'none' }}
            >
              {item.seq}
            </span>
            <span style={{ color: '#5C6070', marginRight: 10, flexShrink: 0 }}>{item.ts}</span>
            <span
              style={{
                color: LEVEL_COLOR[item.level] || '#C9CCDA',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
              }}
            >
              {item.text}
            </span>
          </div>
        )}
      </VirtualList>
      {paused && newWhilePaused > 0 && (
        <button
          onClick={jumpToBottom}
          style={{
            position: 'absolute',
            right: 26,
            bottom: 12,
            background: '#2A2D3A',
            color: '#fff',
            fontSize: 12,
            padding: '5px 12px',
            borderRadius: 999,
            border: 'none',
            cursor: 'pointer',
            boxShadow: '0 2px 8px rgba(0,0,0,.3)',
          }}
        >
          回到底部（新增 {newWhilePaused} 行）
        </button>
      )}
    </div>
  )
}
