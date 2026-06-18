/**
 * LLMExplanationPanel — Displays the GPT-4o generated portfolio explanation.
 *
 * Shows the LLM-generated narrative explaining:
 *   - Why the classical optimizer chose these weights
 *   - How the quantum approach differs
 *   - Which strategy is recommended and why
 *
 * Features:
 *   - Markdown-like rendering (bold, italic, paragraphs, bullet lists)
 *   - Skeleton loading state while explanation is being generated
 *   - Collapsible on mobile
 *
 * Props:
 *   explanation — the LLM explanation string (null while loading)
 *   isLoading   — true while the llm_explanation node is running
 *
 * React 19 migration notes:
 *   - No forwardRef — refs are plain props in React 19
 *   - useId() for stable ARIA IDs
 *   - Removed React namespace prefix where not needed
 *   - Type-only imports use `import type`
 */

import { useState, useId } from "react";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { MessageSquare, ChevronDown, ChevronUp, Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";

// ── Types ─────────────────────────────────────────────────────────────────────

interface LLMExplanationPanelProps {
  explanation: string | null | undefined;
  isLoading?: boolean;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

/**
 * Very lightweight markdown-like renderer.
 * Handles: **bold**, *italic*, paragraph breaks, and bullet points (- item).
 * Does NOT use a full markdown library to keep the bundle small.
 */
function renderExplanation(text: string): React.ReactNode {
  const paragraphs = text.split(/\n\n+/);

  return paragraphs.map((para, pIdx) => {
    // Bullet list paragraph
    if (para.trim().startsWith("- ") || para.trim().startsWith("• ")) {
      const items = para
        .split("\n")
        .filter(
          (line) =>
            line.trim().startsWith("- ") || line.trim().startsWith("• "),
        );
      return (
        <ul key={pIdx} className="my-2 ml-4 list-disc space-y-1">
          {items.map((item, iIdx) => (
            <li key={iIdx} className="text-sm leading-relaxed">
              {renderInline(item.replace(/^[-•]\s+/, ""))}
            </li>
          ))}
        </ul>
      );
    }

    // Regular paragraph
    return (
      <p key={pIdx} className="text-sm leading-relaxed">
        {renderInline(para)}
      </p>
    );
  });
}

/**
 * Render inline formatting: **bold** and *italic*.
 */
function renderInline(text: string): React.ReactNode {
  // Split on **bold** and *italic* markers
  const parts = text.split(/(\*\*[^*]+\*\*|\*[^*]+\*)/g);

  return parts.map((part, idx) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return (
        <strong key={idx} className="font-semibold text-foreground">
          {part.slice(2, -2)}
        </strong>
      );
    }
    if (part.startsWith("*") && part.endsWith("*")) {
      return (
        <em key={idx} className="italic">
          {part.slice(1, -1)}
        </em>
      );
    }
    return part;
  });
}

// ── Loading skeleton ──────────────────────────────────────────────────────────

function ExplanationSkeleton() {
  return (
    <div className="space-y-2 animate-pulse" aria-label="Loading explanation…" aria-busy="true">
      <Skeleton className="h-4 w-full" />
      <Skeleton className="h-4 w-[92%]" />
      <Skeleton className="h-4 w-[85%]" />
      <Skeleton className="h-4 w-full" />
      <Skeleton className="h-4 w-[78%]" />
      <div className="pt-1" />
      <Skeleton className="h-4 w-full" />
      <Skeleton className="h-4 w-[88%]" />
      <Skeleton className="h-4 w-[70%]" />
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export function LLMExplanationPanel({
  explanation,
  isLoading = false,
}: LLMExplanationPanelProps) {
  const [isExpanded, setIsExpanded] = useState(true);
  const panelId = useId();
  const contentId = useId();

  const hasContent = Boolean(explanation);

  return (
    <section
      className="rounded-lg border bg-card"
      aria-labelledby={panelId}
    >
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-3">
        <div className="flex items-center gap-2 flex-1">
          <Sparkles className="h-4 w-4 text-violet-500" aria-hidden="true" />
          <h3 id={panelId} className="text-sm font-semibold">
            AI Portfolio Explanation
          </h3>
          <span className="rounded-full bg-violet-100 px-2 py-0.5 text-xs font-medium text-violet-700 dark:bg-violet-900/30 dark:text-violet-400">
            GPT-4o
          </span>
        </div>
        {hasContent && (
          <Button
            variant="ghost"
            size="sm"
            className="h-7 w-7 p-0"
            onClick={() => setIsExpanded((prev) => !prev)}
            aria-label={isExpanded ? "Collapse explanation" : "Expand explanation"}
            aria-expanded={isExpanded}
            aria-controls={contentId}
          >
            {isExpanded ? (
              <ChevronUp className="h-4 w-4" aria-hidden="true" />
            ) : (
              <ChevronDown className="h-4 w-4" aria-hidden="true" />
            )}
          </Button>
        )}
      </div>

      <Separator />

      {/* Content */}
      <div
        id={contentId}
        className={cn(
          "overflow-hidden transition-all duration-300",
          isExpanded ? "max-h-[600px]" : "max-h-0",
        )}
        role="region"
        aria-label="AI explanation content"
        hidden={!isExpanded}
      >
        <div className="px-4 py-4">
          {isLoading && !hasContent && <ExplanationSkeleton />}

          {!isLoading && !hasContent && (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <MessageSquare className="h-4 w-4" aria-hidden="true" />
              <span>
                Explanation will appear here once the optimization completes.
              </span>
            </div>
          )}

          {hasContent && (
            <div className="prose-sm space-y-3 text-foreground/90">
              {renderExplanation(explanation!)}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
