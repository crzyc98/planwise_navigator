import { useEffect, useMemo, useState } from 'react';
import { ChevronDown, ChevronRight, Loader2, Play } from 'lucide-react';
import {
  FitHistorySet,
  ParamFitJob,
  ParamFitOptions,
  ParamFitThresholds,
  Scenario,
  startParamFit,
} from '../../services/api';
import {
  DEFAULT_FIT_OPTIONS,
  DEFAULT_SEEDS,
  DEFAULT_THRESHOLDS,
  FIT_OPTION_LABELS,
  FitMode,
  movedSettings,
  preRunSummary,
  splitFor,
} from './paramFitHelpers';
import { errorText } from './paramFitUi';

interface ConfigureStepProps {
  readonly workspaceId: string;
  readonly history: FitHistorySet | null;
  readonly scenarios: Scenario[];
  readonly backtestRunning: boolean;
  readonly onLaunched: (job: ParamFitJob) => void;
}

const inputClass =
  'w-full rounded-md border border-border-strong bg-surface-raised p-2 text-sm text-ink shadow-sm focus:border-fidelity-green focus:ring-fidelity-green';

function parseSeeds(raw: string): number[] | null {
  const parts = raw.split(',').map((part) => part.trim()).filter(Boolean);
  const seeds = parts.map(Number);
  const valid = seeds.length >= 1 && seeds.length <= 5 && seeds.every(Number.isInteger) && new Set(seeds).size === seeds.length;
  return valid ? seeds : null;
}

export function ConfigureStep({ workspaceId, history, scenarios, backtestRunning, onLaunched }: ConfigureStepProps) {
  const [scenarioId, setScenarioId] = useState(scenarios[0]?.id ?? '');
  const [mode, setMode] = useState<FitMode>('fit');
  const [holdoutYears, setHoldoutYears] = useState(1);
  const [seedText, setSeedText] = useState(DEFAULT_SEEDS.join(', '));
  const [options, setOptions] = useState<Required<ParamFitOptions>>(DEFAULT_FIT_OPTIONS);
  const [thresholds, setThresholds] = useState<Required<ParamFitThresholds>>(DEFAULT_THRESHOLDS);
  const [notes, setNotes] = useState('');
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [launching, setLaunching] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!scenarios.some((scenario) => scenario.id === scenarioId)) setScenarioId(scenarios[0]?.id ?? '');
  }, [scenarios, scenarioId]);

  const seeds = parseSeeds(seedText);
  const moved = useMemo(() => movedSettings(options, thresholds, mode), [options, thresholds, mode]);
  const split = history && mode === 'backtest' ? splitFor(history, holdoutYears) : null;
  const scenarioName = scenarios.find((scenario) => scenario.id === scenarioId)?.name ?? '';
  const blocker = launchBlocker({ history, scenarioId, mode, splitError: split?.error, seeds, backtestRunning });

  async function launch() {
    if (!history || blocker) return;
    setLaunching(true);
    setError(null);
    try {
      const job = await startParamFit(workspaceId, {
        history_id: history.history_id,
        base_scenario_id: scenarioId,
        mode,
        holdout_years: holdoutYears,
        seeds: seeds ?? DEFAULT_SEEDS,
        thresholds,
        fit_options: options,
        notes,
      });
      onLaunched(job);
    } catch (launchError) {
      setError(errorText(launchError));
    } finally {
      setLaunching(false);
    }
  }

  return (
    <div className="space-y-5">
      <div className="grid gap-4 md:grid-cols-2">
        <label className="block">
          <span className="mb-1 block text-sm font-medium text-ink">Base scenario</span>
          <select value={scenarioId} onChange={(event) => setScenarioId(event.target.value)} className={inputClass}>
            {scenarios.map((scenario) => (
              <option key={scenario.id} value={scenario.id}>
                {scenario.name}
              </option>
            ))}
          </select>
          <span className="mt-1 block text-xs text-ink-muted">
            Its current assumptions are the priors thin cells fall back to.
          </span>
        </label>
        <div>
          <span className="mb-1 block text-sm font-medium text-ink">What to run</span>
          <div className="flex overflow-hidden rounded-md border border-border-strong text-sm">
            {(['fit', 'backtest'] as FitMode[]).map((option) => (
              <button
                key={option}
                type="button"
                onClick={() => setMode(option)}
                className={`flex-1 px-3 py-2 ${mode === option ? 'bg-fidelity-green text-ink-inverse' : 'bg-surface-raised text-ink-muted'}`}
              >
                {option === 'fit' ? 'Fit only' : 'Fit + backtest'}
              </button>
            ))}
          </div>
          <span className="mt-1 block text-xs text-ink-muted">
            A backtest fits on the early years and checks predictions against the held-out years.
          </span>
        </div>
      </div>

      {mode === 'backtest' && (
        <BacktestSettings
          holdoutYears={holdoutYears}
          onHoldout={setHoldoutYears}
          seedText={seedText}
          onSeeds={setSeedText}
          seedsValid={seeds !== null}
          splitError={split?.error ?? null}
        />
      )}

      <button
        type="button"
        onClick={() => setShowAdvanced((value) => !value)}
        className="inline-flex items-center gap-1 text-sm font-medium text-ink-muted hover:text-ink"
      >
        {showAdvanced ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
        Advanced settings
        {moved.length > 0 && <span className="ml-1 rounded bg-warning-surface px-1.5 text-xs text-warning-ink">{moved.length} changed</span>}
      </button>
      {showAdvanced && (
        <AdvancedSettings
          mode={mode}
          options={options}
          onOptions={setOptions}
          thresholds={thresholds}
          onThresholds={setThresholds}
          movedKeys={new Set(moved.map((item) => item.key))}
          notes={notes}
          onNotes={setNotes}
        />
      )}

      {history && (
        <div className="rounded-lg border border-border bg-surface-subtle p-4">
          <h3 className="mb-2 text-sm font-semibold text-ink">Review before running</h3>
          <dl className="grid gap-x-6 gap-y-1 text-sm sm:grid-cols-[max-content_1fr]">
            {preRunSummary({ history, scenarioName, mode, holdoutYears, seeds: seeds ?? [], moved }).map((row) => (
              <div key={row.label} className="contents">
                <dt className="text-ink-muted">{row.label}</dt>
                <dd className={row.emphasis ? 'font-medium text-warning-ink' : 'text-ink'}>{row.value}</dd>
              </div>
            ))}
          </dl>
        </div>
      )}

      {error && <div className="rounded-lg border border-danger-border bg-danger-surface p-3 text-sm text-danger-ink">{error}</div>}

      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={() => void launch()}
          disabled={Boolean(blocker) || launching}
          className="inline-flex items-center gap-2 rounded-lg bg-fidelity-green px-4 py-2 font-medium text-ink-inverse transition-colors hover:bg-fidelity-dark disabled:cursor-not-allowed disabled:bg-surface-disabled"
        >
          {launching ? <Loader2 size={16} className="animate-spin" /> : <Play size={16} />}
          {mode === 'backtest' ? 'Run fit + backtest' : 'Run fit'}
        </button>
        {blocker && <span className="text-sm text-ink-muted">{blocker}</span>}
      </div>
    </div>
  );
}

function launchBlocker(input: {
  history: FitHistorySet | null;
  scenarioId: string;
  mode: FitMode;
  splitError: string | null | undefined;
  seeds: number[] | null;
  backtestRunning: boolean;
}): string | null {
  if (!input.history) return 'Upload or choose a history set first.';
  if (!input.scenarioId) return 'Choose a base scenario.';
  if (input.mode !== 'backtest') return null;
  if (input.splitError) return 'This history cannot support the chosen holdout.';
  if (!input.seeds) return 'Enter 1–5 distinct whole-number seeds.';
  if (input.backtestRunning) return 'A backtest is already running in this workspace.';
  return null;
}

function BacktestSettings(props: {
  holdoutYears: number;
  onHoldout: (value: number) => void;
  seedText: string;
  onSeeds: (value: string) => void;
  seedsValid: boolean;
  splitError: string | null;
}) {
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <label className="block">
        <span className="mb-1 block text-sm font-medium text-ink">Held-out years</span>
        <select value={props.holdoutYears} onChange={(event) => props.onHoldout(Number(event.target.value))} className={inputClass}>
          <option value={1}>1 year</option>
          <option value={2}>2 years</option>
        </select>
        {props.splitError && <span className="mt-1 block text-xs text-danger-ink">{props.splitError}</span>}
      </label>
      <label className="block">
        <span className="mb-1 block text-sm font-medium text-ink">Random seeds</span>
        <input value={props.seedText} onChange={(event) => props.onSeeds(event.target.value)} className={inputClass} />
        <span className={`mt-1 block text-xs ${props.seedsValid ? 'text-ink-muted' : 'text-danger-ink'}`}>
          1–5 distinct seeds, comma-separated. More seeds show how much results vary run to run.
        </span>
      </label>
    </div>
  );
}

function AdvancedSettings(props: {
  mode: FitMode;
  options: Required<ParamFitOptions>;
  onOptions: (value: Required<ParamFitOptions>) => void;
  thresholds: Required<ParamFitThresholds>;
  onThresholds: (value: Required<ParamFitThresholds>) => void;
  movedKeys: Set<string>;
  notes: string;
  onNotes: (value: string) => void;
}) {
  const movedClass = (key: string) => (props.movedKeys.has(key) ? 'border-warning-border bg-warning-surface' : '');
  return (
    <div className="space-y-4 rounded-lg border border-border p-4">
      <div className="grid gap-4 md:grid-cols-2">
        {(Object.keys(FIT_OPTION_LABELS) as (keyof ParamFitOptions)[]).map((key) => (
          <label key={key} className="block">
            <span className="mb-1 block text-sm font-medium text-ink">{FIT_OPTION_LABELS[key]}</span>
            <input
              type="number"
              step="any"
              value={props.options[key]}
              onChange={(event) => props.onOptions({ ...props.options, [key]: Number(event.target.value) })}
              className={`${inputClass} ${movedClass(key)}`}
            />
            <span className="mt-1 block text-xs text-ink-muted">Default {DEFAULT_FIT_OPTIONS[key]}</span>
          </label>
        ))}
      </div>
      {props.mode === 'backtest' && (
        <div>
          <h4 className="mb-2 text-sm font-medium text-ink">Backtest thresholds (warn / fail, as a fraction)</h4>
          <div className="grid gap-3 md:grid-cols-2">
            {(Object.keys(DEFAULT_THRESHOLDS) as (keyof ParamFitThresholds)[]).map((family) => (
              <div key={family} className={`flex items-center gap-2 rounded-md border border-border p-2 ${movedClass(`thresholds.${family}`)}`}>
                <span className="w-28 text-sm capitalize text-ink">{family}</span>
                {(['warn', 'fail'] as const).map((bound) => (
                  <input
                    key={bound}
                    type="number"
                    step="0.01"
                    aria-label={`${family} ${bound}`}
                    value={props.thresholds[family][bound]}
                    onChange={(event) =>
                      props.onThresholds({
                        ...props.thresholds,
                        [family]: { ...props.thresholds[family], [bound]: Number(event.target.value) },
                      })
                    }
                    className="w-24 rounded-md border border-border-strong bg-surface-raised p-1.5 text-sm text-ink"
                  />
                ))}
              </div>
            ))}
          </div>
        </div>
      )}
      <label className="block">
        <span className="mb-1 block text-sm font-medium text-ink">Notes (recorded in the pack)</span>
        <input value={props.notes} maxLength={500} onChange={(event) => props.onNotes(event.target.value)} className={inputClass} />
      </label>
    </div>
  );
}
