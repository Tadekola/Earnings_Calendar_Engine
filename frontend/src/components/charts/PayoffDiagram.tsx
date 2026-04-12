"use client";

import {
  ResponsiveContainer,
  ComposedChart,
  Area,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  ReferenceLine,
  Tooltip,
} from "recharts";
import { RecommendedTrade } from "@/lib/api";

interface PayoffPoint {
  price: number;
  pnl: number;
}

function computePayoff(trade: RecommendedTrade): PayoffPoint[] {
  const legs = trade.legs;
  const spot = trade.spot_price;
  const totalDebit = trade.total_debit_mid;

  // Calculate P&L across price range
  const lower = trade.lower_strike;
  const upper = trade.upper_strike;
  const spread = upper - lower;
  const rangeMin = Math.max(0, spot - spread * 2.5);
  const rangeMax = spot + spread * 2.5;
  const step = (rangeMax - rangeMin) / 200;

  const points: PayoffPoint[] = [];

  for (let price = rangeMin; price <= rangeMax; price += step) {
    let pnl = -totalDebit; // Start with the debit paid

    for (const leg of legs) {
      const isCall = leg.option_type === "CALL";
      const isBuy = leg.side === "BUY";
      const mid = leg.mid ?? 0;

      // Intrinsic value at expiration
      let intrinsic = 0;
      if (isCall) {
        intrinsic = Math.max(0, price - leg.strike);
      } else {
        intrinsic = Math.max(0, leg.strike - price);
      }

      if (isBuy) {
        pnl += intrinsic;
      } else {
        pnl -= intrinsic;
      }
    }

    points.push({
      price: Math.round(price * 100) / 100,
      pnl: Math.round(pnl * 100) / 100,
    });
  }

  return points;
}

interface PayoffDiagramProps {
  trade: RecommendedTrade;
  height?: number;
}

export default function PayoffDiagram({ trade, height = 280 }: PayoffDiagramProps) {
  const data = computePayoff(trade);

  const maxProfit = Math.max(...data.map((d) => d.pnl));
  const maxLoss = Math.min(...data.map((d) => d.pnl));
  const yMin = Math.floor(maxLoss * 1.2);
  const yMax = Math.ceil(maxProfit * 1.2);

  return (
    <div className="w-full">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-gray-700 uppercase tracking-wide dark:text-gray-300">
          P&L at Expiration
        </h3>
        <div className="flex items-center gap-4 text-xs">
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-2.5 w-2.5 rounded-full bg-emerald-500" />
            Max Profit: <span className="font-mono font-semibold text-emerald-600">${maxProfit.toFixed(2)}</span>
          </span>
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-2.5 w-2.5 rounded-full bg-red-500" />
            Max Loss: <span className="font-mono font-semibold text-red-600">${maxLoss.toFixed(2)}</span>
          </span>
        </div>
      </div>
      <ResponsiveContainer width="100%" height={height}>
        <ComposedChart data={data} margin={{ top: 5, right: 20, bottom: 20, left: 10 }}>
          <defs>
            <linearGradient id="profitGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#10b981" stopOpacity={0.3} />
              <stop offset="100%" stopColor="#10b981" stopOpacity={0} />
            </linearGradient>
            <linearGradient id="lossGrad" x1="0" y1="1" x2="0" y2="0">
              <stop offset="0%" stopColor="#ef4444" stopOpacity={0.15} />
              <stop offset="100%" stopColor="#ef4444" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#e9ecef" />
          <XAxis
            dataKey="price"
            tick={{ fontSize: 10, fill: "#6b7280" }}
            tickFormatter={(v) => `$${v.toFixed(0)}`}
            label={{ value: "Stock Price", position: "bottom", offset: 0, fontSize: 11, fill: "#9ca3af" }}
          />
          <YAxis
            domain={[yMin, yMax]}
            tick={{ fontSize: 10, fill: "#6b7280" }}
            tickFormatter={(v) => `$${v}`}
            width={50}
          />
          <Tooltip
            formatter={(value) => [`$${Number(value).toFixed(2)}`, "P&L"]}
            labelFormatter={(label) => `Price: $${Number(label).toFixed(2)}`}
            contentStyle={{
              backgroundColor: "#1f2937",
              border: "none",
              borderRadius: "8px",
              color: "#f3f4f6",
              fontSize: "12px",
              fontFamily: "var(--font-mono)",
            }}
          />
          <ReferenceLine y={0} stroke="#6b7280" strokeWidth={1.5} strokeDasharray="4 4" />
          <ReferenceLine
            x={trade.spot_price}
            stroke="#4263eb"
            strokeWidth={1}
            strokeDasharray="3 3"
            label={{ value: "Spot", position: "top", fontSize: 10, fill: "#4263eb" }}
          />
          {trade.profit_zone_low && (
            <ReferenceLine
              x={trade.profit_zone_low}
              stroke="#10b981"
              strokeWidth={1}
              strokeDasharray="2 2"
            />
          )}
          {trade.profit_zone_high && (
            <ReferenceLine
              x={trade.profit_zone_high}
              stroke="#10b981"
              strokeWidth={1}
              strokeDasharray="2 2"
            />
          )}
          <Area
            type="monotone"
            dataKey="pnl"
            stroke="none"
            fill="url(#profitGrad)"
            fillOpacity={1}
            baseLine={0}
            isAnimationActive={false}
          />
          <Line
            type="monotone"
            dataKey="pnl"
            stroke="#4263eb"
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
          />
        </ComposedChart>
      </ResponsiveContainer>
      {trade.profit_zone_low && trade.profit_zone_high && (
        <div className="mt-2 text-center text-xs text-gray-500 dark:text-gray-400">
          Profit zone: <span className="font-mono font-semibold text-emerald-600">${trade.profit_zone_low.toFixed(2)}</span>
          {" — "}
          <span className="font-mono font-semibold text-emerald-600">${trade.profit_zone_high.toFixed(2)}</span>
          {" "}| Breakeven width: <span className="font-mono font-semibold">
            ${(trade.profit_zone_high - trade.profit_zone_low).toFixed(2)}
          </span>
        </div>
      )}
    </div>
  );
}
