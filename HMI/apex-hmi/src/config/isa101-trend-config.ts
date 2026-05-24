/**
 * ISA-101 Compliant Trend Configuration
 * 
 * Based on ISA-101 Human-Machine Interfaces for Process Automation Systems
 * Compatible with Ignition, WinCC, Wonderware, and FactoryTalk standards
 * 
 * References:
 * - ISA-101: Human Machine Interfaces standard
 * - Ignition Easy Chart / Vision Trend component
 * - Siemens WinCC Trend Control
 * - Wonderware InTouch Trend Object
 */

/**
 * ISA-101 Color Palette for Trends
 * 
 * Industry Mapping:
 * - Ignition: Dark theme with high-contrast colors
 * - WinCC: Industrial gray background with vibrant trend colors
 * - Wonderware: Dark backgrounds for 24/7 operator viewing
 */
export const ISA_TREND_COLORS = {
  // Background colors - Dark for reduced eye strain in 24/7 operations
  background: {
    main: '#1a1a1a',          // Main chart background - very dark gray
    grid: '#121212',           // Grid area background
    yAxis: '#0f1419',          // Y-axis panel background
    xAxis: '#0a0a0b',          // X-axis panel background
  },
  
  // Grid lines - Subtle but visible
  grid: {
    major: 'rgba(100, 116, 139, 0.35)',  // Major grid lines - more visible
    minor: 'rgba(71, 85, 105, 0.2)',     // Minor grid lines - subtle
    axis: 'rgba(59, 130, 246, 0.6)',     // Axis border lines
  },
  
  // High-contrast trend line colors (ISA-101 recommended)
  // These colors provide maximum contrast against dark backgrounds
  // and are distinguishable for colorblind operators
  trendLines: [
    '#00FF00',  // Bright Green - Primary trend (PEN 1)
    '#00FFFF',  // Cyan - Secondary trend (PEN 2)
    '#FFFF00',  // Yellow - Tertiary trend (PEN 3)
    '#FF00FF',  // Magenta - Additional (PEN 4)
    '#FF8800',  // Orange - Additional (PEN 5)
    '#00FF88',  // Mint Green - Additional (PEN 6)
    '#FF0088',  // Hot Pink - Additional (PEN 7)
    '#88FF00',  // Lime - Additional (PEN 8)
  ],
  
  // Limit lines - Clearly distinguishable from trend data
  limits: {
    high: '#FF4444',          // High limit - red
    low: '#44AAFF',           // Low limit - blue
    setpoint: '#FFD700',      // Setpoint - gold
  },
  
  // Text and labels - High readability
  text: {
    primary: '#E5E5E5',       // Main text - light gray
    secondary: '#60a5fa',     // Axis labels - blue
    highlight: '#00FF00',     // Highlighted values - green
    disabled: '#666666',      // Disabled text - dark gray
  },
  
  // Data point markers
  markers: {
    fill: '#FFFFFF',          // Marker fill
    stroke: '#000000',        // Marker stroke for contrast
    highlight: '#FFFF00',     // Highlighted marker - yellow
  },
};

/**
 * Typography Settings - ISA-101 compliant
 * 
 * Industry Standard Fonts:
 * - Ignition: Arial, Tahoma, Verdana
 * - WinCC: Arial, Segoe UI
 * - Wonderware: Arial, MS Sans Serif
 * 
 * Recommended: Monospace fonts for numerical values (better alignment)
 */
export const ISA_TREND_TYPOGRAPHY = {
  // Font families (in order of preference)
  fontFamily: {
    primary: 'Arial, "Segoe UI", Tahoma, sans-serif',           // General text
    numeric: 'Consolas, "Courier New", monospace',              // Numbers and data
    legend: 'Arial, "Segoe UI", Tahoma, sans-serif',            // Legend text
  },
  
  // Font sizes (in pixels)
  fontSize: {
    title: 16,              // Chart title
    axisLabel: 13,          // Y-axis numeric labels
    axisUnit: 12,           // Unit labels
    legend: 13,             // Legend text
    tooltip: 12,            // Tooltip text
    annotation: 11,         // Annotation text
  },
  
  // Font weights
  fontWeight: {
    normal: 400,
    bold: 700,
    values: 700,            // For numeric values (better readability)
  },
};

/**
 * Line and Stroke Settings - ISA-101 compliant
 * 
 * Industry Mapping:
 * - Ignition: Line width 2-3px for easy visibility
 * - WinCC: Line width 2px default, up to 5px for critical parameters
 * - Wonderware: Line width 2-4px
 */
export const ISA_TREND_STROKES = {
  // Trend line widths (in pixels)
  trendLine: {
    normal: 2.5,            // Normal trend line - clearly visible
    highlighted: 3.5,       // Selected/highlighted trend
    critical: 4,            // Critical parameter (alarm state)
  },
  
  // Grid line widths
  grid: {
    major: 1.5,             // Major grid lines
    minor: 0.8,             // Minor grid lines
    axis: 2,                // Axis border
  },
  
  // Reference line widths
  reference: {
    limit: 2,               // Limit lines (high/low)
    setpoint: 2,            // Setpoint line
    cursor: 1,              // Cursor crosshair
  },
  
  // Data point marker sizes
  marker: {
    radius: 4,              // Normal marker radius
    radiusHighlight: 6,     // Highlighted marker radius
    strokeWidth: 1.5,       // Marker outline width
    recentRadius: 5,        // Recent data points (last 5)
  },
  
  // Line rendering properties
  rendering: {
    antiAlias: true,        // Enable anti-aliasing for smooth lines
    lineCap: 'round',       // Round line caps (smoother appearance)
    lineJoin: 'round',      // Round line joins (no sharp corners)
    tension: 0.3,           // Curve tension (0 = straight, 1 = very curved)
  },
};

/**
 * Time Axis Configuration - ISA-101 compliant
 * 
 * Requirements:
 * - Uniform sampling intervals
 * - Clear time labels
 * - Proper date/time formatting
 * - Consistent timezone display
 */
export const ISA_TREND_TIME_AXIS = {
  // Time format options
  format: {
    live: 'HH:mm:ss',                           // Live data: 14:35:22
    liveWithMs: 'HH:mm:ss.SSS',                 // With milliseconds: 14:35:22.456
    historical: 'MMM DD, HH:mm',                // Historical: Jan 15, 14:35
    historicalShort: 'HH:mm',                   // Short: 14:35
    tooltip: 'MMM DD, YYYY HH:mm:ss',          // Full: Jan 15, 2024 14:35:22
  },
  
  // Sampling intervals (in milliseconds)
  sampling: {
    fast: 1000,             // 1 second - fast changing values
    normal: 2000,           // 2 seconds - normal process variables
    slow: 5000,             // 5 seconds - slow changing values
  },
  
  // Time ranges (in minutes)
  ranges: {
    realtime: [5, 10, 15, 30, 60],                    // Real-time view
    historical: [60, 120, 240, 480, 1440],            // Historical view (1h to 24h)
  },
  
  // Data point limits
  dataPoints: {
    minimum: 10,            // Minimum points to display
    optimum: 50,            // Optimum for smooth curves
    maximum: 200,           // Maximum to prevent performance issues
  },
  
  // Grid subdivisions
  grid: {
    majorDivisions: 10,     // Major time divisions
    minorDivisions: 5,      // Minor subdivisions per major
  },
};

/**
 * Units Display Configuration
 * 
 * ISA-101 Requirement: Engineering units MUST be displayed
 * Common mistake: Missing or unclear units
 */
export const ISA_TREND_UNITS = {
  // Unit display format
  format: {
    yAxis: '[{unit}]',              // Y-axis: [RPM], [°C], [bar]
    legend: '{tag} ({unit})',       // Legend: Motor Speed (RPM)
    tooltip: '{value} {unit}',      // Tooltip: 1485 RPM
  },
  
  // Unit positioning
  position: {
    yAxis: 'top',                   // Position on Y-axis (top/middle/bottom)
    legend: 'right',                // Legend position
  },
  
  // Common engineering units (for validation)
  common: [
    'RPM', 'Hz',                    // Speed
    '°C', '°F', 'K',                // Temperature
    'bar', 'psi', 'kPa', 'MPa',     // Pressure
    'm³/h', 'L/min', 'GPM',         // Flow
    '%', 'mm', 'cm', 'm',           // Level
    'A', 'V', 'W', 'kW',            // Electrical
    'mm/s', 'g',                     // Vibration
  ],
};

/**
 * Marker Configuration - Data Point Visualization
 * 
 * ISA-101: Markers useful for:
 * - Slow-changing values (clear data point visibility)
 * - Troubleshooting (identifying exact sample times)
 * - Data quality verification (missing points visible)
 */
export const ISA_TREND_MARKERS = {
  // Marker display settings
  enabled: true,                    // Show markers by default
  showOnHover: false,               // Always show (not just on hover)
  
  // Marker shapes (SVG paths)
  shapes: {
    circle: 'circle',               // Standard circular marker
    square: 'square',               // Square marker
    diamond: 'diamond',             // Diamond marker
    triangle: 'triangle',           // Triangle marker
  },
  
  // Marker styling
  style: {
    default: 'circle',              // Default shape
    opacity: 0.9,                   // Marker opacity
    hollowRatio: 0.6,               // Hollow center (0 = solid, 1 = ring)
  },
  
  // Highlighting
  highlight: {
    recent: true,                   // Highlight recent points
    recentCount: 5,                 // Number of recent points to highlight
    currentPulse: true,             // Pulse animation on most recent point
  },
};

/**
 * Statistical Overlay Configuration
 * 
 * Optional: Display min/max/avg during selected time range
 */
export const ISA_TREND_STATISTICS = {
  enabled: false,                   // Toggle statistics overlay
  display: ['min', 'max', 'avg', 'stdDev'],  // Statistics to show
  position: 'top-right',            // Position on chart
  format: {
    min: 'Min: {value} {unit}',
    max: 'Max: {value} {unit}',
    avg: 'Avg: {value} {unit}',
    stdDev: 'σ: {value} {unit}',
  },
};

/**
 * INDUSTRY MAPPING GUIDE
 * 
 * Ignition (Inductive Automation)
 * --------------------------------
 * Component: Easy Chart / Vision Trend
 * Background: Chart Background → ISA_TREND_COLORS.background.main (#1a1a1a)
 * Grid: Major Grid Lines → ISA_TREND_COLORS.grid.major
 * Pen 1 Color: Bright Green (#00FF00)
 * Pen Width: 2-3px → ISA_TREND_STROKES.trendLine.normal (2.5px)
 * Time Format: HH:mm:ss → ISA_TREND_TIME_AXIS.format.live
 * Font: Arial, 13pt → ISA_TREND_TYPOGRAPHY
 * 
 * WinCC (Siemens)
 * ---------------
 * Component: WinCC Trend Control / TrendView
 * Background Color: RGB(26,26,26) → ISA_TREND_COLORS.background.main
 * Curve Color 1: RGB(0,255,0) → Green
 * Line Width: 2px → ISA_TREND_STROKES.trendLine.normal
 * Grid Style: Major/Minor → ISA_TREND_COLORS.grid
 * Font: Segoe UI, 13pt
 * Marker Style: Circle, 4px → ISA_TREND_MARKERS
 * 
 * Wonderware (AVEVA)
 * ------------------
 * Component: Trend Object / InTouch Trend
 * Background: Black/Dark Gray → ISA_TREND_COLORS.background.main
 * Pen 1: Bright Green → #00FF00
 * Pen Width: 2-3px
 * Grid: Major Grid → ISA_TREND_COLORS.grid.major
 * Font: Arial, Regular
 * Time Format: HH:mm:ss
 * 
 * FactoryTalk (Rockwell)
 * ----------------------
 * Component: Trend Object
 * Background: Dark Gray → ISA_TREND_COLORS.background.main
 * Pen Color: High contrast colors
 * Line Width: 2-4px
 * Grid: Enabled with major/minor
 * Marker: Optional, circle
 * 
 * COMMON SETTINGS ACROSS ALL PLATFORMS:
 * - Dark background for 24/7 operator visibility
 * - High-contrast trend colors (Green, Cyan, Yellow)
 * - Line width: 2-3px for clear visibility
 * - Grid: Major + Minor for easy value reading
 * - Units ALWAYS displayed on Y-axis
 * - Time format: HH:mm:ss for live, date included for historical
 * - Anti-aliased lines for smooth appearance
 * - Markers optional but recommended for slow variables
 */

/**
 * Performance and Quality Settings
 */
export const ISA_TREND_PERFORMANCE = {
  // Rendering optimization
  useCanvas: false,                 // Use SVG for crisp lines (Canvas for >500 points)
  downsample: true,                 // Downsample when points > maximum
  antiAlias: true,                  // Anti-aliasing for smooth lines
  
  // Animation
  animate: {
    enabled: true,                  // Smooth transitions
    duration: 300,                  // Transition duration (ms)
  },
  
  // Update behavior
  liveUpdate: {
    enabled: true,                  // Auto-update for live data
    interval: 2000,                 // Update interval (ms)
    smoothTransition: true,         // Smooth data point addition
  },
};

/**
 * Maximum Selected Tags Configuration
 * 
 * Industry Standard: Limit concurrent trend displays to prevent:
 * - Visual clutter and operator confusion
 * - Performance degradation from excessive data processing
 * - Cognitive overload (ISA-101 guideline: 3-8 trends max)
 * 
 * Typical Values:
 * - 3-5 tags: Standard for most HMI applications
 * - 8 tags: High-end displays with large screens
 * - 10+ tags: Engineering/diagnostics mode only
 */
export const MAX_SELECTED_TAGS = 10;

/**
 * Export all configurations as a single object
 */
export const ISA_101_TREND_CONFIG = {
  colors: ISA_TREND_COLORS,
  typography: ISA_TREND_TYPOGRAPHY,
  strokes: ISA_TREND_STROKES,
  timeAxis: ISA_TREND_TIME_AXIS,
  units: ISA_TREND_UNITS,
  markers: ISA_TREND_MARKERS,
  statistics: ISA_TREND_STATISTICS,
  performance: ISA_TREND_PERFORMANCE,
  maxSelectedTags: MAX_SELECTED_TAGS,
};

export default ISA_101_TREND_CONFIG;
