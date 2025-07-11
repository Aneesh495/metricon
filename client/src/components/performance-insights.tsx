import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { ProcessedQuestion, QuizStats } from "@/types/quiz";
import { 
  TrendingUp, 
  TrendingDown, 
  Target, 
  Award, 
  AlertCircle,
  CheckCircle2,
  BarChart3,
  Brain
} from "lucide-react";

interface PerformanceInsightsProps {
  stats: QuizStats;
  questions: ProcessedQuestion[];
}

export function PerformanceInsights({ stats, questions }: PerformanceInsightsProps) {
  // Calculate insights
  const getPerformanceInsights = () => {
    const insights = [];
    
    // Overall performance assessment
    if (stats.accuracyPercentage >= 80) {
      insights.push({
        type: "success",
        icon: Award,
        title: "Excellent Performance",
        description: `You're performing exceptionally well with ${stats.accuracyPercentage.toFixed(1)}% accuracy!`,
        action: "Continue challenging yourself with harder questions."
      });
    } else if (stats.accuracyPercentage >= 60) {
      insights.push({
        type: "warning",
        icon: Target,
        title: "Good Progress",
        description: `You're on the right track with ${stats.accuracyPercentage.toFixed(1)}% accuracy.`,
        action: "Focus on reviewing incorrect answers to improve further."
      });
    } else {
      insights.push({
        type: "alert",
        icon: AlertCircle,
        title: "Room for Improvement",
        description: `Your accuracy is ${stats.accuracyPercentage.toFixed(1)}%. Don't worry, practice makes perfect!`,
        action: "Review fundamentals and practice more frequently."
      });
    }

    // Attempt efficiency
    if (stats.avgAttempts <= 1.5) {
      insights.push({
        type: "success",
        icon: CheckCircle2,
        title: "Efficient Learning",
        description: `You typically need only ${stats.avgAttempts.toFixed(1)} attempts per question.`,
        action: "Your learning efficiency is excellent!"
      });
    } else if (stats.avgAttempts >= 3) {
      insights.push({
        type: "info",
        icon: Brain,
        title: "Persistence Pays Off",
        description: `You average ${stats.avgAttempts.toFixed(1)} attempts per question.`,
        action: "Consider reviewing material before attempting questions."
      });
    }

    // Question mastery
    const masteryRate = (stats.masteredQuestions / stats.totalQuestions) * 100;
    if (masteryRate >= 70) {
      insights.push({
        type: "success",
        icon: TrendingUp,
        title: "High Mastery Rate",
        description: `You've mastered ${masteryRate.toFixed(1)}% of questions on your latest attempts.`,
        action: "Great job! You're building strong understanding."
      });
    } else if (masteryRate < 30) {
      insights.push({
        type: "alert",
        icon: TrendingDown,
        title: "Focus on Consistency",
        description: `Only ${masteryRate.toFixed(1)}% of questions were answered correctly on the latest attempt.`,
        action: "Review and practice to build consistent performance."
      });
    }

    return insights;
  };

  const getQuestionCategories = () => {
    const struggling = questions.filter(q => q.accuracy < 50 && q.totalAttempts >= 2);
    const improving = questions.filter(q => {
      if (q.attempts.length < 2) return false;
      const recent = q.attempts.slice(-2);
      return recent.every(a => a.correct) && q.attempts.some(a => !a.correct);
    });
    const mastered = questions.filter(q => q.accuracy >= 80 && q.totalAttempts >= 2);

    return { struggling, improving, mastered };
  };

  const insights = getPerformanceInsights();
  const categories = getQuestionCategories();

  const getInsightBadgeColor = (type: string) => {
    switch (type) {
      case "success": return "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200";
      case "warning": return "bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200";
      case "alert": return "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200";
      default: return "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200";
    }
  };

  return (
    <div className="space-y-6">
      {/* Performance Insights */}
      <Card className="bg-card dark:bg-card border-border">
        <CardHeader>
          <CardTitle className="flex items-center text-foreground">
            <BarChart3 className="h-5 w-5 mr-2 text-primary" />
            Performance Insights
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {insights.map((insight, index) => (
            <div key={index} className="p-4 rounded-lg bg-muted/30 dark:bg-muted/20 border border-border">
              <div className="flex items-start space-x-3">
                <div className={`p-2 rounded-full ${getInsightBadgeColor(insight.type)}`}>
                  <insight.icon className="h-4 w-4" />
                </div>
                <div className="flex-1">
                  <h4 className="font-medium text-foreground">{insight.title}</h4>
                  <p className="text-sm text-muted-foreground mt-1">{insight.description}</p>
                  <p className="text-sm text-primary mt-2 font-medium">{insight.action}</p>
                </div>
              </div>
            </div>
          ))}
        </CardContent>
      </Card>

      {/* Question Categories */}
      <Card className="bg-card dark:bg-card border-border">
        <CardHeader>
          <CardTitle className="text-foreground">Question Categories</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {/* Struggling Questions */}
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <h4 className="font-medium text-foreground">Needs Focus</h4>
                <Badge variant="destructive" className="bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200">
                  {categories.struggling.length}
                </Badge>
              </div>
              <Progress 
                value={(categories.struggling.length / stats.totalQuestions) * 100} 
                className="h-2 bg-muted"
              />
              <p className="text-xs text-muted-foreground">
                Questions with low accuracy that need more practice
              </p>
            </div>

            {/* Improving Questions */}
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <h4 className="font-medium text-foreground">Improving</h4>
                <Badge variant="secondary" className="bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200">
                  {categories.improving.length}
                </Badge>
              </div>
              <Progress 
                value={(categories.improving.length / stats.totalQuestions) * 100} 
                className="h-2 bg-muted"
              />
              <p className="text-xs text-muted-foreground">
                Questions showing positive progress trends
              </p>
            </div>

            {/* Mastered Questions */}
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <h4 className="font-medium text-foreground">Mastered</h4>
                <Badge className="bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200">
                  {categories.mastered.length}
                </Badge>
              </div>
              <Progress 
                value={(categories.mastered.length / stats.totalQuestions) * 100} 
                className="h-2 bg-muted"
              />
              <p className="text-xs text-muted-foreground">
                Questions consistently answered correctly
              </p>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}