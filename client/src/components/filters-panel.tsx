import { Card, CardContent } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Label } from "@/components/ui/label";
import { FilterType, QuizStats } from "@/types/quiz";

interface FiltersPanelProps {
  filter: FilterType;
  onFilterChange: (filter: FilterType) => void;
  stats: QuizStats;
}

export function FiltersPanel({ filter, onFilterChange, stats }: FiltersPanelProps) {
  const handleFilterTypeChange = (type: "all" | "correct" | "incorrect") => {
    onFilterChange({ ...filter, type });
  };

  const handleSortChange = (sort: "attempts" | "accuracy-high" | "accuracy-low" | "recent") => {
    onFilterChange({ ...filter, sort });
  };

  return (
    <Card className="enhanced-card shadow-sm">
      <CardContent className="p-6">
        <h2 className="text-lg font-semibold text-foreground mb-4">Filters</h2>
        
        <div className="space-y-4">
          {/* Filter by Result */}
          <div>
            <Label className="text-sm font-medium text-foreground mb-2 block">Filter by Result</Label>
            <RadioGroup value={filter.type} onValueChange={handleFilterTypeChange}>
              <div className="flex items-center space-x-2">
                <RadioGroupItem value="all" id="all" />
                <Label htmlFor="all" className="text-sm text-muted-foreground">All Attempts</Label>
              </div>
              <div className="flex items-center space-x-2">
                <RadioGroupItem value="correct" id="correct" />
                <Label htmlFor="correct" className="text-sm text-muted-foreground">Correct Only</Label>
              </div>
              <div className="flex items-center space-x-2">
                <RadioGroupItem value="incorrect" id="incorrect" />
                <Label htmlFor="incorrect" className="text-sm text-muted-foreground">Incorrect Only</Label>
              </div>
            </RadioGroup>
          </div>

          {/* Sort Options */}
          <div>
            <Label className="text-sm font-medium text-foreground mb-2 block">Sort by</Label>
            <Select value={filter.sort} onValueChange={handleSortChange}>
              <SelectTrigger className="w-full">
                <SelectValue placeholder="Select sort order" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="attempts">Most Attempts</SelectItem>
                <SelectItem value="accuracy-high">Highest Accuracy</SelectItem>
                <SelectItem value="accuracy-low">Lowest Accuracy</SelectItem>
                <SelectItem value="recent">Recent Activity</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {/* Quick Stats */}
          <div className="pt-4 border-t border-border">
            <h3 className="text-sm font-medium text-foreground mb-2">Quick Stats</h3>
            <div className="space-y-2">
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Total Questions</span>
                <span className="font-medium text-foreground">{stats.totalQuestions}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Avg. Attempts/Question</span>
                <span className="font-medium text-foreground">{stats.avgAttempts.toFixed(1)}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Questions Mastered</span>
                <span className="font-medium text-green-600 dark:text-green-400">{stats.masteredQuestions}</span>
              </div>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
