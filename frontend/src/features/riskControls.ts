export type RiskParameters = {
  delta_threshold: number;
  max_size: number;
  max_loss: number;
  max_open_positions: number;
};

export type RiskField = keyof RiskParameters;

export type RiskFormValues = Record<RiskField, string>;
export type RiskFormErrors = Partial<Record<RiskField, string>>;

export const RISK_PRESETS: Record<"conservative" | "balanced" | "aggressive", RiskParameters> = {
  conservative: {
    delta_threshold: 0.1,
    max_size: 5,
    max_loss: 2500,
    max_open_positions: 10
  },
  balanced: {
    delta_threshold: 0.2,
    max_size: 10,
    max_loss: 5000,
    max_open_positions: 20
  },
  aggressive: {
    delta_threshold: 0.35,
    max_size: 20,
    max_loss: 10000,
    max_open_positions: 35
  }
};

export function toRiskFormValues(parameters: Partial<RiskParameters> | null | undefined): RiskFormValues {
  const fallback = RISK_PRESETS.balanced;
  return {
    delta_threshold: String(parameters?.delta_threshold ?? fallback.delta_threshold),
    max_size: String(parameters?.max_size ?? fallback.max_size),
    max_loss: String(parameters?.max_loss ?? fallback.max_loss),
    max_open_positions: String(parameters?.max_open_positions ?? fallback.max_open_positions)
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
  max_open_positions: { min: 1, max: 10000, integer: true, label: "Max open positions" }
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

  return {
    parsed: Object.keys(errors).length === 0 ? parsed : null,
    errors
  };
}

