"use client";

import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Cell,
} from "recharts";
import { ScanResult } from "@/lib/api";

interface Props {
  results: ScanResult[];
  height?: number;
}

function scoreToColor(score: number) {
  if (score >= 70) return "#10b981";
  if (score >= 50) return "#f59e0b";
  return "#ef4444";
}

export default function ScoreDistribution({ results, height = 220 }: Props) {
  const scored = results
    .filter((r) => r.overall_score != null)
    .map((r) => ({
      ticker: r.ticker,
      score: r.overall_score!,
      classification: r.classification,
    }))
    .sort((a, b) => b.score - a.score);

  if (scored.length === 0) return null;

  return (
    <div className="w-full">
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={scored} margin={{ top: 5, right: 10, bottom: 20, left: 10 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e9ecef" vertical={false} />
          <XAxis
            dataKey="ticker"
            tick={{ fontSize: 9, fill: "#6b7280" }}
            angle={-45}
            textAnchor="end"
            interval={0}
            height={50}
          />
          <YAxis
            domain={[0, 100]}
            tick={{ fontSize: 10, fill: "#6b7280" }}
            width={30}
          />
          <Tooltip
            formatter={(value) => [Number(value).toFixed(1), "Score"]}
            contentStyle={{
              backgroundColor: "#1f2937",
              border: "none",
              borderRadius: "8px",
              color: "#f3f4f6",
              fontSize: "12px",
              fontFamily: "var(--font-mono)",
            }}
          />
          <Bar dataKey="score" radius={[4, 4, 0, 0]} maxBarSize={32}>
            {scored.map((entry, index) => (
              <Cell key={index} fill={scoreToColor(entry.score)} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
