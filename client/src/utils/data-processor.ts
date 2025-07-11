import { LocalSubmissions, ProcessedQuestion, QuizStats, QuizAttempt } from "@/types/quiz";

export function processQuizData(localSubmissions: LocalSubmissions): {
  stats: QuizStats;
  questions: ProcessedQuestion[];
  performanceData: Array<{ attempt: number; correct: boolean; questionId: string }>;
} {
  const questions: ProcessedQuestion[] = [];
  let totalAttempts = 0;
  let totalCorrect = 0;
  let totalIncorrect = 0;
  const performanceData: Array<{ attempt: number; correct: boolean; questionId: string }> = [];
  let attemptIndex = 0;

  // Process each question
  for (const [questionId, questionData] of Object.entries(localSubmissions)) {
    const attempts = questionData.attempts;
    const correctAttempts = attempts.filter(attempt => attempt.correct).length;
    const incorrectAttempts = attempts.length - correctAttempts;
    const accuracy = attempts.length > 0 ? (correctAttempts / attempts.length) * 100 : 0;
    const lastAttemptCorrect = attempts.length > 0 ? attempts[attempts.length - 1].correct : false;

    questions.push({
      id: questionId,
      totalAttempts: attempts.length,
      correctAttempts,
      incorrectAttempts,
      accuracy,
      attempts,
      lastAttemptCorrect
    });

    totalAttempts += attempts.length;
    totalCorrect += correctAttempts;
    totalIncorrect += incorrectAttempts;

    // Build performance data for chart
    attempts.forEach(attempt => {
      performanceData.push({
        attempt: attemptIndex++,
        correct: attempt.correct,
        questionId
      });
    });
  }

  const accuracyPercentage = totalAttempts > 0 ? (totalCorrect / totalAttempts) * 100 : 0;
  const avgAttempts = questions.length > 0 ? totalAttempts / questions.length : 0;
  const masteredQuestions = questions.filter(q => q.lastAttemptCorrect).length;

  const stats: QuizStats = {
    totalAttempts,
    correctAnswers: totalCorrect,
    incorrectAnswers: totalIncorrect,
    accuracyPercentage,
    totalQuestions: questions.length,
    avgAttempts,
    masteredQuestions
  };

  return { stats, questions, performanceData };
}

export function getLocalStorageData(): LocalSubmissions {
  try {
    const stored = localStorage.getItem('quizSubmissions');
    if (!stored) {
      // If no data in localStorage, use the provided sample data
      const sampleData = {
        "1f86e0a7-0736-4f45-85d7-b0e4cdf5f969": {
          "attempts": [
            { "id": "b75b7f23-1a27-40f1-aaaf-3ac2fb5df052", "correct": false, "userSolution": [2], "type": "MULTIPLE_CHOICE" },
            { "id": "87733164-7758-49cd-aff3-ba81d78b2189", "correct": false, "userSolution": [1], "type": "MULTIPLE_CHOICE" },
            { "id": "1ac69fa1-ab04-4c71-a893-df44f06fe5c1", "correct": true, "userSolution": [4], "type": "MULTIPLE_CHOICE" }
          ]
        },
        "2babcb23-91c7-4328-be7e-21d928212a72": {
          "attempts": [
            { "id": "cbe6c697-a405-4855-96ed-f8ac71351b93", "correct": true, "userSolution": [2], "type": "MULTIPLE_CHOICE" }
          ]
        },
        "34b774c2-fd83-480d-acdb-3b170477cdb8": {
          "attempts": [
            { "id": "6dc31110-d753-4044-ad2b-5ec14379e43d", "correct": false, "userSolution": [3], "type": "MULTIPLE_CHOICE" },
            { "id": "7057d4ad-2654-4637-b08c-c7bab6c5afce", "correct": false, "userSolution": [2], "type": "MULTIPLE_CHOICE" },
            { "id": "2b5d6099-8bb8-4d51-aaba-df6948fcedc1", "correct": true, "userSolution": [1], "type": "MULTIPLE_CHOICE" }
          ]
        },
        "92b0b416-a28e-4d94-a6d0-00e30c836209": {
          "attempts": [
            { "id": "6c07efa6-c1ac-490d-bac1-5e7cd41e150c", "correct": false, "userSolution": [4], "type": "MULTIPLE_CHOICE" },
            { "id": "3f57ef1a-a88d-44d3-a001-41d80b9d9c42", "correct": false, "userSolution": [4], "type": "MULTIPLE_CHOICE" },
            { "id": "ded59800-12bf-4b32-93e3-4e3669198e0f", "correct": true, "userSolution": [1], "type": "MULTIPLE_CHOICE" }
          ]
        },
        "ad02cfa5-e269-4f18-953c-eabaf4aba395": {
          "attempts": [
            { "id": "1a68d8ce-5267-4c2d-9c08-3b001c1cd4b8", "correct": false, "userSolution": [1], "type": "MULTIPLE_CHOICE" }
          ]
        },
        "ae399a1f-0722-4de6-a0c9-164a5d3e4a09": {
          "attempts": [
            { "id": "86afd507-8b08-4be6-8eee-e0f211197510", "correct": false, "userSolution": [1], "type": "MULTIPLE_CHOICE" },
            { "id": "392ff2cf-5de7-438c-b8c4-9010e96d3da4", "correct": false, "userSolution": [4], "type": "MULTIPLE_CHOICE" },
            { "id": "c1759689-5b79-43fb-bb61-5f7d41fc8ba6", "correct": true, "userSolution": [3], "type": "MULTIPLE_CHOICE" }
          ]
        },
        "b82e5940-1afd-4514-8fe1-c3bd89adbb27": {
          "attempts": [
            { "id": "3527499c-2c01-4fc5-be9e-588375ed5a08", "correct": false, "userSolution": [0], "type": "MULTIPLE_CHOICE" }
          ]
        },
        "c5fe1087-3fad-40e3-8b02-baa066f7718d": {
          "attempts": [
            { "id": "829a32c1-821d-4558-ba1e-d889cadad2a1", "correct": false, "userSolution": [1], "type": "MULTIPLE_CHOICE" },
            { "id": "399b2822-83c5-4565-9cfb-bde6b4a87d74", "correct": true, "userSolution": [3], "type": "MULTIPLE_CHOICE" }
          ]
        },
        "ce88915a-d4cd-46cb-a1e6-c63f016ce5c7": {
          "attempts": [
            { "id": "1a2165c2-fe40-48dc-b06b-fceedee00319", "correct": false, "userSolution": [4], "type": "MULTIPLE_CHOICE" }
          ]
        },
        "d028ae9b-37c1-4d74-a191-574e365dfa42": {
          "attempts": [
            { "id": "b04df926-749b-450d-a41d-92ba4056145d", "correct": false, "userSolution": [4], "type": "MULTIPLE_CHOICE" }
          ]
        },
        "d44531f1-3cf7-404d-bd10-e9a786484b8a": {
          "attempts": [
            { "id": "adc9bd82-a158-4748-878a-2eb1eb4e955e", "correct": false, "userSolution": [0], "type": "MULTIPLE_CHOICE" },
            { "id": "32fe2248-de2b-42c0-aacd-b988eb5fd2fd", "correct": false, "userSolution": [2], "type": "MULTIPLE_CHOICE" },
            { "id": "9202d742-94e0-406d-a1f0-1078c1e0983a", "correct": true, "userSolution": [4], "type": "MULTIPLE_CHOICE" }
          ]
        },
        "fce43ea6-284e-4347-ab51-b0b32184c310": {
          "attempts": [
            { "id": "c50d3110-aed2-44ba-aa03-cce1ec03a578", "correct": false, "userSolution": [1], "type": "MULTIPLE_CHOICE" }
          ]
        }
      };
      localStorage.setItem('quizSubmissions', JSON.stringify(sampleData));
      return sampleData;
    }
    return JSON.parse(stored);
  } catch (error) {
    console.error('Error reading from localStorage:', error);
    return {};
  }
}
