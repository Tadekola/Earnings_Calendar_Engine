"use client";

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  Legend,
} from "recharts";
import { IVPoint } from "@/lib/api";

interface IVTermStructureProps {
  points: IVPoint[];
  spotPrice: number;
}

export default function IVTermStructure({ points, spotPrice }: IVTermStructureProps) {
  if (!points || points.length === 0) {
    return (
      <div className="flex h-48 items-center justify-center text-sm text-gray-400">
        No IV data available
      </div>
    );
  }

  const data = points.map((p) => ({
    dte: p.days_to_expiry,
    label: `${p.days_to_expiry}d`,
    atm_iv: p.atm_iv,
    call_iv: p.call_iv,
    put_iv: p.put_iv,
    expiration: p.expiration,
  }));

  const ivValues = data.map((d) => d.atm_iv);
  const minIV = Math.floor(Math.min(...ivValues) * 0.9);
  const maxIV = Math.ceil(Math.max(...ivValues) * 1.1);

  return (
    <ResponsiveContainer width="100%" height={280}>
      <LineChart data={data} margin={{ top: 10, right: 20, left: 0, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.3} />
        <XAxis
          dataKey="dte"
          tick={{ fill: "#9CA3AF", fontSize: 11 }}
          label={{ value: "Days to Expiry", position: "insideBottom", offset: -2, fill: "#6B7280", fontSize: 11 }}
        />
        <YAxis
          domain={[minIV, maxIV]}
          tick={{ fill: "#9CA3AF", fontSize: 11 }}
          tickFormatter={(v: number) => `${v}%`}
          label={{ value: "IV %", angle: -90, position: "insideLeft", fill: "#6B7280", fontSize: 11 }}
        />
        <Tooltip
          contentStyle={{
            backgroundColor: "#1F2937",
            border: "1px solid #374151",
            borderRadius: 8,
            fontSize: 12,
          }}
          labelStyle={{ color: "#D1D5DB" }}
          formatter={((value: any, name: any) => [
            `${Number(value).toFixed(1)}%`,
            name === "atm_iv" ? "ATM IV" : name === "call_iv" ? "Call IV" : "Put IV",
          ]) as any}
          labelFormatter={(dte: unknown) => `${dte} days to expiry`}
        />
        <Legend
          wrapperStyle={{ fontSize: 11 }}
          formatter={(value: string) =>
            value === "atm_iv" ? "ATM IV" : value === "call_iv" ? "Call IV" : "Put IV"
          }
        />
        <Line
          type="monotone"
          dataKey="atm_iv"
          stroke="#6366F1"
          strokeWidth={2.5}
          dot={{ fill: "#6366F1", r: 4 }}
          activeDot={{ r: 6 }}
        />
        <Line
          type="monotone"
          dataKey="call_iv"
          stroke="#10B981"
          strokeWidth={1.5}
          strokeDasharray="5 5"
          dot={{ fill: "#10B981", r: 3 }}
        />
        <Line
          type="monotone"
          dataKey="put_iv"
          stroke="#F59E0B"
          strokeWidth={1.5}
          strokeDasharray="5 5"
          dot={{ fill: "#F59E0B", r: 3 }}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
