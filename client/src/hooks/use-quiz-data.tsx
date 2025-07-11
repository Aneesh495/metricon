import { useState, useEffect } from "react";
import { LocalSubmissions, ProcessedQuestion, QuizStats, FilterType } from "@/types/quiz";
import { processQuizData, getLocalStorageData } from "@/utils/data-processor";

export function useQuizData() {
  const [localSubmissions, setLocalSubmissions] = useState<LocalSubmissions>({});
  const [stats, setStats] = useState<QuizStats>({
    totalAttempts: 0,
    correctAnswers: 0,
    incorrectAnswers: 0,
    accuracyPercentage: 0,
    totalQuestions: 0,
    avgAttempts: 0,
    masteredQuestions: 0
  });
  const [questions, setQuestions] = useState<ProcessedQuestion[]>([]);
  const [performanceData, setPerformanceData] = useState<Array<{ attempt: number; correct: boolean; questionId: string }>>([]);
  const [filter, setFilter] = useState<FilterType>({ type: "all", sort: "attempts" });
  const [loading, setLoading] = useState(true);

  const loadData = () => {
    setLoading(true);
    try {
      const data = getLocalStorageData();
      const processed = processQuizData(data);
      
      setLocalSubmissions(data);
      setStats(processed.stats);
      setQuestions(processed.questions);
      setPerformanceData(processed.performanceData);
    } catch (error) {
      console.error('Error processing quiz data:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const filteredQuestions = questions
    .filter(question => {
      if (filter.type === "correct") {
        return question.correctAttempts > 0;
      } else if (filter.type === "incorrect") {
        return question.incorrectAttempts > 0;
      }
      return true;
    })
    .sort((a, b) => {
      switch (filter.sort) {
        case "attempts":
          return b.totalAttempts - a.totalAttempts;
        case "accuracy-high":
          return b.accuracy - a.accuracy;
        case "accuracy-low":
          return a.accuracy - b.accuracy;
        case "recent":
          return 0; // Keep original order for recent
        default:
          return 0;
      }
    });

  return {
    stats,
    questions: filteredQuestions,
    performanceData,
    filter,
    setFilter,
    loading,
    refreshData: loadData
  };
}
