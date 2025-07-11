import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { QuizStats } from "@/types/quiz";
import { Users, Trophy, Target, Star, TrendingUp } from "lucide-react";

interface BenchmarkingProps {
  stats: QuizStats;
}

export function Benchmarking({ stats }: BenchmarkingProps) {
  // Simulated benchmark data (in a real app, this would come from your backend)
  const benchmarks = {
    beginner: { accuracy: 45, avgAttempts: 3.2, name: "Beginner" },
    intermediate: { accuracy: 65, avgAttempts: 2.1, name: "Intermediate" },
    advanced: { accuracy: 80, avgAttempts: 1.6, name: "Advanced" },
    expert: { accuracy: 92, avgAttempts: 1.2, name: "Expert" }
  };

  const getUserLevel = () => {
    const { accuracyPercentage, avgAttempts } = stats;
    
    if (accuracyPercentage >= 90 && avgAttempts <= 1.3) {
      return { level: "Expert", tier: 4, color: "text-purple-600 dark:text-purple-400" };
    } else if (accuracyPercentage >= 75 && avgAttempts <= 1.8) {
      return { level: "Advanced", tier: 3, color: "text-blue-600 dark:text-blue-400" };
    } else if (accuracyPercentage >= 60 && avgAttempts <= 2.5) {
      return { level: "Intermediate", tier: 2, color: "text-green-600 dark:text-green-400" };
    } else {
      return { level: "Beginner", tier: 1, color: "text-yellow-600 dark:text-yellow-400" };
    }
  };

  const getPerformancePercentile = () => {
    // Simulated percentile calculation
    const { accuracyPercentage } = stats;
    
    if (accuracyPercentage >= 90) return 95;
    if (accuracyPercentage >= 80) return 85;
    if (accuracyPercentage >= 70) return 70;
    if (accuracyPercentage >= 60) return 55;
    if (accuracyPercentage >= 50) return 40;
    return 25;
  };

  const getNextLevelProgress = () => {
    const currentLevel = getUserLevel();
    const nextTier = Math.min(currentLevel.tier + 1, 4);
    const targetAccuracy = Object.values(benchmarks)[nextTier - 1]?.accuracy || 95;
    const progress = Math.min((stats.accuracyPercentage / targetAccuracy) * 100, 100);
    
    return {
      progress,
      target: targetAccuracy,
      pointsNeeded: Math.max(0, targetAccuracy - stats.accuracyPercentage)
    };
  };

  const userLevel = getUserLevel();
  const percentile = getPerformancePercentile();
  const nextLevel = getNextLevelProgress();

  const achievements = [
    {
      name: "First Steps",
      description: "Complete your first quiz attempt",
      unlocked: stats.totalAttempts > 0,
      icon: Target
    },
    {
      name: "Persistent Learner",
      description: "Complete 10 quiz attempts",
      unlocked: stats.totalAttempts >= 10,
      icon: TrendingUp
    },
    {
      name: "Accuracy Master",
      description: "Achieve 75% overall accuracy",
      unlocked: stats.accuracyPercentage >= 75,
      icon: Star
    },
    {
      name: "Quiz Champion",
      description: "Answer 5 questions correctly in a row",
      unlocked: stats.correctAnswers >= 5,
      icon: Trophy
    }
  ];

  return (
    <div className="space-y-6">
      {/* User Level & Percentile */}
      <Card className="bg-card dark:bg-card border-border">
        <CardHeader>
          <CardTitle className="flex items-center text-foreground">
            <Users className="h-5 w-5 mr-2 text-primary" />
            Performance Level
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className={`text-2xl font-bold ${userLevel.color}`}>{userLevel.level}</h3>
              <p className="text-muted-foreground">Your current skill level</p>
            </div>
            <div className="text-right">
              <p className="text-2xl font-bold text-primary">{percentile}th</p>
              <p className="text-muted-foreground">Percentile</p>
            </div>
          </div>

          {/* Progress to Next Level */}
          {userLevel.tier < 4 && (
            <div className="space-y-2">
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Progress to {Object.values(benchmarks)[userLevel.tier]?.name}</span>
                <span className="font-medium text-foreground">{nextLevel.progress.toFixed(1)}%</span>
              </div>
              <Progress value={nextLevel.progress} className="h-2 bg-muted" />
              <p className="text-xs text-muted-foreground">
                Need {nextLevel.pointsNeeded.toFixed(1)} more accuracy points to advance
              </p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Benchmark Comparison */}
      <Card className="bg-card dark:bg-card border-border">
        <CardHeader>
          <CardTitle className="text-foreground">Benchmark Comparison</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {Object.entries(benchmarks).map(([key, benchmark], index) => {
              const isCurrentLevel = benchmark.name === userLevel.level;
              const userSurpassed = stats.accuracyPercentage >= benchmark.accuracy;
              
              return (
                <div key={key} className="flex items-center justify-between p-3 rounded-lg bg-muted/30 dark:bg-muted/20">
                  <div className="flex items-center space-x-3">
                    <div className={`w-3 h-3 rounded-full ${
                      isCurrentLevel ? 'bg-primary' : 
                      userSurpassed ? 'bg-green-500' : 'bg-gray-300 dark:bg-gray-600'
                    }`} />
                    <div>
                      <p className={`font-medium ${isCurrentLevel ? 'text-primary' : 'text-foreground'}`}>
                        {benchmark.name}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {benchmark.accuracy}% accuracy • {benchmark.avgAttempts} avg attempts
                      </p>
                    </div>
                  </div>
                  {isCurrentLevel && (
                    <Badge className="bg-primary/10 text-primary border-primary/20">
                      Current Level
                    </Badge>
                  )}
                  {userSurpassed && !isCurrentLevel && (
                    <Badge className="bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200">
                      Achieved
                    </Badge>
                  )}
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>

      {/* Achievements */}
      <Card className="bg-card dark:bg-card border-border">
        <CardHeader>
          <CardTitle className="text-foreground">Achievements</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {achievements.map((achievement, index) => (
              <div
                key={index}
                className={`p-4 rounded-lg border transition-all ${
                  achievement.unlocked 
                    ? 'bg-primary/5 border-primary/20 text-foreground' 
                    : 'bg-muted/30 border-border text-muted-foreground'
                }`}
              >
                <div className="flex items-center space-x-3">
                  <div className={`p-2 rounded-full ${
                    achievement.unlocked 
                      ? 'bg-primary/10 text-primary' 
                      : 'bg-muted text-muted-foreground'
                  }`}>
                    <achievement.icon className="h-4 w-4" />
                  </div>
                  <div>
                    <h4 className="font-medium">{achievement.name}</h4>
                    <p className="text-xs">{achievement.description}</p>
                  </div>
                </div>
                {achievement.unlocked && (
                  <Badge className="mt-2 bg-primary/10 text-primary border-primary/20" variant="outline">
                    Unlocked
                  </Badge>
                )}
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}