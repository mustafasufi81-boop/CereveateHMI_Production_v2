# Predictive UI Design Proposal

## Goal
Make predictive analytics feel like a first-class experience when the user clicks `🔮 ML Predict Missing`.

The predictive view should:
- open cleanly and immediately
- focus on one task at a time
- show the prediction result as the main visual
- keep BI completely separate
- avoid making predictive feel like another BI panel

## Core Processing Model
Predictive logic should be treated as a **Python-first, on-demand analytical service**.

This means the prediction engine should:
- run only after explicit user action
- fetch historian data once as a snapshot
- process the data in Python memory
- return compact results to the UI
- release DB connections, dataframe memory, and worker resources immediately

It should **not** behave like a live historian scanner, continuous poller, or always-on background task.

## Current Behavior
From the current code:
- the button `predictMissingData` in `templates/trends.html` opens the predictive flow
- the UI is handled by `static/modules/predictive_interpolation.js`
- prediction requests use `/api/prediction/*`
- BI uses a separate path (`BIAnalytics`, `/api/v1/analytics/*`, `/api/bi/*`)

So the architecture is already separate. The improvement needed is mostly **UX and presentation**, not backend coupling.

## High-Performance Rules
Predictive processing must stay lightweight and transient.

### Predictive Must
- start only on explicit user request
- run for the requested dataset and date range only
- stop after result generation
- support graceful cancellation when the UI closes or the session becomes inactive
- use timeout guards for fetch and model execution
- cap dataset size and compare-mode model count
- clean up memory and temporary objects immediately

### Predictive Must Not
- run continuously in the background
- keep DB cursors open
- poll the historian endlessly
- auto-refresh without user action
- keep fetching live data after the result is built
- tie itself to the live ingestion stream

## Predictive Session Lifecycle
Add a session manager in Python to track each prediction job.

Recommended job state fields:
- session ID
- user ID
- requested tag
- requested date range
- model name(s)
- cancellation flag
- start time
- timeout deadline
- job status

Recommended lifecycle:
1. user clicks predict
2. backend creates a prediction session
3. historian data is fetched once into a temporary dataframe
4. DB connection closes immediately
5. model runs in memory
6. result is returned
7. resources are released
8. session is removed or marked complete

If the user closes the modal, changes tab, cancels, or disconnects, the backend should cancel the running job gracefully.

## Best Experience on Click
When the user clicks the predictive button, show a **dedicated predictive workspace** instead of a small popup.

### Recommended Layout
Use a full-screen modal or slide-over page with 3 zones:

1. **Top Summary Bar**
   - selected tag
   - date range
   - data points found
   - model status
   - confidence indicator

2. **Main Prediction Panel**
   - large Plotly chart as the primary focus
   - default view should be the selected model result
   - show original data and predicted extension clearly
   - highlight missing sections and filled points

3. **Side Insights Panel**
   - model comparison cards
   - confidence score
   - error metric if available
   - runtime/status
   - save / accept actions

## Recommended Click Flow
1. User clicks `🔮 ML Predict Missing`
2. System opens a predictive workspace immediately
3. Backend creates a transient prediction session
4. User selects:
   - tag
   - date range
   - model mode: single or compare
5. System fetches a historian snapshot once
6. Python model runs on the snapshot in memory
7. Results appear in the main chart first
8. User can compare models side by side
9. User saves the chosen prediction

## What Should Be Shown First
The first thing the user should see after clicking is:
- the selected tag name
- a large prediction chart placeholder or loading chart
- a short status message like `Preparing prediction workspace...`

After the data is ready, the **prediction chart** should appear before model details.

## Visual Rules
Use this order of importance:
- **Primary**: prediction chart
- **Secondary**: model selector and confidence
- **Tertiary**: logs, technical details, raw metadata

Design style suggestions:
- dark industrial theme
- strong accent colors for predicted points
- clear distinction between actual data and predicted values
- minimal clutter
- sticky action bar at the bottom

## Suggested UI Components
### Header
- title: `ML Trend Prediction`
- selected tag
- selected date range
- close button

### Chart Area
- Plotly line chart with actual vs predicted overlay
- optional shaded gap region
- legend with clear labels:
  - `Actual`
  - `Predicted`
  - `Confidence band`

### Model Cards
Show cards for:
- FFT
- ARIMA
- Prophet
- Exponential
- Polynomial
- Random Forest
- Linear

Each card should include:
- model name
- short description
- confidence
- predicted point count
- select button

### Action Buttons
- `Run Prediction`
- `Compare Models`
- `Save Selected Prediction`
- `Close`

## Keep BI Separate
Do not mix BI controls into the predictive view.

BI should remain in:
- `BIAnalytics`
- `bi_analytics.js`
- `advanced_bi_dashboard.js`
- `/api/v1/analytics/*`

Predictive should stay in:
- `PredictiveInterpolation`
- `predictive_interpolation.js`
- `/api/prediction/*`

## Optional Improvement Path
If you want the best user experience, implement predictive as:
- a dedicated modal
- with a large chart first
- and model comparison below it

That makes it feel more like a focused analysis tool and less like a hidden utility.

For Python backend performance, the model runner should prefer:
- preloaded lightweight model objects where possible
- vectorized dataframe operations
- bounded batch sizes
- async job tracking only for the active request
- no live-historian attachment

## Implementation Checklist
- [ ] open a full-screen predictive modal on click
- [ ] show selected tag and date range in the header
- [ ] render the prediction chart first
- [ ] keep model cards below or beside the chart
- [ ] separate actual vs predicted styles clearly
- [ ] keep BI logic untouched
- [ ] make the save action obvious and primary
- [ ] add Python session manager and cancellation support
- [ ] fetch historian data as a one-time snapshot only
- [ ] enforce timeouts and dataset caps
- [ ] release DB and memory resources after completion
- [ ] prevent continuous polling or auto-refresh

## Suggested File Targets
If you later want to implement this UI, the main files are:
- `HistoricalTrends/templates/trends.html`
- `HistoricalTrends/static/modules/predictive_interpolation.js`
- `HistoricalTrends/static/trends.js`

## Summary
The best design is a **dedicated predictive workspace with a large chart-first layout**. That gives the user an obvious, professional flow when they click prediction, while keeping BI fully separate.

The backend should be a **transient, session-scoped Python analytical engine** that works from a snapshot, not from a live stream, so historian stability and database performance stay protected.
 
