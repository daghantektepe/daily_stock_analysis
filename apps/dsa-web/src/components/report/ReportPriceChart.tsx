import type React from 'react';
import { useEffect, useMemo, useState } from 'react';
import {
  Area,
  AreaChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import apiClient from '../../api';
import { Card } from '../common';

interface KLineItem {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
  change_percent?: number;
}

interface StockHistoryPayload {
  stock_code: string;
  data: KLineItem[];
}

interface ReportPriceChartProps {
  stockCode: string;
  stopLoss?: number | null;
  takeProfit?: number | null;
  idealBuy?: number | null;
}

export const ReportPriceChart: React.FC<ReportPriceChartProps> = ({
  stockCode,
  stopLoss,
  takeProfit,
  idealBuy,
}) => {
  const [bars, setBars] = useState<KLineItem[]>([]);
  const [days, setDays] = useState<number>(90);

  useEffect(() => {
    const code = stockCode.trim();
    if (!code) {
      setBars([]);
      return;
    }

    let cancelled = false;
    apiClient
      .get<StockHistoryPayload>(`/api/v1/stocks/${encodeURIComponent(code)}/history`, {
        params: { period: 'daily', days },
      })
      .then((res) => {
        if (!cancelled && Array.isArray(res.data?.data)) {
          setBars(res.data.data);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setBars([]);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [stockCode, days]);

  const domain = useMemo(() => {
    if (bars.length === 0) return ['auto', 'auto'] as const;
    const prices = bars.map((b) => b.close).filter((v) => Number.isFinite(v));
    if (stopLoss && Number.isFinite(stopLoss)) prices.push(stopLoss);
    if (takeProfit && Number.isFinite(takeProfit)) prices.push(takeProfit);
    if (idealBuy && Number.isFinite(idealBuy)) prices.push(idealBuy);
    const min = Math.min(...prices);
    const max = Math.max(...prices);
    const pad = Math.max((max - min) * 0.08, min * 0.01);
    return [Number((min - pad).toFixed(2)), Number((max + pad).toFixed(2))] as [number, number];
  }, [bars, stopLoss, takeProfit, idealBuy]);

  if (bars.length < 2) {
    return null;
  }

  return (
    <Card variant="bordered" padding="sm" className="home-panel-card">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div>
          <span className="label-uppercase">TEKNİK FİYAT GRAFİĞİ</span>
          <h3 className="text-sm font-semibold text-foreground">
            {stockCode} — Son {days} Gün Kapanış &amp; Kritik Seviyeler
          </h3>
        </div>
        <div className="flex items-center gap-1 rounded-lg border border-border/60 bg-base/40 p-0.5 text-[11px]">
          {[30, 90, 180].map((windowDays) => (
            <button
              key={windowDays}
              type="button"
              onClick={() => setDays(windowDays)}
              className={`rounded-md px-2 py-0.5 font-mono transition ${
                days === windowDays
                  ? 'bg-primary text-white'
                  : 'text-secondary-text hover:text-foreground'
              }`}
            >
              {windowDays}G
            </button>
          ))}
        </div>
      </div>

      <div className="h-52 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={bars} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="reportPriceFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#38bdf8" stopOpacity={0.35} />
                <stop offset="95%" stopColor="#38bdf8" stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.14)" />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 10, fill: '#94a3b8' }}
              tickFormatter={(val: string) => (typeof val === 'string' ? val.slice(5) : '')}
              minTickGap={24}
            />
            <YAxis
              domain={domain}
              tick={{ fontSize: 10, fill: '#94a3b8' }}
              width={52}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: '#0f172a',
                borderColor: 'rgba(148,163,184,0.25)',
                borderRadius: '10px',
                fontSize: '12px',
              }}
              labelStyle={{ color: '#e2e8f0', fontWeight: 600 }}
            />
            {stopLoss && Number.isFinite(stopLoss) ? (
              <ReferenceLine
                y={stopLoss}
                stroke="#f43f5e"
                strokeDasharray="4 4"
                label={{ value: `ZK ${stopLoss}`, position: 'insideBottomLeft', fill: '#fb7185', fontSize: 10 }}
              />
            ) : null}
            {idealBuy && Number.isFinite(idealBuy) ? (
              <ReferenceLine
                y={idealBuy}
                stroke="#38bdf8"
                strokeDasharray="3 3"
                label={{ value: `Alım ${idealBuy}`, position: 'insideTopLeft', fill: '#7dd3fc', fontSize: 10 }}
              />
            ) : null}
            {takeProfit && Number.isFinite(takeProfit) ? (
              <ReferenceLine
                y={takeProfit}
                stroke="#10b981"
                strokeDasharray="4 4"
                label={{ value: `KA ${takeProfit}`, position: 'insideTopRight', fill: '#34d399', fontSize: 10 }}
              />
            ) : null}
            <Area
              type="monotone"
              dataKey="close"
              name="Kapanış"
              stroke="#38bdf8"
              strokeWidth={2}
              fill="url(#reportPriceFill)"
              isAnimationActive={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </Card>
  );
};
