import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ProcessedQuestion } from "@/types/quiz";
import { Brain, TrendingUp, TrendingDown, Minus } from "lucide-react";

interface DifficultyScoringProps {
  questions: ProcessedQuestion[];
}

interface DifficultyAnalysis {
  id: string;
  difficulty: "Easy" | "Medium" | "Hard" | "Expert";
  score: number;
  attempts: number;
  accuracy: number;
  trend: "improving" | "declining" | "stable";
}

export function DifficultyScoring({ questions }: DifficultyScoringProps) {
  const calculateDifficulty = (question: ProcessedQuestion): DifficultyAnalysis => {
    const { totalAttempts, accuracy, attempts } = question;
    
    // Calculate difficulty score based on attempts needed and accuracy
    let score = 0;
    
    // More attempts = higher difficulty
    if (totalAttempts >= 4) score += 40;
    else if (totalAttempts >= 3) score += 25;
    else if (totalAttempts >= 2) score += 10;
    
    // Lower accuracy = higher difficulty
    if (accuracy < 25) score += 40;
    else if (accuracy < 50) score += 25;
    else if (accuracy < 75) score += 15;
    else score += 5;
    
    // Trend analysis (improvement over time)
    let trend: "improving" | "declining" | "stable" = "stable";
    if (attempts.length >= 2) {
      const firstHalf = attempts.slice(0, Math.ceil(attempts.length / 2));
      const secondHalf = attempts.slice(Math.ceil(attempts.length / 2));
      
      const firstHalfAccuracy = firstHalf.filter(a => a.correct).length / firstHalf.length;
      const secondHalfAccuracy = secondHalf.filter(a => a.correct).length / secondHalf.length;
      
      if (secondHalfAccuracy > firstHalfAccuracy + 0.2) trend = "improving";
      else if (secondHalfAccuracy < firstHalfAccuracy - 0.2) trend = "declining";
    }
    
    // Determine difficulty level
    let difficulty: "Easy" | "Medium" | "Hard" | "Expert";
    if (score >= 60) difficulty = "Expert";
    else if (score >= 40) difficulty = "Hard";
    else if (score >= 20) difficulty = "Medium";
    else difficulty = "Easy";
    
    return {
      id: question.id,
      difficulty,
      score,
      attempts: totalAttempts,
      accuracy,
      trend
    };
  };

  const analysisData = questions.map(calculateDifficulty);
  
  const getDifficultyColor = (difficulty: string) => {
    switch (difficulty) {
      case "Easy": return "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200";
      case "Medium": return "bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200";
      case "Hard": return "bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-200";
      case "Expert": return "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200";
      default: return "bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200";
    }
  };

  const getTrendIcon = (trend: string) => {
    switch (trend) {
      case "improving": return <TrendingUp className="h-3 w-3 text-green-600 dark:text-green-400" />;
      case "declining": return <TrendingDown className="h-3 w-3 text-red-600 dark:text-red-400" />;
      default: return <Minus className="h-3 w-3 text-gray-600 dark:text-gray-400" />;
    }
  };

  const difficultyStats = {
    Easy: analysisData.filter(q => q.difficulty === "Easy").length,
    Medium: analysisData.filter(q => q.difficulty === "Medium").length,
    Hard: analysisData.filter(q => q.difficulty === "Hard").length,
    Expert: analysisData.filter(q => q.difficulty === "Expert").length,
  };

  return (
    <Card className="shadow-sm bg-card dark:bg-card border-border">
      <CardHeader>
        <CardTitle className="flex items-center text-foreground">
          <Brain className="h-5 w-5 mr-2 text-primary" />
          Difficulty Analysis
        </CardTitle>
      </CardHeader>
      <CardContent>
        {/* Difficulty Distribution */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
          {Object.entries(difficultyStats).map(([level, count]) => (
            <div key={level} className="text-center">
              <Badge className={getDifficultyColor(level)} variant="secondary">
                {level}
              </Badge>
              <p className="text-2xl font-bold mt-1 text-foreground">{count}</p>
              <p className="text-xs text-muted-foreground">questions</p>
            </div>
          ))}
        </div>

        {/* Individual Question Analysis */}
        <div className="space-y-3">
          <h4 className="font-medium text-foreground">Question Breakdown</h4>
          <div className="max-h-64 overflow-y-auto space-y-2">
            {analysisData.map((analysis) => (
              <div
                key={analysis.id}
                className="flex items-center justify-between p-3 rounded-lg bg-muted/50 dark:bg-muted/20 hover:bg-muted dark:hover:bg-muted/40 transition-colors"
              >
                <div className="flex items-center space-x-3">
                  <span className="text-sm font-mono text-muted-foreground">
                    {analysis.id.substring(0, 8)}
                  </span>
                  <Badge className={getDifficultyColor(analysis.difficulty)} variant="secondary">
                    {analysis.difficulty}
                  </Badge>
                </div>
                <div className="flex items-center space-x-3">
                  <div className="text-right">
                    <p className="text-sm font-medium text-foreground">
                      {analysis.accuracy.toFixed(1)}%
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {analysis.attempts} attempts
                    </p>
                  </div>
                  {getTrendIcon(analysis.trend)}
                </div>
              </div>
            ))}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}