import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { ProcessedQuestion } from "@/types/quiz";
import { HelpCircle, CheckCircle, XCircle, ChevronRight } from "lucide-react";

interface QuestionsListProps {
  questions: ProcessedQuestion[];
}

export function QuestionsList({ questions }: QuestionsListProps) {
  const formatQuestionId = (id: string) => {
    return `Question ${id.substring(0, 8)}`;
  };

  const renderAttemptsDots = (attempts: any[]) => {
    return attempts.map((attempt, index) => (
      <div
        key={index}
        className={`h-2 w-2 rounded-full ${
          attempt.correct ? 'bg-green-500' : 'bg-red-500'
        }`}
      />
    ));
  };

  return (
    <Card className="enhanced-card shadow-sm">
      <CardContent className="p-6">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-lg font-semibold text-foreground">Question Performance</h2>
        </div>

        <div className="space-y-4 max-h-96 overflow-y-auto custom-scrollbar">
          {questions.map((question) => (
            <div
              key={question.id}
              className="border border-border rounded-lg p-4 hover:bg-muted/50 dark:hover:bg-muted/20 transition-colors"
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-3">
                  <div className="h-10 w-10 rounded-lg bg-muted flex items-center justify-center">
                    <HelpCircle className="h-5 w-5 text-muted-foreground" />
                  </div>
                  <div>
                    <h3 className="font-medium text-foreground">
                      {formatQuestionId(question.id)}
                    </h3>
                    <p className="text-sm text-muted-foreground">
                      {question.totalAttempts} attempts • {question.accuracy.toFixed(1)}% accuracy
                    </p>
                  </div>
                </div>
                <div className="flex items-center space-x-2">
                  <div className="flex items-center space-x-1">
                    <CheckCircle className="h-4 w-4 text-green-500 dark:text-green-400" />
                    <span className="text-sm text-green-600 dark:text-green-400 font-medium">
                      {question.correctAttempts}
                    </span>
                  </div>
                  <div className="flex items-center space-x-1">
                    <XCircle className="h-4 w-4 text-red-500 dark:text-red-400" />
                    <span className="text-sm text-red-600 dark:text-red-400 font-medium">
                      {question.incorrectAttempts}
                    </span>
                  </div>
                  <button className="text-muted-foreground hover:text-foreground transition-colors">
                    <ChevronRight className="h-4 w-4" />
                  </button>
                </div>
              </div>

              {/* Attempts Timeline */}
              <div className="mt-4 pl-13">
                <div className="flex items-center space-x-2">
                  <div className="flex items-center space-x-1">
                    {renderAttemptsDots(question.attempts)}
                  </div>
                  <span className="text-xs text-muted-foreground">
                    Latest: {question.lastAttemptCorrect ? 'Correct' : 'Incorrect'}
                  </span>
                </div>
              </div>
            </div>
          ))}
        </div>

        {questions.length === 0 && (
          <div className="text-center py-8">
            <HelpCircle className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
            <p className="text-muted-foreground">No questions match the current filters</p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
