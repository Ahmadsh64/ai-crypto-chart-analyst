import { Layers } from "lucide-react";
import { PageStub } from "@/components/common/page-stub";

export default function MarketAnalysisPage() {
  return (
    <PageStub
      title="SMC / ICT Analysis"
      description="Market structure, liquidity, order blocks, FVGs, kill zones, and session levels."
      phase="Phase 3"
      icon={Layers}
    />
  );
}
