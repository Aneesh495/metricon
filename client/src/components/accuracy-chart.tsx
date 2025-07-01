import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip, Legend } from "recharts";
import { Card, CardContent } from "@/components/ui/card";
import { QuizStats } from "@/types/quiz";

interface AccuracyChartProps {
  stats: QuizStats;
}

export function AccuracyChart({ stats }: AccuracyChartProps) {
  const data = [
    { name: 'Correct', value: stats.correctAnswers, color: '#10b981' },
    { name: 'Incorrect', value: stats.incorrectAnswers, color: '#ef4444' }
  ];

  const COLORS = ['#10b981', '#ef4444'];

  return (
    <Card className="enhanced-card shadow-sm">
      <CardContent className="p-6">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-lg font-semibold text-foreground">Question Accuracy Distribution</h2>
          <button className="text-sm text-primary hover:text-primary/80 transition-colors">
            <span className="mr-1">⤢</span>View Details
          </button>
        </div>
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={data}
                cx="50%"
                cy="50%"
                innerRadius={60}
                outerRadius={100}
                paddingAngle={5}
                dataKey="value"
              >
                {data.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip 
                formatter={(value) => [`${value} attempts`, 'Count']}
                contentStyle={{
                  backgroundColor: 'hsl(var(--background))',
                  border: '1px solid hsl(var(--border))',
                  borderRadius: '6px'
                }}
              />
            </PieChart>
          </ResponsiveContainer>
        </div>
        <div className="flex justify-center space-x-4 mt-4">
          <div className="flex items-center">
            <div className="w-3 h-3 bg-green-500 rounded-full mr-2"></div>
            <span className="text-sm text-muted-foreground">Correct ({stats.correctAnswers})</span>
          </div>
          <div className="flex items-center">
            <div className="w-3 h-3 bg-red-500 rounded-full mr-2"></div>
            <span className="text-sm text-muted-foreground">Incorrect ({stats.incorrectAnswers})</span>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
