import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from "recharts";
import { Card, CardContent } from "@/components/ui/card";

interface PerformanceChartProps {
  data: Array<{ attempt: number; correct: boolean; questionId: string }>;
}

export function PerformanceChart({ data }: PerformanceChartProps) {
  // Transform data for chart
  const chartData = data.map((item, index) => ({
    attempt: index + 1,
    correct: item.correct ? 1 : 0,
    incorrect: item.correct ? 0 : 1,
    questionId: item.questionId
  }));

  return (
    <Card className="enhanced-card shadow-sm">
      <CardContent className="p-6">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-lg font-semibold text-foreground">Performance Over Time</h2>
          <div className="flex items-center space-x-2">
            <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-green-100 text-green-600 dark:bg-green-900/30 dark:text-green-400">
              <div className="w-2 h-2 bg-green-600 dark:bg-green-400 rounded-full mr-1"></div>
              Correct
            </span>
            <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-red-100 text-red-600 dark:bg-red-900/30 dark:text-red-400">
              <div className="w-2 h-2 bg-red-600 dark:bg-red-400 rounded-full mr-1"></div>
              Incorrect
            </span>
          </div>
        </div>
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
              <XAxis 
                dataKey="attempt" 
                tick={{ fontSize: 12, fill: 'hsl(var(--muted-foreground))' }}
                axisLine={false}
                tickLine={false}
              />
              <YAxis 
                domain={[0, 1]}
                ticks={[0, 1]}
                tickFormatter={(value) => value === 1 ? 'Correct' : 'Incorrect'}
                tick={{ fontSize: 12, fill: 'hsl(var(--muted-foreground))' }}
                axisLine={false}
                tickLine={false}
              />
              <Tooltip 
                formatter={(value, name) => [
                  value === 1 ? 'Correct' : 'Incorrect',
                  name === 'correct' ? 'Result' : 'Result'
                ]}
                labelFormatter={(label) => `Attempt ${label}`}
                contentStyle={{
                  backgroundColor: 'hsl(var(--background))',
                  border: '1px solid hsl(var(--border))',
                  borderRadius: '6px'
                }}
              />
              <Line 
                type="monotone" 
                dataKey="correct" 
                stroke="#10b981" 
                strokeWidth={2}
                dot={{ fill: '#10b981', strokeWidth: 2, r: 4 }}
                activeDot={{ r: 6 }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}
