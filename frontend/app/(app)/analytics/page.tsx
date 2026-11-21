import { BarChart3 } from "lucide-react";
import { PageStub } from "@/components/common/page-stub";

export default function AnalyticsPage() {
  return (
    <PageStub
      title="Performance Analytics"
      description="Standalone win rate / expectancy lives here in Phase 6.0.6+. Performance panels already ship inside Historical Replay."
      phase="Coming later · Phase 6.0.6+"
      icon={BarChart3}
    />
  );
}
