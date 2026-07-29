# SOP: Data Visualization & Plotting

Use this procedure when the query asks to plot, chart, graph, visualize, or show a graphic layout of the analysis.

## Guidelines:
1. **Choose the Right Visual**:
   - *Line Chart*: Show trends over time.
   - *Bar Chart*: Compare quantities across categories.
   - *Scatter Plot*: Expose relationship/correlation between two numeric variables.
   - *Box Plot / Histogram*: Show distributions and outliers.
2. **Professional Styling (CSS/Aesthetics equivalent in Python)**:
   - Always set a neat style (e.g., `plt.style.use('seaborn-v0_8-whitegrid')` if available, or set custom colors).
   - Use soft, premium hex color palettes (e.g., `#2b5c8f` for primary elements, `#f28e2b` for secondary accents). Avoid default harsh primaries (red, blue, green).
   - Set a distinct figure size (e.g., `figsize=(10, 6)`) to ensure high resolution and readability.
   - Always label the X and Y axes, provide a descriptive title, and add a legend if plotting multiple series.
   - Run `plt.tight_layout()` before saving to prevent label clipping.
3. **Output Operations**:
   - Save figures directly to `outputs/` using `plt.savefig()` with high DPI (e.g., `dpi=150`).
   - Clearly log the output path to STDOUT (e.g., `Chart saved to outputs/chart_name.png`) so the user/agent can reference the visual artifact.
