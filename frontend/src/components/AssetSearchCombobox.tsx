/**
 * AssetSearchCombobox — a debounced search combobox for selecting ticker symbols.
 *
 * Behaviour:
 *   - User types a query (min 1 character) → debounced 300 ms → calls backend
 *     /assets/search endpoint via useAssetSearch hook
 *   - Results are shown in a dropdown list
 *   - Selecting a result calls onSelect(ticker, name, sector)
 *   - Already-selected tickers are shown as disabled in the dropdown
 *   - Pressing Escape or clicking outside closes the dropdown
 *   - Keyboard navigation: ArrowUp / ArrowDown / Enter
 *
 * React 19: uses named imports — no `import * as React` needed.
 *
 * Usage:
 *   <AssetSearchCombobox
 *     selectedTickers={["AAPL", "MSFT"]}
 *     onSelect={(ticker, name, sector) => addTicker(ticker, name, sector)}
 *     disabled={isOptimizing}
 *   />
 */

import {
  useState,
  useEffect,
  useRef,
  type ChangeEvent,
  type KeyboardEvent,
} from "react";
import { Search, Loader2, Plus } from "lucide-react";
import { useAssetSearch } from "@/hooks/useAssetSearch";
import { cn } from "@/lib/utils";
import { Input } from "@/components/ui/input";

export interface AssetSearchComboboxProps {
  /** Tickers already in the selection — shown as disabled in results. */
  selectedTickers: string[];
  /** Called when the user picks an asset from the dropdown. */
  onSelect: (ticker: string, name: string, sector?: string) => void;
  /** When true, the input is disabled. */
  disabled?: boolean;
  /** Placeholder text for the search input. */
  placeholder?: string;
  /** Additional class names for the container. */
  className?: string;
}

export function AssetSearchCombobox({
  selectedTickers,
  onSelect,
  disabled = false,
  placeholder = "Search ticker or company name…",
  className,
}: AssetSearchComboboxProps) {
  const [query, setQuery] = useState("");
  const [isOpen, setIsOpen] = useState(false);
  const [highlightedIndex, setHighlightedIndex] = useState(-1);

  const { results, isLoading } = useAssetSearch(query);

  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);

  // Close dropdown when clicking outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (
        containerRef.current &&
        !containerRef.current.contains(event.target as Node)
      ) {
        setIsOpen(false);
        setHighlightedIndex(-1);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  // Open dropdown when results arrive
  useEffect(() => {
    if (results.length > 0 && query.length > 0) {
      setIsOpen(true);
      setHighlightedIndex(-1);
    } else if (results.length === 0 && !isLoading) {
      // Keep open to show "no results" message if query is non-empty
      if (query.length > 0) {
        setIsOpen(true);
      }
    }
  }, [results, isLoading, query]);

  // Scroll highlighted item into view
  useEffect(() => {
    if (highlightedIndex >= 0 && listRef.current) {
      const item = listRef.current.children[highlightedIndex] as HTMLElement;
      item?.scrollIntoView({ block: "nearest" });
    }
  }, [highlightedIndex]);

  function handleInputChange(e: ChangeEvent<HTMLInputElement>) {
    const value = e.target.value;
    setQuery(value);
    if (value.length === 0) {
      setIsOpen(false);
      setHighlightedIndex(-1);
    }
  }

  function handleSelect(ticker: string, name: string, sector?: string) {
    onSelect(ticker, name, sector);
    setQuery("");
    setIsOpen(false);
    setHighlightedIndex(-1);
    inputRef.current?.focus();
  }

  function handleKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (!isOpen) return;

    switch (e.key) {
      case "ArrowDown":
        e.preventDefault();
        setHighlightedIndex((prev) =>
          prev < results.length - 1 ? prev + 1 : 0,
        );
        break;
      case "ArrowUp":
        e.preventDefault();
        setHighlightedIndex((prev) =>
          prev > 0 ? prev - 1 : results.length - 1,
        );
        break;
      case "Enter":
        e.preventDefault();
        if (highlightedIndex >= 0 && highlightedIndex < results.length) {
          const item = results[highlightedIndex];
          if (!selectedTickers.includes(item.ticker)) {
            handleSelect(item.ticker, item.name, item.sector);
          }
        }
        break;
      case "Escape":
        setIsOpen(false);
        setHighlightedIndex(-1);
        break;
    }
  }

  const showNoResults =
    isOpen && !isLoading && query.length > 0 && results.length === 0;
  const showResults = isOpen && results.length > 0;

  return (
    <div ref={containerRef} className={cn("relative", className)}>
      {/* Search input */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          ref={inputRef}
          type="text"
          value={query}
          onChange={handleInputChange}
          onKeyDown={handleKeyDown}
          onFocus={() => {
            if (results.length > 0 && query.length > 0) setIsOpen(true);
          }}
          placeholder={placeholder}
          disabled={disabled}
          className="pl-9 pr-9"
          aria-label="Search for assets"
          aria-autocomplete="list"
          aria-expanded={isOpen}
          aria-controls="asset-search-listbox"
          role="combobox"
          autoComplete="off"
        />
        {isLoading && (
          <Loader2 className="absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 animate-spin text-muted-foreground" />
        )}
      </div>

      {/* Dropdown */}
      {(showResults || showNoResults) && (
        <div className="absolute z-50 mt-1 w-full rounded-md border border-border bg-popover shadow-lg">
          {showNoResults ? (
            <div className="px-3 py-4 text-center text-sm text-muted-foreground">
              No assets found for &ldquo;{query}&rdquo;
            </div>
          ) : (
            <ul
              ref={listRef}
              id="asset-search-listbox"
              role="listbox"
              aria-label="Asset search results"
              className="max-h-60 overflow-y-auto py-1"
            >
              {results.map((asset, index) => {
                const isAlreadySelected = selectedTickers.includes(
                  asset.ticker,
                );
                const isHighlighted = index === highlightedIndex;

                return (
                  <li
                    key={asset.ticker}
                    role="option"
                    aria-selected={isAlreadySelected}
                    aria-disabled={isAlreadySelected}
                    className={cn(
                      "flex cursor-pointer items-center justify-between px-3 py-2 text-sm transition-colors",
                      isHighlighted && !isAlreadySelected
                        ? "bg-accent text-accent-foreground"
                        : "hover:bg-accent/50",
                      isAlreadySelected &&
                        "cursor-not-allowed opacity-50",
                    )}
                    onMouseEnter={() =>
                      !isAlreadySelected && setHighlightedIndex(index)
                    }
                    onMouseDown={(e) => {
                      // Prevent input blur before click registers
                      e.preventDefault();
                      if (!isAlreadySelected) {
                        handleSelect(
                          asset.ticker,
                          asset.name,
                          asset.sector,
                        );
                      }
                    }}
                  >
                    <div className="flex flex-col">
                      <span className="font-semibold">{asset.ticker}</span>
                      <span className="text-xs text-muted-foreground">
                        {asset.name}
                        {asset.sector && ` · ${asset.sector}`}
                        {asset.exchange && ` · ${asset.exchange}`}
                      </span>
                    </div>
                    {isAlreadySelected ? (
                      <span className="text-xs text-muted-foreground">
                        Added
                      </span>
                    ) : (
                      <Plus className="h-4 w-4 text-muted-foreground" />
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
