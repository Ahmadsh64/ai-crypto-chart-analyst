import { BarChart3 } from "lucide-react";
import { PageStub } from "@/components/common/page-stub";

export default function AnalyticsPage() {
  return (
    <PageStub
      title="Performance Analytics"
      description="Win rate, expectancy, drawdown, and other simulated performance metrics."
      phase="Phase 6"
      icon={BarChart3}
    />
  );
}
