import { BookOpen } from "lucide-react";
import { PageStub } from "@/components/common/page-stub";

export default function TradeJournalPage() {
  return (
    <PageStub
      title="Trade Journal"
      description="Simulated trade tracking arrives with Phase 6.0.5+. Use Historical Replay for session-level fills today."
      phase="Coming later · Phase 6.0.5+"
      icon={BookOpen}
    />
  );
}
