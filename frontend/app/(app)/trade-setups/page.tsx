import { Target } from "lucide-react";
import { PageStub } from "@/components/common/page-stub";

export default function TradeSetupsPage() {
  return (
    <PageStub
      title="Trade Setups"
      description="Structured LONG / SHORT plans with entry, stop, targets, and risk sizing."
      phase="Phase 4"
      icon={Target}
    />
  );
}
