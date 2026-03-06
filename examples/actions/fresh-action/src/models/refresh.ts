export enum CommandArgType {
  NUMBER = 'NUMBER'
}

export enum FlightRuleState {
  PASSED = 'PASSED',
  VIOLATED = 'VIOLATED'
}

export type FlightRule = {
  flight_rule_id: string;
  flight_rule_version: string;
  flight_rule_description: string;
  criticality: string;
  state: FlightRuleState;
  num_violations: number;
  results: FlightRuleResult[];
}

export type FlightRuleResult = {
  state: FlightRuleState;
  step_number: number;
  command_stem: string;
  command_args: {
    name: string;
    value: number;
    type: CommandArgType;
  }[];
  flight_rule_id: string;
  message: string;
}

export type RefreshResponse = {
  metadata: {
    fresh_version: string;
    run_creation_time: string;
  };
  summary: {
    seqId: string;
    rules_checked: number;
    rules_passed: number;
    rules_violated: number;
    rules_flagged: number;
    violation_locations: string[];
  }
  fr_checks: Record<string, FlightRule[]>;
}
