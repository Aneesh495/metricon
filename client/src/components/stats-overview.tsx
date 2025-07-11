import { QuizStats } from "@/types/quiz";
import { Card, CardContent } from "@/components/ui/card";
import { ClipboardList, CheckCircle, XCircle, Percent } from "lucide-react";

interface StatsOverviewProps {
  stats: QuizStats;
}

export function StatsOverview({ stats }: StatsOverviewProps) {
  const cards = [
    {
      title: "Total Attempts",
      value: stats.totalAttempts,
      icon: ClipboardList,
      color: "text-blue-600",
      bgColor: "bg-blue-100"
    },
    {
      title: "Correct Answers",
      value: stats.correctAnswers,
      icon: CheckCircle,
      color: "text-green-600",
      bgColor: "bg-green-100"
    },
    {
      title: "Incorrect Answers",
      value: stats.incorrectAnswers,
      icon: XCircle,
      color: "text-red-600",
      bgColor: "bg-red-100"
    },
    {
      title: "Accuracy Rate",
      value: `${stats.accuracyPercentage.toFixed(1)}%`,
      icon: Percent,
      color: "text-blue-600",
      bgColor: "bg-blue-100"
    }
  ];

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
      {cards.map((card, index) => (
        <Card key={index} className="enhanced-card card-hover transition-all duration-300 hover:shadow-lg hover:-translate-y-1">
          <CardContent className="p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-muted-foreground">{card.title}</p>
                <p className={`text-3xl font-bold ${card.color} dark:${card.color.replace('600', '400')}`}>{card.value}</p>
              </div>
              <div className={`h-12 w-12 ${card.bgColor} dark:bg-opacity-20 rounded-lg flex items-center justify-center`}>
                <card.icon className={`${card.color} dark:${card.color.replace('600', '400')} h-6 w-6`} />
              </div>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
