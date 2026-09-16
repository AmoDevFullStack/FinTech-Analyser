/** A 0–100 score as a ring, coloured by band, with the number inside it.
 *
 * docs/decisions.md ADR-011: financial-position quality is deliberately encoded in
 * colour here, which reverses design-system.md §2.3's general rule against it. The
 * reversal is scoped to this one component. Meaning still never rests on colour alone —
 * the number and the band's name are both rendered as text, so the ring reads the same
 * in greyscale or to a screen reader.
 */
export type ScoreBand = "poor" | "fair" | "good";

const BAND_LABEL: Record<ScoreBand, string> = {
  poor: "Needs attention",
  fair: "Fair",
  good: "Strong",
};

const BAND_STROKE: Record<ScoreBand, string> = {
  poor: "stroke-score-poor",
  fair: "stroke-score-fair",
  good: "stroke-score-good",
};

const BAND_TEXT: Record<ScoreBand, string> = {
  poor: "text-score-poor",
  fair: "text-score-fair",
  good: "text-score-good",
};

export function scoreBand(value: number): ScoreBand {
  if (value < 40) return "poor";
  if (value < 70) return "fair";
  return "good";
}

export function ScoreGauge({
  value,
  size = 112,
  strokeWidth = 10,
  label = "Score",
}: {
  value: number;
  size?: number;
  strokeWidth?: number;
  label?: string;
}) {
  const band = scoreBand(value);
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const clamped = Math.min(100, Math.max(0, value));
  const offset = circumference * (1 - clamped / 100);
  const center = size / 2;
  const compact = size < 80;

  return (
    <div
      role="img"
      aria-label={`${label}: ${value} of 100, ${BAND_LABEL[band]}`}
      className="relative inline-flex items-center justify-center"
      style={{ width: size, height: size }}
    >
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden="true">
        <circle
          cx={center}
          cy={center}
          r={radius}
          fill="none"
          strokeWidth={strokeWidth}
          className="stroke-surface-sunken"
        />
        <circle
          cx={center}
          cy={center}
          r={radius}
          fill="none"
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          transform={`rotate(-90 ${center} ${center})`}
          className={`${BAND_STROKE[band]} transition-[stroke-dashoffset] duration-500 ease-out motion-reduce:transition-none`}
        />
      </svg>
      <div className="absolute flex flex-col items-center" aria-hidden="true">
        <span
          className={`tabular-nums text-content ${compact ? "text-label font-medium" : "text-figure-lg"}`}
        >
          {value}
        </span>
        {compact ? null : (
          <span className={`text-caption font-medium ${BAND_TEXT[band]}`}>{BAND_LABEL[band]}</span>
        )}
      </div>
    </div>
  );
}
