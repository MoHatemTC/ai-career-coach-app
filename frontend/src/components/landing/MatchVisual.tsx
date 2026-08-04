/**
 * The signature element, and the landing hero.
 *
 * Sprints already built this idiom: their "Leave With Proof" section pairs a
 * pentagon radar with labelled bars and a percentage per row, scoring five
 * capability dimensions. That is structurally our problem too, so reusing the
 * pairing makes the product read as native rather than borrowed.
 *
 * Static sample data on purpose. The hero must render before any backend call,
 * and a hero that depends on the pipeline is a hero that shows a spinner to a
 * first-time visitor.
 */
const DIMENSIONS = [
  { label: "Skills", value: 0.9 },
  { label: "Seniority", value: 0.82 },
  { label: "Domain", value: 0.88 },
  { label: "Tools", value: 0.85 },
  { label: "Growth", value: 0.78 },
] as const;

const SIZE = 240;
const CENTRE = SIZE / 2;
const RADIUS = 88;

function point(index: number, total: number, scale: number) {
  // Start at twelve o'clock rather than three, so the shape reads upright.
  const angle = (Math.PI * 2 * index) / total - Math.PI / 2;
  return {
    x: CENTRE + Math.cos(angle) * RADIUS * scale,
    y: CENTRE + Math.sin(angle) * RADIUS * scale,
  };
}

function polygon(scale: number, values?: readonly number[]) {
  return DIMENSIONS.map((_, index) => {
    const factor = values ? (values[index] ?? 0) : 1;
    const { x, y } = point(index, DIMENSIONS.length, scale * factor);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
}

export function MatchVisual() {
  const values = DIMENSIONS.map((dimension) => dimension.value);

  return (
    <div className="grid gap-8 sm:grid-cols-[auto,1fr] sm:items-center">
      <svg
        viewBox={`0 0 ${SIZE} ${SIZE}`}
        className="mx-auto h-56 w-56 shrink-0"
        role="img"
        aria-label="A radar chart showing fit across five dimensions: skills 90 percent, seniority 82, domain 88, tools 85, growth 78."
      >
        {/* Grid rings, lightest first so the data shape sits on top. */}
        {[0.25, 0.5, 0.75, 1].map((ring) => (
          <polygon
            key={ring}
            points={polygon(ring)}
            fill="none"
            stroke="#E3E8F5"
            strokeWidth="1"
          />
        ))}
        {DIMENSIONS.map((dimension, index) => {
          const { x, y } = point(index, DIMENSIONS.length, 1);
          return (
            <line
              key={dimension.label}
              x1={CENTRE}
              y1={CENTRE}
              x2={x}
              y2={y}
              stroke="#E3E8F5"
              strokeWidth="1"
            />
          );
        })}

        <polygon
          points={polygon(1, values)}
          fill="#1A5FEE"
          fillOpacity="0.16"
          stroke="#1A5FEE"
          strokeWidth="2"
          strokeLinejoin="round"
        />
        {DIMENSIONS.map((dimension, index) => {
          const { x, y } = point(index, DIMENSIONS.length, values[index] ?? 0);
          return <circle key={dimension.label} cx={x} cy={y} r="3.5" fill="#1A5FEE" />;
        })}
      </svg>

      <ul className="space-y-3">
        {DIMENSIONS.map((dimension) => (
          <li key={dimension.label}>
            <div className="flex items-baseline justify-between text-sm">
              <span className="font-medium text-ink">{dimension.label}</span>
              <span className="tabular text-ink-muted">{Math.round(dimension.value * 100)}%</span>
            </div>
            <div className="mt-1 h-1.5 overflow-hidden rounded-chip bg-line">
              <div
                className="h-full rounded-chip bg-brand"
                style={{ width: `${dimension.value * 100}%` }}
              />
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
