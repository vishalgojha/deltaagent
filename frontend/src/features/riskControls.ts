export type RiskParameters = {
  delta_threshold: number;
  max_size: number;
  max_loss: number;
  max_open_positions: number;
  execution_alert_slippage_warn_bps: number;
  execution_alert_slippage_critical_bps: number;
  execution_alert_latency_warn_ms: number;
  execution_alert_latency_critical_ms: number;
  execution_alert_fill_coverage_warn_pct: number;
  execution_alert_fill_coverage_critical_pct: number;
};

export type RiskField = keyof RiskParameters;

export type RiskFormValues = Record<RiskField, string>;
export type RiskFormErrors = Partial<Record<RiskField, string>>;

export const RISK_PRESETS: Record<"conservative" | "balanced" | "aggressive", RiskParameters> = {
  conservative: {
    delta_threshold: 0.1,
    max_size: 5,
    max_loss: 2500,
    max_open_positions: 10,
    execution_alert_slippage_warn_bps: 10,
    execution_alert_slippage_critical_bps: 20,
    execution_alert_latency_warn_ms: 2000,
    execution_alert_latency_critical_ms: 5000,
    execution_alert_fill_coverage_warn_pct: 85,
    execution_alert_fill_coverage_critical_pct: 70
  },
  balanced: {
    delta_threshold: 0.2,
    max_size: 10,
    max_loss: 5000,
    max_open_positions: 20,
    execution_alert_slippage_warn_bps: 15,
    execution_alert_slippage_critical_bps: 30,
    execution_alert_latency_warn_ms: 3000,
    execution_alert_latency_critical_ms: 8000,
    execution_alert_fill_coverage_warn_pct: 75,
    execution_alert_fill_coverage_critical_pct: 50
  },
  aggressive: {
    delta_threshold: 0.35,
    max_size: 20,
    max_loss: 10000,
    max_open_positions: 35,
    execution_alert_slippage_warn_bps: 25,
    execution_alert_slippage_critical_bps: 50,
    execution_alert_latency_warn_ms: 5000,
    execution_alert_latency_critical_ms: 12000,
    execution_alert_fill_coverage_warn_pct: 60,
    execution_alert_fill_coverage_critical_pct: 40
  }
};

export function toRiskFormValues(parameters: Partial<RiskParameters> | null | undefined): RiskFormValues {
  const fallback = RISK_PRESETS.balanced;
  return {
    delta_threshold: String(parameters?.delta_threshold ?? fallback.delta_threshold),
    max_size: String(parameters?.max_size ?? fallback.max_size),
    max_loss: String(parameters?.max_loss ?? fallback.max_loss),
    max_open_positions: String(parameters?.max_open_positions ?? fallback.max_open_positions),
    execution_alert_slippage_warn_bps: String(
      parameters?.execution_alert_slippage_warn_bps ?? fallback.execution_alert_slippage_warn_bps
    ),
    execution_alert_slippage_critical_bps: String(
      parameters?.execution_alert_slippage_critical_bps ?? fallback.execution_alert_slippage_critical_bps
    ),
    execution_alert_latency_warn_ms: String(
      parameters?.execution_alert_latency_warn_ms ?? fallback.execution_alert_latency_warn_ms
    ),
    execution_alert_latency_critical_ms: String(
      parameters?.execution_alert_latency_critical_ms ?? fallback.execution_alert_latency_critical_ms
    ),
    execution_alert_fill_coverage_warn_pct: String(
      parameters?.execution_alert_fill_coverage_warn_pct ?? fallback.execution_alert_fill_coverage_warn_pct
    ),
    execution_alert_fill_coverage_critical_pct: String(
      parameters?.execution_alert_fill_coverage_critical_pct ?? fallback.execution_alert_fill_coverage_critical_pct
    )
  };
}

type ValidationRule = {
  min: number;
  max: number;
  integer?: boolean;
  label: string;
};

const VALIDATION_RULES: Record<RiskField, ValidationRule> = {
  delta_threshold: { min: 0.01, max: 5, label: "Delta threshold" },
  max_size: { min: 1, max: 100000, integer: true, label: "Max size" },
  max_loss: { min: 1, max: 100000000, label: "Max loss" },
  max_open_positions: { min: 1, max: 10000, integer: true, label: "Max open positions" },
  execution_alert_slippage_warn_bps: { min: 1, max: 10000, label: "Slippage warning threshold" },
  execution_alert_slippage_critical_bps: { min: 1, max: 10000, label: "Slippage critical threshold" },
  execution_alert_latency_warn_ms: { min: 100, max: 600000, integer: true, label: "Latency warning threshold" },
  execution_alert_latency_critical_ms: {
    min: 100,
    max: 600000,
    integer: true,
    label: "Latency critical threshold"
  },
  execution_alert_fill_coverage_warn_pct: {
    min: 1,
    max: 100,
    label: "Fill coverage warning threshold"
  },
  execution_alert_fill_coverage_critical_pct: {
    min: 1,
    max: 100,
    label: "Fill coverage critical threshold"
  }
};

export function validateRiskValues(values: RiskFormValues): { parsed: RiskParameters | null; errors: RiskFormErrors } {
  const errors: RiskFormErrors = {};
  const parsed = {} as RiskParameters;

  (Object.keys(VALIDATION_RULES) as RiskField[]).forEach((field) => {
    const raw = values[field].trim();
    const rule = VALIDATION_RULES[field];
    if (!raw) {
      errors[field] = `${rule.label} is required`;
      return;
    }

    const numeric = Number(raw);
    if (!Number.isFinite(numeric)) {
      errors[field] = `${rule.label} must be a valid number`;
      return;
    }

    if (rule.integer && !Number.isInteger(numeric)) {
      errors[field] = `${rule.label} must be an integer`;
      return;
    }

    if (numeric < rule.min || numeric > rule.max) {
      errors[field] = `${rule.label} must be between ${rule.min} and ${rule.max}`;
      return;
    }

    parsed[field] = numeric;
  });

  if (Object.keys(errors).length === 0) {
    if (parsed.execution_alert_slippage_critical_bps < parsed.execution_alert_slippage_warn_bps) {
      errors.execution_alert_slippage_critical_bps =
        "Slippage critical threshold must be greater than or equal to warning threshold";
    }
    if (parsed.execution_alert_latency_critical_ms < parsed.execution_alert_latency_warn_ms) {
      errors.execution_alert_latency_critical_ms =
        "Latency critical threshold must be greater than or equal to warning threshold";
    }
    if (parsed.execution_alert_fill_coverage_warn_pct < parsed.execution_alert_fill_coverage_critical_pct) {
      errors.execution_alert_fill_coverage_warn_pct =
        "Fill coverage warning threshold must be greater than or equal to critical threshold";
    }
  }

  return {
    parsed: Object.keys(errors).length === 0 ? parsed : null,
    errors
  };
}

