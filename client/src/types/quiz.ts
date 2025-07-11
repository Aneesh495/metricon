export interface QuizAttempt {
  id: string;
  correct: boolean;
  userSolution: number[];
  type: "MULTIPLE_CHOICE";
}

export interface QuestionData {
  attempts: QuizAttempt[];
}

export interface LocalSubmissions {
  [questionId: string]: QuestionData;
}

export interface ProcessedQuestion {
  id: string;
  totalAttempts: number;
  correctAttempts: number;
  incorrectAttempts: number;
  accuracy: number;
  attempts: QuizAttempt[];
  lastAttemptCorrect: boolean;
}

export interface QuizStats {
  totalAttempts: number;
  correctAnswers: number;
  incorrectAnswers: number;
  accuracyPercentage: number;
  totalQuestions: number;
  avgAttempts: number;
  masteredQuestions: number;
}

export interface FilterType {
  type: "all" | "correct" | "incorrect";
  sort: "attempts" | "accuracy-high" | "accuracy-low" | "recent";
}
