import { useEffect, useRef } from 'react'
import * as echarts from 'echarts'

export default function RevenueChart() {
  const chartRef = useRef(null)

  useEffect(() => {
    const el = chartRef.current
    if (!el) return

    try {
      const instance = echarts.init(el)

      instance.setOption({
        backgroundColor: 'transparent',
        tooltip: { trigger: 'axis' },
        legend: { top: 0, textStyle: { color: '#6b7280' } },
        grid: { top: 40, left: 10, right: 10, bottom: 10, containLabel: true },
        xAxis: {
          type: 'category',
          data: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
          axisLine: { lineStyle: { color: '#ddd6fe' } },
          axisLabel: { color: '#6b7280' }
        },
        yAxis: {
          type: 'value',
          splitLine: { lineStyle: { color: 'rgba(139,92,246,0.10)' } },
          axisLabel: { color: '#6b7280' }
        },
        dataZoom: [{ type: 'inside' }],
        series: [
          {
            name: 'Requests',
            type: 'line',
            smooth: true,
            data: [120, 182, 151, 234, 290, 330, 310],
            lineStyle: { width: 3, color: '#7c3aed' },
            itemStyle: { color: '#7c3aed' },
            areaStyle: { color: 'rgba(124,58,237,0.12)' }
          },
          {
            name: 'Tokens',
            type: 'bar',
            data: [80, 132, 101, 154, 190, 230, 210],
            itemStyle: {
              color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                { offset: 0, color: '#a855f7' },
                { offset: 1, color: '#7c3aed' }
              ]),
              borderRadius: [8, 8, 0, 0]
            }
          }
        ]
      })

      const resizeObserver = new ResizeObserver(() => instance.resize())
      resizeObserver.observe(el)
      window.addEventListener('resize', instance.resize)

      return () => {
        resizeObserver.disconnect()
        window.removeEventListener('resize', instance.resize)
        instance.dispose()
      }
    } catch (err) {
      console.error('[RevenueChart] Failed to initialize chart:', err)
    }
  }, [])

  return <div ref={chartRef} className="h-[240px] w-full" />
}