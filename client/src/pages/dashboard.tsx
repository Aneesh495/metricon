import { useState } from "react";
import { useQuizData } from "@/hooks/use-quiz-data";
import { StatsOverview } from "@/components/stats-overview";
import { PerformanceChart } from "@/components/performance-chart";
import { AccuracyChart } from "@/components/accuracy-chart";
import { FiltersPanel } from "@/components/filters-panel";
import { QuestionsList } from "@/components/questions-list";
import { DifficultyScoring } from "@/components/difficulty-scoring";
import { ExportData } from "@/components/export-data";
import { PerformanceInsights } from "@/components/performance-insights";
import { Benchmarking } from "@/components/benchmarking";
import { ThemeToggle } from "@/components/theme-toggle";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { TrendingUp, RefreshCw, BarChart3, Award, Brain, Users } from "lucide-react";

export default function Dashboard() {
  const { stats, questions, performanceData, filter, setFilter, loading, refreshData } = useQuizData();
  const [activeTab, setActiveTab] = useState("overview");

  if (loading) {
    return (
      <div className="min-h-screen bg-background dark:dark-gradient light-gradient flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mx-auto"></div>
          <p className="text-muted-foreground mt-2">Loading quiz data...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background dark:dark-gradient light-gradient">
      {/* Header */}
      <header className="bg-background/80 dark:bg-background/90 backdrop-blur-sm shadow-sm border-b border-border sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            <div className="flex items-center">
              <TrendingUp className="text-primary h-8 w-8 mr-3" />
              <h1 className="text-xl font-bold text-foreground">Quiz Analytics Dashboard</h1>
            </div>
            <div className="flex items-center space-x-4">
              <ExportData stats={stats} questions={questions} />
              <Button onClick={refreshData} className="bg-primary hover:bg-primary/90">
                <RefreshCw className="h-4 w-4 mr-2" />
                Refresh Data
              </Button>
              <ThemeToggle />
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
          <TabsList className="grid w-full grid-cols-4 mb-8 bg-muted/50">
            <TabsTrigger value="overview" className="flex items-center">
              <BarChart3 className="h-4 w-4 mr-2" />
              Overview
            </TabsTrigger>
            <TabsTrigger value="insights" className="flex items-center">
              <Brain className="h-4 w-4 mr-2" />
              Insights
            </TabsTrigger>
            <TabsTrigger value="difficulty" className="flex items-center">
              <Award className="h-4 w-4 mr-2" />
              Difficulty
            </TabsTrigger>
            <TabsTrigger value="benchmarks" className="flex items-center">
              <Users className="h-4 w-4 mr-2" />
              Benchmarks
            </TabsTrigger>
          </TabsList>

          <TabsContent value="overview" className="space-y-8">
            {/* Stats Overview */}
            <StatsOverview stats={stats} />

            {/* Charts Section */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <PerformanceChart data={performanceData} />
              <AccuracyChart stats={stats} />
            </div>

            {/* Filters and Questions List */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              <FiltersPanel filter={filter} onFilterChange={setFilter} stats={stats} />
              <div className="lg:col-span-2">
                <QuestionsList questions={questions} />
              </div>
            </div>
          </TabsContent>

          <TabsContent value="insights" className="space-y-8">
            <PerformanceInsights stats={stats} questions={questions} />
          </TabsContent>

          <TabsContent value="difficulty" className="space-y-8">
            <DifficultyScoring questions={questions} />
          </TabsContent>

          <TabsContent value="benchmarks" className="space-y-8">
            <Benchmarking stats={stats} />
          </TabsContent>
        </Tabs>
      </main>
    </div>
  );
}
