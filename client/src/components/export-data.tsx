import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Download, FileText, FileSpreadsheet, Loader2 } from "lucide-react";
import { ProcessedQuestion, QuizStats } from "@/types/quiz";
import { useToast } from "@/hooks/use-toast";

interface ExportDataProps {
  stats: QuizStats;
  questions: ProcessedQuestion[];
}

export function ExportData({ stats, questions }: ExportDataProps) {
  const [isExporting, setIsExporting] = useState(false);
  const { toast } = useToast();

  const generateCSV = () => {
    const headers = [
      "Question ID",
      "Total Attempts",
      "Correct Attempts", 
      "Incorrect Attempts",
      "Accuracy (%)",
      "Last Attempt Result",
      "Attempt History"
    ];

    const rows = questions.map(q => [
      q.id,
      q.totalAttempts,
      q.correctAttempts,
      q.incorrectAttempts,
      q.accuracy.toFixed(2),
      q.lastAttemptCorrect ? "Correct" : "Incorrect",
      q.attempts.map(a => a.correct ? "✓" : "✗").join("")
    ]);

    const csvContent = [
      headers.join(","),
      ...rows.map(row => row.join(","))
    ].join("\n");

    return csvContent;
  };

  const generateHTMLReport = () => {
    return `
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Quiz Analytics Report</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; background: #f9fafb; }
        .container { max-width: 1200px; margin: 0 auto; background: white; padding: 40px; border-radius: 12px; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1); }
        .header { text-align: center; margin-bottom: 40px; border-bottom: 2px solid #e5e7eb; padding-bottom: 20px; }
        .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 40px; }
        .stat-card { background: #f3f4f6; padding: 20px; border-radius: 8px; text-align: center; }
        .stat-value { font-size: 2rem; font-weight: bold; color: #1f2937; }
        .stat-label { color: #6b7280; font-size: 0.9rem; margin-top: 5px; }
        .questions-table { width: 100%; border-collapse: collapse; margin-top: 20px; }
        .questions-table th, .questions-table td { padding: 12px; text-align: left; border-bottom: 1px solid #e5e7eb; }
        .questions-table th { background: #f9fafb; font-weight: 600; }
        .accuracy-high { color: #059669; font-weight: 600; }
        .accuracy-medium { color: #d97706; font-weight: 600; }
        .accuracy-low { color: #dc2626; font-weight: 600; }
        .timestamp { text-align: center; margin-top: 30px; color: #6b7280; font-size: 0.9rem; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Quiz Performance Analytics Report</h1>
            <p>Comprehensive analysis of quiz attempt data</p>
        </div>
        
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-value">${stats.totalAttempts}</div>
                <div class="stat-label">Total Attempts</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">${stats.correctAnswers}</div>
                <div class="stat-label">Correct Answers</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">${stats.incorrectAnswers}</div>
                <div class="stat-label">Incorrect Answers</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">${stats.accuracyPercentage.toFixed(1)}%</div>
                <div class="stat-label">Overall Accuracy</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">${stats.totalQuestions}</div>
                <div class="stat-label">Total Questions</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">${stats.avgAttempts.toFixed(1)}</div>
                <div class="stat-label">Avg Attempts/Question</div>
            </div>
        </div>

        <h2>Question Performance Details</h2>
        <table class="questions-table">
            <thead>
                <tr>
                    <th>Question ID</th>
                    <th>Total Attempts</th>
                    <th>Correct</th>
                    <th>Incorrect</th>
                    <th>Accuracy</th>
                    <th>Last Result</th>
                </tr>
            </thead>
            <tbody>
                ${questions.map(q => {
                  const accuracyClass = q.accuracy >= 75 ? 'accuracy-high' : 
                                       q.accuracy >= 50 ? 'accuracy-medium' : 'accuracy-low';
                  return `
                    <tr>
                        <td><code>${q.id.substring(0, 8)}</code></td>
                        <td>${q.totalAttempts}</td>
                        <td>${q.correctAttempts}</td>
                        <td>${q.incorrectAttempts}</td>
                        <td class="${accuracyClass}">${q.accuracy.toFixed(1)}%</td>
                        <td>${q.lastAttemptCorrect ? '✅ Correct' : '❌ Incorrect'}</td>
                    </tr>
                  `;
                }).join('')}
            </tbody>
        </table>
        
        <div class="timestamp">
            Report generated on ${new Date().toLocaleString()}
        </div>
    </div>
</body>
</html>`;
  };

  const downloadFile = (content: string, filename: string, type: string) => {
    const blob = new Blob([content], { type });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  const handleExport = async (format: 'csv' | 'html') => {
    setIsExporting(true);
    
    try {
      const timestamp = new Date().toISOString().split('T')[0];
      
      if (format === 'csv') {
        const csvContent = generateCSV();
        downloadFile(csvContent, `quiz-analytics-${timestamp}.csv`, 'text/csv');
        toast({
          title: "Export Successful",
          description: "CSV file has been downloaded successfully.",
        });
      } else {
        const htmlContent = generateHTMLReport();
        downloadFile(htmlContent, `quiz-analytics-${timestamp}.html`, 'text/html');
        toast({
          title: "Export Successful", 
          description: "HTML report has been downloaded successfully.",
        });
      }
    } catch (error) {
      toast({
        title: "Export Failed",
        description: "There was an error exporting the data. Please try again.",
        variant: "destructive",
      });
    } finally {
      setIsExporting(false);
    }
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" disabled={isExporting} className="bg-background border-border hover:bg-accent">
          {isExporting ? (
            <Loader2 className="h-4 w-4 mr-2 animate-spin" />
          ) : (
            <Download className="h-4 w-4 mr-2" />
          )}
          Export Data
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="bg-background border-border">
        <DropdownMenuItem 
          onClick={() => handleExport('csv')}
          className="hover:bg-accent hover:text-accent-foreground"
        >
          <FileSpreadsheet className="mr-2 h-4 w-4" />
          <span>Export as CSV</span>
        </DropdownMenuItem>
        <DropdownMenuItem 
          onClick={() => handleExport('html')}
          className="hover:bg-accent hover:text-accent-foreground"
        >
          <FileText className="mr-2 h-4 w-4" />
          <span>Export as HTML Report</span>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}