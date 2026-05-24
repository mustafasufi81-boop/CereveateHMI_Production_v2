import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import api from "@/services/api";
import { downloadDailyReportXlsx, downloadDailyReportXlsxFiltered, fetchDailyReport } from "@/services/reportApi";
import { UserHeader } from "@/components/hmi/UserHeader";
import { useTagSelection } from "@/context/tag-selection-context";

interface AreaOption {
  plant: string;
  area: string;
  server_progid: string;
}

const toDateInput = (d: Date) => {
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
};

const DailyReport = () => {
  const { selection, updateSelection } = useTagSelection();
  
  const [date, setDate] = useState<string>(selection.date);
  const [selectedPlants, setSelectedPlants] = useState<string[]>(selection.selectedPlants || []);
  const [selectedAreas, setSelectedAreas] = useState<string[]>(selection.selectedAreas || []);
  const [selectedSource, setSelectedSource] = useState<string>("");
  const [tagSearchFilter, setTagSearchFilter] = useState<string>("");
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [showPlantDropdown, setShowPlantDropdown] = useState<boolean>(false);
  const [showTagDropdown, setShowTagDropdown] = useState<boolean>(false);
  const [showAreaDropdown, setShowAreaDropdown] = useState<boolean>(false);
  const [reportRequest, setReportRequest] = useState<{ date: string; plant: string; area: string; sourceId?: string } | null>(null);
  const [errorMsg, setErrorMsg] = useState<string>("");
  const [isDownloading, setIsDownloading] = useState<boolean>(false);
  const [isDownloadingFiltered, setIsDownloadingFiltered] = useState<boolean>(false);
  const [pageSize, setPageSize] = useState<number>(200);
  const [currentPage, setCurrentPage] = useState<number>(1);
  const [tableScrollWidth, setTableScrollWidth] = useState<number>(0);
  const topScrollRef = useRef<HTMLDivElement | null>(null);
  const bottomScrollRef = useRef<HTMLDivElement | null>(null);
  const tableRef = useRef<HTMLTableElement | null>(null);
  const tagDropdownRef = useRef<HTMLDivElement | null>(null);

  const scrollDataLeft = () => {
    topScrollRef.current?.scrollBy({ left: -240, behavior: "smooth" });
  };

  const scrollDataRight = () => {
    topScrollRef.current?.scrollBy({ left: 240, behavior: "smooth" });
  };

  const areasQuery = useQuery({
    queryKey: ["report-areas"],
    queryFn: async (): Promise<AreaOption[]> => {
      const response = await api.get("/reports/areas");
      return response.data?.areas || [];
    },
    refetchOnWindowFocus: false,
    refetchOnReconnect: true,
    refetchOnMount: true,
    staleTime: 0,
  });

  // CASCADE: Step 1 — all unique sources (exclude blank but keep Unknown)
  const uniqueSources = useMemo(() => {
    const set = new Set<string>();
    (areasQuery.data || []).forEach((x) => { if (x.server_progid && x.server_progid !== 'Unknown') set.add(x.server_progid); });
    return Array.from(set).sort();
  }, [areasQuery.data]);

  // CASCADE: Step 2 — plants filtered by selected source
  const uniquePlants = useMemo(() => {
    const set = new Set<string>();
    (areasQuery.data || [])
      .filter((x) => !selectedSource || x.server_progid === selectedSource)
      .forEach((x) => set.add(x.plant));
    return Array.from(set).sort();
  }, [areasQuery.data, selectedSource]);

  // CASCADE: Step 3 — areas filtered by selected source AND selected plants
  const areasForPlants = useMemo(() => {
    const set = new Set<string>();
    (areasQuery.data || [])
      .filter((x) =>
        (!selectedSource || x.server_progid === selectedSource) &&
        (selectedPlants.length === 0 || selectedPlants.includes(x.plant))
      )
      .forEach((x) => set.add(x.area));
    return Array.from(set).sort();
  }, [areasQuery.data, selectedSource, selectedPlants]);

  // When source changes: reset plants and areas
  useEffect(() => {
    setSelectedPlants([]);
    setSelectedAreas([]);
  }, [selectedSource]);

  // When plant changes: reset areas that are no longer valid, auto-select all valid areas
  useEffect(() => {
    setSelectedAreas(prev => {
      const valid = prev.filter(a => areasForPlants.includes(a));
      if (selectedPlants.length > 0 && valid.length === 0 && areasForPlants.length > 0) return areasForPlants;
      return valid;
    });
  }, [areasForPlants]);

  const togglePlant = (plant: string) => {
    setSelectedPlants(prev => 
      prev.includes(plant) 
        ? prev.filter(p => p !== plant)
        : [...prev, plant]
    );
  };

  const selectAllPlants = () => {
    setSelectedPlants(uniquePlants);
  };

  const clearAllPlants = () => {
    setSelectedPlants([]);
  };

  const toggleArea = (area: string) => {
    setSelectedAreas(prev => 
      prev.includes(area) 
        ? prev.filter(a => a !== area)
        : [...prev, area]
    );
  };

  const selectAllAreas = () => {
    setSelectedAreas(areasForPlants);
  };

  const clearAllAreas = () => {
    setSelectedAreas([]);
  };

  const reportQuery = useQuery({
    queryKey: ["daily-report", reportRequest?.date, reportRequest?.plant, reportRequest?.area, reportRequest?.sourceId, currentPage, pageSize],
    queryFn: () => fetchDailyReport(reportRequest!.date, reportRequest!.plant, reportRequest!.area, reportRequest!.sourceId, currentPage, pageSize),
    enabled: Boolean(reportRequest),
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    refetchOnMount: false,
  });

  const totalRows = reportQuery.data?.pagination?.total_rows ?? 0;
  const totalPages = reportQuery.data?.pagination?.total_pages ?? 0;
  const rows = reportQuery.data?.rows || [];
  const queryErrorMessage =
    (reportQuery.error as any)?.response?.data?.error ||
    (reportQuery.error as any)?.message ||
    "Failed to load report.";

  // Filter rows by tag search (must be after rows definition)
  const filteredRows = useMemo(() => {
    let filtered = rows;
    
    // Apply multi-select tag filter first
    if (selectedTags.length > 0) {
      filtered = filtered.filter((row) => selectedTags.includes(row.tag_id));
    }
    
    // Then apply search filter
    if (tagSearchFilter.trim()) {
      const search = tagSearchFilter.toLowerCase().trim();
      filtered = filtered.filter((row) => 
        row.tag_id?.toLowerCase().includes(search) || 
        row.display_label?.toLowerCase().includes(search)
      );
    }
    
    return filtered;
  }, [rows, tagSearchFilter, selectedTags]);

  // Get all unique tags for multi-select dropdown
  const allTags = useMemo(() => {
    return rows.map(row => ({
      id: row.tag_id,
      label: row.display_label || row.tag_id
    }));
  }, [rows]);

  // Filtered tags for dropdown based on search
  const filteredTagsForDropdown = useMemo(() => {
    if (!tagSearchFilter.trim()) return allTags;
    const searchLower = tagSearchFilter.toLowerCase();
    return allTags.filter(tag => 
      tag.id.toLowerCase().includes(searchLower) || 
      tag.label.toLowerCase().includes(searchLower)
    );
  }, [allTags, tagSearchFilter]);

  const toggleTag = (tagId: string) => {
    setSelectedTags(prev => 
      prev.includes(tagId) 
        ? prev.filter(id => id !== tagId)
        : [...prev, tagId]
    );
  };

  const selectAllTags = () => {
    setSelectedTags(allTags.map(t => t.id));
  };

  const clearAllTags = () => {
    setSelectedTags([]);
  };

  // Close tag dropdown when clicking outside it
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (tagDropdownRef.current && !tagDropdownRef.current.contains(e.target as Node)) {
        setShowTagDropdown(false);
      }
    };
    if (showTagDropdown) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [showTagDropdown]);

  // Reset to page 1 when filter changes
  useEffect(() => { setCurrentPage(1); }, [selectedTags, tagSearchFilter]);

  useEffect(() => {
    setCurrentPage(1);
  }, [pageSize]);

  // Persist selection to context when values change
  useEffect(() => {
    updateSelection({
      date,
      selectedPlants,
      selectedAreas,
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [date, selectedPlants, selectedAreas]);

  useEffect(() => {
    const updateWidth = () => {
      setTableScrollWidth(tableRef.current?.scrollWidth || 0);
    };

    updateWidth();
    window.addEventListener("resize", updateWidth);
    return () => window.removeEventListener("resize", updateWidth);
  }, [reportQuery.data, pageSize, currentPage]);

  useEffect(() => {
    const top = topScrollRef.current;
    const bottom = bottomScrollRef.current;
    if (!top || !bottom) return;

    let syncing = false;

    const handleTopScroll = () => {
      if (syncing) return;
      syncing = true;
      bottom.scrollLeft = top.scrollLeft;
      syncing = false;
    };

    const handleBottomScroll = () => {
      if (syncing) return;
      syncing = true;
      top.scrollLeft = bottom.scrollLeft;
      syncing = false;
    };

    top.addEventListener("scroll", handleTopScroll);
    bottom.addEventListener("scroll", handleBottomScroll);

    return () => {
      top.removeEventListener("scroll", handleTopScroll);
      bottom.removeEventListener("scroll", handleBottomScroll);
    };
  }, [reportQuery.data]);

  const onDownload = async () => {
    if (isDownloading || reportQuery.isFetching) {
      return;
    }

    if (!date || selectedPlants.length === 0 || selectedAreas.length === 0) {
      setErrorMsg("Select date, at least one plant and at least one area.");
      return;
    }

    setErrorMsg("");
    setIsDownloading(true);
    try {
      await downloadDailyReportXlsx(date, selectedPlants.join(","), selectedAreas.join(","), selectedSource || undefined);
    } catch (e: any) {
      setErrorMsg(e?.response?.data?.error || "Failed to download report");
    } finally {
      setIsDownloading(false);
    }
  };

  const onDownloadFiltered = async () => {
    if (isDownloadingFiltered || reportQuery.isFetching) return;
    if (!date || selectedPlants.length === 0 || selectedAreas.length === 0) {
      setErrorMsg("Select date, at least one plant and at least one area.");
      return;
    }
    const tagsToDownload = filteredRows.map(r => r.tag_id);
    if (tagsToDownload.length === 0) {
      setErrorMsg("No tags currently visible to download.");
      return;
    }
    setErrorMsg("");
    setIsDownloadingFiltered(true);
    try {
      await downloadDailyReportXlsxFiltered(date, selectedPlants.join(","), selectedAreas.join(","), tagsToDownload, selectedSource || undefined);
    } catch (e: any) {
      setErrorMsg(e?.response?.data?.error || "Failed to download filtered report");
    } finally {
      setIsDownloadingFiltered(false);
    }
  };

  const onGenerate = () => {
    if (reportQuery.isFetching || isDownloading) {
      return;
    }

    if (!date || selectedPlants.length === 0 || selectedAreas.length === 0) {
      setErrorMsg("Select date, at least one plant and at least one area.");
      return;
    }

    setErrorMsg("");
    setCurrentPage(1);
    setReportRequest({
      date,
      plant: selectedPlants.join(","),
      area: selectedAreas.join(","),
      sourceId: selectedSource || undefined,
    });
  };

  const location = useLocation();

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100 p-4">
      <div className="max-w-[1800px] mx-auto space-y-4">
        {/* Page header */}
        <div className="flex items-center justify-between bg-white rounded-lg shadow-md p-4 border border-gray-200">
          <h1 className="text-2xl font-bold tracking-wide text-gray-800">Reports Dashboard</h1>
          <div className="flex items-center gap-3">
            <Link to="/" className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-semibold transition-colors shadow-md">
              ← Back to HMI
            </Link>
            <UserHeader />
          </div>
        </div>

        {/* Tab strip */}
        <div className="flex bg-white rounded-lg shadow-md overflow-hidden border border-gray-200">
          <Link
            to="/reports/daily"
            className={`px-6 py-3 text-sm font-bold border-b-4 transition-all ${
              location.pathname === "/reports/daily"
                ? "border-blue-600 bg-blue-50 text-blue-700"
                : "border-transparent text-gray-600 hover:text-blue-600 hover:bg-gray-50"
            }`}
          >
            📅 Daily Report
          </Link>
          <Link
            to="/reports/shift"
            className={`px-6 py-3 text-sm font-bold border-b-4 transition-all ${
              location.pathname === "/reports/shift"
                ? "border-blue-600 bg-blue-50 text-blue-700"
                : "border-transparent text-gray-600 hover:text-blue-600 hover:bg-gray-50"
            }`}
          >
            ⏰ Shift Report
          </Link>
          <Link
            to="/reports/monthly"
            className={`px-6 py-3 text-sm font-bold border-b-4 transition-all ${
              location.pathname === "/reports/monthly"
                ? "border-blue-600 bg-blue-50 text-blue-700"
                : "border-transparent text-gray-600 hover:text-blue-600 hover:bg-gray-50"
            }`}
          >
            📈 Monthly Report
          </Link>
        </div>

        <div className="bg-blue-50 border-l-4 border-blue-600 p-3 rounded-r-lg">
          <p className="text-sm font-semibold text-blue-900">ℹ️ Industrial 4-level report view (5 AM to 5 AM)</p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-5 gap-4 bg-white p-6 rounded-lg shadow-lg border-2 border-gray-200">
          <div>
            <label className="text-xs font-bold text-gray-700 block mb-2">📅 Date</label>
            <input
              type="date"
              value={date}
              onChange={(e) => {
                setDate(e.target.value);
                setReportRequest(null);
              }}
              className="w-full bg-white border-2 border-gray-300 rounded-lg px-3 py-2 text-gray-800 font-semibold focus:border-blue-500 focus:ring-2 focus:ring-blue-200 transition-all"
            />
          </div>
          <div>
            <label className="text-xs font-bold text-gray-700 block mb-2">🔌 Source (OPC/PLC)</label>
            <select
              value={selectedSource}
              onChange={(e) => {
                setSelectedSource(e.target.value);
                setSelectedPlants([]);
                setSelectedAreas([]);
                setReportRequest(null);
              }}
              className="w-full bg-white border-2 border-gray-300 rounded-lg px-3 py-2 text-gray-800 font-semibold focus:border-blue-500 focus:ring-2 focus:ring-blue-200 transition-all"
            >
              <option value="">All Sources</option>
              {uniqueSources.map((source) => (
                <option key={source} value={source}>{source}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs font-bold text-gray-700 block mb-2">🏭 Plant ({selectedPlants.length} selected)</label>
            <div className="relative">
              <button
                onClick={() => setShowPlantDropdown(!showPlantDropdown)}
                disabled={uniquePlants.length === 0}
                className="w-full bg-white border-2 border-gray-300 rounded-lg px-3 py-2 text-gray-800 font-semibold focus:border-blue-500 focus:ring-2 focus:ring-blue-200 transition-all text-left disabled:bg-gray-100 disabled:cursor-not-allowed flex items-center justify-between"
                title={uniquePlants.length === 0 ? 'No plants available' : ''}
              >
                <span>{selectedPlants.length > 0 ? `${selectedPlants.length} plant(s)` : 'Select Plants'}</span>
                <span>🔽</span>
              </button>
              {showPlantDropdown && uniquePlants.length > 0 && (
                <div className="absolute top-full left-0 mt-2 w-full max-h-80 overflow-hidden bg-white rounded-lg shadow-2xl border-2 border-blue-500 z-50 flex flex-col">
                  <div className="sticky top-0 bg-blue-50 p-3 border-b-2 border-blue-300 flex items-center justify-between gap-2">
                    <button
                      onClick={selectAllPlants}
                      className="px-3 py-1 bg-green-600 hover:bg-green-700 text-white rounded text-xs font-bold transition-colors"
                    >
                      Select All
                    </button>
                    <button
                      onClick={clearAllPlants}
                      className="px-3 py-1 bg-red-600 hover:bg-red-700 text-white rounded text-xs font-bold transition-colors"
                    >
                      Clear All
                    </button>
                    <button
                      onClick={() => setShowPlantDropdown(false)}
                      className="px-3 py-1 bg-gray-600 hover:bg-gray-700 text-white rounded text-xs font-bold transition-colors"
                    >
                      Close
                    </button>
                  </div>
                  <div className="overflow-y-auto max-h-60 p-2">
                    {uniquePlants.map((plant) => (
                      <label
                        key={plant}
                        className="flex items-center gap-2 p-2 hover:bg-blue-50 rounded cursor-pointer transition-colors"
                      >
                        <input
                          type="checkbox"
                          checked={selectedPlants.includes(plant)}
                          onChange={() => togglePlant(plant)}
                          className="w-4 h-4 text-blue-600 bg-white border-2 border-gray-400 rounded focus:ring-2 focus:ring-blue-500 cursor-pointer"
                        />
                        <span className="text-sm font-semibold text-gray-800">{plant}</span>
                      </label>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
          <div>
            <label className="text-xs font-bold text-gray-700 block mb-2">🏭 Area ({selectedAreas.length} selected)</label>
            <div className="relative">
              <button
                onClick={() => setShowAreaDropdown(!showAreaDropdown)}
                disabled={selectedPlants.length === 0 || areasForPlants.length === 0}
                className="w-full bg-white border-2 border-gray-300 rounded-lg px-3 py-2 text-gray-800 font-semibold focus:border-blue-500 focus:ring-2 focus:ring-blue-200 transition-all text-left disabled:bg-gray-100 disabled:cursor-not-allowed flex items-center justify-between"
                title={selectedPlants.length === 0 ? 'Select a plant first' : ''}
              >
                <span>{selectedAreas.length > 0 ? `${selectedAreas.length} area(s)` : selectedPlants.length === 0 ? 'Select plant first' : 'Select Areas'}</span>
                <span>🔽</span>
              </button>
              {showAreaDropdown && areasForPlants.length > 0 && (
                <div className="absolute top-full left-0 mt-2 w-full max-h-80 overflow-hidden bg-white rounded-lg shadow-2xl border-2 border-blue-500 z-50 flex flex-col">
                  <div className="sticky top-0 bg-blue-50 p-3 border-b-2 border-blue-300 flex items-center justify-between gap-2">
                    <button
                      onClick={selectAllAreas}
                      className="px-3 py-1 bg-green-600 hover:bg-green-700 text-white rounded text-xs font-bold transition-colors"
                    >
                      Select All
                    </button>
                    <button
                      onClick={clearAllAreas}
                      className="px-3 py-1 bg-red-600 hover:bg-red-700 text-white rounded text-xs font-bold transition-colors"
                    >
                      Clear All
                    </button>
                    <button
                      onClick={() => setShowAreaDropdown(false)}
                      className="px-3 py-1 bg-gray-600 hover:bg-gray-700 text-white rounded text-xs font-bold transition-colors"
                    >
                      Close
                    </button>
                  </div>
                  <div className="overflow-y-auto p-2 flex-1">
                    {areasForPlants.map((area) => (
                      <label
                        key={area}
                        className="flex items-center gap-2 p-2 hover:bg-blue-50 rounded cursor-pointer text-gray-800"
                      >
                        <input
                          type="checkbox"
                          checked={selectedAreas.includes(area)}
                          onChange={() => toggleArea(area)}
                          className="w-4 h-4 accent-blue-600"
                        />
                        <span className="text-sm font-medium">{area}</span>
                      </label>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
          <div className="flex items-end">
            <button
              onClick={onGenerate}
              className="w-full bg-blue-600 hover:bg-blue-700 rounded-lg px-4 py-3 font-bold text-white shadow-lg disabled:bg-gray-400 disabled:cursor-not-allowed transition-all transform hover:scale-105"
              disabled={!date || selectedPlants.length === 0 || selectedAreas.length === 0 || reportQuery.isFetching}
            >
              {reportQuery.isFetching ? "⏳ Loading..." : "✅ Generate"}
            </button>
          </div>
          <div className="flex items-end">
            <button
              onClick={onDownload}
              className="w-full bg-emerald-600 hover:bg-emerald-700 rounded-lg px-4 py-3 font-bold text-white shadow-lg disabled:bg-gray-400 disabled:cursor-not-allowed transition-all transform hover:scale-105"
              disabled={!date || selectedPlants.length === 0 || selectedAreas.length === 0 || isDownloading || reportQuery.isFetching}
            >
              {isDownloading ? "⬇️ Downloading..." : "📊 Download Excel"}
            </button>
          </div>
        </div>

        {errorMsg && <div className="bg-red-100 border-l-4 border-red-500 text-red-700 p-4 rounded-r-lg shadow-md font-semibold">⚠️ {errorMsg}</div>}

        {reportQuery.isLoading && <div className="bg-blue-100 border-l-4 border-blue-500 text-blue-700 p-4 rounded-r-lg shadow-md font-semibold">⏳ Loading report...</div>}
        {reportQuery.isError && <div className="bg-red-100 border-l-4 border-red-500 text-red-700 p-4 rounded-r-lg shadow-md font-semibold">❌ {queryErrorMessage}</div>}

        {reportQuery.data && (
          <div className="bg-white border-2 border-gray-300 rounded-lg overflow-hidden shadow-2xl">
            {/* Professional Header with Logo */}
            <div className="bg-gradient-to-r from-blue-900 via-blue-800 to-blue-900 p-6 border-b-4 border-amber-500">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-4">
                  <img 
                    src="/Logo_Company.png" 
                    alt="Company Logo" 
                    className="h-16 w-auto bg-white rounded-lg p-2 shadow-lg"
                    onError={(e) => { e.currentTarget.style.display = 'none'; }}
                  />
                  <div className="text-white">
                    <div className="font-bold text-2xl tracking-wide">{reportQuery.data.meta.company}</div>
                    <div className="text-blue-200 text-lg mt-1">{reportQuery.data.meta.plant}</div>
                  </div>
                </div>
                <div className="text-right text-white">
                  <div className="text-sm text-blue-200">Report Date</div>
                  <div className="font-bold text-xl">{reportQuery.data.meta.date}</div>
                </div>
              </div>
              <div className="mt-4 pt-4 border-t border-blue-700">
                <div className="text-white text-lg font-semibold text-center">
                  {reportQuery.data.meta.report_title}
                </div>
              </div>
            </div>

            {/* Tag Search + Tag Filter */}
            <div className="px-6 py-4 bg-gray-50 border-b-2 border-gray-200">
              <div className="flex items-center gap-3 flex-wrap">
                <label htmlFor="tag-search" className="text-sm font-semibold text-gray-700 whitespace-nowrap">🔍 Search Tags:</label>
                <input
                  id="tag-search"
                  type="text"
                  value={tagSearchFilter}
                  onChange={(e) => setTagSearchFilter(e.target.value)}
                  placeholder="Filter by tag ID or label..."
                  className="flex-1 bg-white border-2 border-gray-300 rounded-lg px-4 py-2 text-sm text-gray-800 placeholder-gray-400 focus:border-blue-500 focus:ring-2 focus:ring-blue-200 transition-all"
                />
                {tagSearchFilter && (
                  <button
                    onClick={() => setTagSearchFilter("")}
                    className="px-4 py-2 bg-red-500 hover:bg-red-600 text-white rounded-lg text-sm font-semibold transition-colors shadow-md"
                  >
                    Clear
                  </button>
                )}
                {/* Tag multi-select filter — lives HERE (outside overflow-x-auto) */}
                <div className="relative" ref={tagDropdownRef}>
                  <button
                    onClick={() => setShowTagDropdown(!showTagDropdown)}
                    className={`px-4 py-2 rounded-lg text-sm font-semibold transition-colors shadow-md ${
                      selectedTags.length > 0
                        ? 'bg-blue-600 hover:bg-blue-700 text-white'
                        : 'bg-white border-2 border-gray-300 hover:border-blue-400 text-gray-700'
                    }`}
                  >
                    🔽 Filter Tags {selectedTags.length > 0 ? `(${selectedTags.length} selected)` : ''}
                  </button>
                  {selectedTags.length > 0 && (
                    <button
                      onClick={() => setSelectedTags([])}
                      className="ml-1 px-3 py-2 bg-red-500 hover:bg-red-600 text-white rounded-lg text-sm font-semibold transition-colors shadow-md"
                    >
                      × Clear
                    </button>
                  )}
                  {showTagDropdown && (
                    <div className="absolute top-full left-0 mt-2 w-80 max-h-96 bg-white rounded-lg shadow-2xl border-2 border-blue-500 z-[9999] flex flex-col">
                      <div className="bg-blue-50 p-3 border-b-2 border-blue-300 flex items-center justify-between gap-2">
                        <button onClick={selectAllTags} className="px-3 py-1 bg-green-600 hover:bg-green-700 text-white rounded text-xs font-bold">Select All</button>
                        <button onClick={clearAllTags} className="px-3 py-1 bg-red-600 hover:bg-red-700 text-white rounded text-xs font-bold">Clear All</button>
                        <button onClick={() => setShowTagDropdown(false)} className="px-3 py-1 bg-gray-600 hover:bg-gray-700 text-white rounded text-xs font-bold">Close</button>
                      </div>
                      <div className="p-3 border-b border-gray-200">
                        <input
                          type="text"
                          placeholder="🔍 Search tags..."
                          value={tagSearchFilter}
                          onChange={(e) => setTagSearchFilter(e.target.value)}
                          className="w-full px-3 py-2 border-2 border-gray-300 rounded-lg text-sm focus:border-blue-500"
                        />
                      </div>
                      <div className="overflow-y-auto p-2 flex-1">
                        {filteredTagsForDropdown.length === 0 ? (
                          <div className="text-center py-4 text-gray-500 text-sm">No tags found</div>
                        ) : (
                          filteredTagsForDropdown.map((tag) => (
                            <label key={tag.id} className="flex items-center gap-2 p-2 hover:bg-blue-50 rounded cursor-pointer text-gray-800">
                              <input
                                type="checkbox"
                                checked={selectedTags.includes(tag.id)}
                                onChange={() => toggleTag(tag.id)}
                                className="w-4 h-4 accent-blue-600"
                              />
                              <span className="text-sm">{tag.label}</span>
                            </label>
                          ))
                        )}
                      </div>
                    </div>
                  )}
                </div>
                <div className="text-sm font-semibold text-gray-600 bg-white px-3 py-2 rounded-lg border border-gray-300">
                  {filteredRows.length} of {rows.length} tags
                </div>
              </div>
            </div>

            <div className="px-6 py-4 bg-gray-50 border-b-2 border-gray-200 flex items-center justify-between gap-3 flex-wrap">
              <div className="text-sm font-semibold text-gray-700">
                Showing {filteredRows.length} tags {tagSearchFilter ? `(filtered from ${rows.length})` : ''}
              </div>
              <div className="flex items-center gap-3">
                {/* Download Filtered button — exports only the currently visible rows */}
                {(filteredRows.length < rows.length || selectedTags.length > 0) && (
                  <button
                    type="button"
                    onClick={onDownloadFiltered}
                    disabled={isDownloadingFiltered || filteredRows.length === 0}
                    className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-sm font-semibold transition-colors shadow-md disabled:opacity-50 disabled:cursor-not-allowed"
                    title={`Download Excel with only the ${filteredRows.length} currently visible tags`}
                  >
                    {isDownloadingFiltered ? "⬇️ Downloading..." : `📥 Download Filtered (${filteredRows.length} tags)`}
                  </button>
                )}
              </div>
              <div className="flex items-center gap-3 text-sm">
                <label htmlFor="rows-per-page" className="font-semibold text-gray-700">Rows per page</label>
                <select
                  id="rows-per-page"
                  value={pageSize}
                  onChange={(e) => setPageSize(Number(e.target.value))}
                  className="bg-white border-2 border-gray-300 rounded-lg px-3 py-2 font-semibold text-gray-700 focus:border-blue-500 focus:ring-2 focus:ring-blue-200"
                >
                  <option value={20}>20</option>
                  <option value={50}>50</option>
                  <option value={100}>100</option>
                  <option value={200}>200</option>
                </select>
                <button
                  type="button"
                  onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                  disabled={currentPage <= 1}
                  className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 text-white font-semibold disabled:opacity-50 disabled:cursor-not-allowed disabled:bg-gray-400 transition-colors shadow-md"
                  aria-label="Previous page"
                >
                  ← Prev
                </button>
                <span className="font-bold text-gray-800 bg-white px-4 py-2 rounded-lg border-2 border-gray-300">Page {totalPages ? currentPage : 0} / {totalPages}</span>
                <button
                  type="button"
                  onClick={() => setCurrentPage((p) => Math.min(Math.max(totalPages, 1), p + 1))}
                  disabled={totalPages === 0 || currentPage >= totalPages}
                  className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 text-white font-semibold disabled:opacity-50 disabled:cursor-not-allowed disabled:bg-gray-400 transition-colors shadow-md"
                  aria-label="Next page"
                >
                  Next →
                </button>
              </div>
            </div>

            <div className="px-4 py-2 border-b border-slate-700 flex items-center gap-3 bg-slate-800/60">
              <span className="text-xs text-slate-300">Horizontal Scroll</span>
              <button
                type="button"
                onClick={scrollDataLeft}
                className="px-2 py-1 rounded bg-slate-700 hover:bg-slate-600 text-xs"
                aria-label="Scroll table left"
              >
                ←
              </button>
              <button
                type="button"
                onClick={scrollDataRight}
                className="px-2 py-1 rounded bg-slate-700 hover:bg-slate-600 text-xs"
                aria-label="Scroll table right"
              >
                →
              </button>
              <div ref={topScrollRef} className="flex-1 h-4 overflow-x-scroll overflow-y-hidden rounded bg-slate-900 border border-slate-600">
                <div style={{ width: tableScrollWidth, height: 12 }} />
              </div>
            </div>

            <div ref={bottomScrollRef} className="overflow-x-auto">
              <table ref={tableRef} className="min-w-full text-sm">
                <thead className="bg-gradient-to-r from-blue-900 to-blue-800 sticky top-0 shadow-lg">
                  <tr>
                    <th className="p-3 border-2 border-blue-700 text-white font-bold">S.No</th>
                    <th className="p-3 border-2 border-blue-700 text-white font-bold">Equipment</th>
                    <th className="p-3 border-2 border-blue-700 text-white font-bold">Sub Equipment</th>
                    <th className="p-3 border-2 border-blue-700 text-white font-bold">
                      Tag Name
                      {selectedTags.length > 0 && (
                        <span className="ml-2 bg-amber-400 text-blue-900 text-xs font-bold px-2 py-0.5 rounded-full">{selectedTags.length}</span>
                      )}
                    </th>
                    <th className="p-3 border-2 border-blue-700 text-white font-bold">Tag Description</th>
                    <th className="p-3 border-2 border-blue-700 text-white font-bold">Unit</th>
                    <th className="p-3 border-2 border-blue-700 text-white font-bold">Avg</th>
                    <th className="p-3 border-2 border-blue-700 text-white font-bold">Min</th>
                    <th className="p-3 border-2 border-blue-700 text-white font-bold">Max</th>
                    {reportQuery.data.columns.map((col) => (
                      <th key={col} className="p-3 border-2 border-blue-700 whitespace-nowrap text-white font-bold">{col}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {filteredRows.map((row, rowIdx) => (
                    <tr key={`${row.s_no}-${row.tag_id}`} className={`${rowIdx % 2 === 0 ? 'bg-blue-50' : 'bg-white'} hover:bg-amber-50 transition-colors`}>
                      <td className="p-3 border border-gray-300 text-center font-semibold text-gray-800">{row.s_no}</td>
                      <td className="p-3 border border-gray-300 text-gray-800">{row.group}</td>
                      <td className="p-3 border border-gray-300 text-gray-800">{row.sub_equipment || "-"}</td>
                      <td className="p-3 border border-gray-300 font-semibold text-gray-900">{row.tag_id}</td>
                      <td className="p-3 border border-gray-300 text-gray-800">{row.description || row.display_label || row.tag_id}</td>
                      <td className="p-3 border border-gray-300 text-gray-800">{row.eng_unit || "-"}</td>
                      <td className="p-3 border border-gray-300 text-right font-bold text-blue-900">{row.avg ?? "-"}</td>
                      <td className="p-3 border border-gray-300 text-right font-bold text-red-700">{row.min ?? "-"}</td>
                      <td className="p-3 border border-gray-300 text-right font-bold text-green-700">{row.max ?? "-"}</td>
                      {row.hourly.map((v, idx) => (
                        <td key={idx} className="p-3 border border-gray-300 text-right text-gray-800 font-medium">{v ?? "-"}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default DailyReport;
