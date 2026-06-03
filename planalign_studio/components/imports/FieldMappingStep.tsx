import React, { useEffect, useState } from 'react';
import { ChevronDown, ChevronUp, AlertCircle, Loader2, Info } from 'lucide-react';
import {
  ImportSession,
  FieldMapping,
  Transformation,
  OutputType,
  TransformType,
  MappingValidationError,
  CensusField,
  ColumnSuggestion,
  FormatDetectionResult,
  SuggestionsResponse,
  getSuggestions,
  saveMapping,
} from '../../services/importService';

const TRANSFORM_TYPES: { value: TransformType; label: string }[] = [
  { value: 'string_case', label: 'Change Case' },
  { value: 'date_parse', label: 'Parse Date' },
  { value: 'null_replace', label: 'Replace Nulls' },
  { value: 'null_drop', label: 'Drop Null Rows' },
  { value: 'calculated_field', label: 'Calculated Field' },
];

function ConfidenceBadge({ confidence }: { confidence: 'high' | 'medium' | 'low' | null }) {
  if (!confidence || confidence === 'low') {
    return <span className="text-xs px-1.5 py-0.5 rounded bg-gray-100 text-gray-500">Low</span>;
  }
  if (confidence === 'medium') {
    return <span className="text-xs px-1.5 py-0.5 rounded bg-amber-100 text-amber-700">Medium</span>;
  }
  return <span className="text-xs px-1.5 py-0.5 rounded bg-green-100 text-green-700">High</span>;
}

function FormatPanel({ detection }: { detection: FormatDetectionResult }) {
  const [chosenFormat, setChosenFormat] = useState<string | null>(
    detection.is_ambiguous ? null : detection.detected_format
  );

  if (detection.detected_format === 'boolean_alias') {
    return (
      <div className="mt-1 text-xs text-gray-500 bg-gray-50 rounded px-2 py-1.5 flex items-center gap-1.5">
        <Info size={12} className="shrink-0 text-blue-400" />
        <span>Boolean detected: {detection.parsed_sample_values[0]}</span>
      </div>
    );
  }

  if (detection.detected_format === 'currency_string') {
    return (
      <div className="mt-1 text-xs text-gray-500 bg-gray-50 rounded px-2 py-1.5 flex items-center gap-1.5">
        <Info size={12} className="shrink-0 text-blue-400" />
        <span>
          Currency symbols and commas will be stripped automatically.
          Samples: {detection.parsed_sample_values.join(', ')}
        </span>
      </div>
    );
  }

  if (detection.is_ambiguous && detection.format_options) {
    return (
      <div className="mt-1 text-xs bg-amber-50 border border-amber-200 rounded px-2 py-1.5 space-y-1">
        <div className="flex items-center gap-1 text-amber-700 font-medium">
          <AlertCircle size={12} />
          <span>Ambiguous date format — please confirm:</span>
        </div>
        <div className="flex gap-3">
          {detection.format_options.map((fmt) => (
            <label key={fmt} className="flex items-center gap-1 cursor-pointer">
              <input
                type="radio"
                name={`fmt-${fmt}`}
                value={fmt}
                checked={chosenFormat === fmt}
                onChange={() => setChosenFormat(fmt)}
                className="accent-fidelity-green"
              />
              <span className="font-mono">{fmt}</span>
            </label>
          ))}
        </div>
      </div>
    );
  }

  if (detection.detected_format) {
    return (
      <div className="mt-1 text-xs text-gray-500 bg-gray-50 rounded px-2 py-1.5 flex items-center gap-1.5">
        <Info size={12} className="shrink-0 text-blue-400" />
        <span>
          Detected format: <span className="font-mono">{detection.detected_format}</span>
          {detection.parsed_sample_values.length > 0 && (
            <> — samples: {detection.parsed_sample_values.slice(0, 3).join(', ')}</>
          )}
        </span>
      </div>
    );
  }

  return null;
}

function TransformParams({ type, params, onChange }: {
  type: TransformType;
  params: Record<string, unknown>;
  onChange: (params: Record<string, unknown>) => void;
}) {
  if (type === 'string_case') {
    return (
      <select
        className="text-xs border border-gray-200 rounded px-2 py-1"
        value={(params.case as string) || 'lower'}
        onChange={(e) => onChange({ case: e.target.value })}
      >
        <option value="upper">UPPERCASE</option>
        <option value="lower">lowercase</option>
        <option value="title">Title Case</option>
      </select>
    );
  }
  if (type === 'date_parse') {
    return (
      <input
        type="text"
        placeholder="%m/%d/%Y"
        className="text-xs border border-gray-200 rounded px-2 py-1 w-32"
        value={(params.format as string) || ''}
        onChange={(e) => onChange({ format: e.target.value })}
      />
    );
  }
  if (type === 'null_replace') {
    return (
      <input
        type="text"
        placeholder="replacement value"
        className="text-xs border border-gray-200 rounded px-2 py-1 w-32"
        value={(params.value as string) ?? ''}
        onChange={(e) => onChange({ value: e.target.value })}
      />
    );
  }
  if (type === 'calculated_field') {
    return (
      <input
        type="text"
        placeholder="e.g. COL_A + ' ' + COL_B"
        className="text-xs border border-gray-200 rounded px-2 py-1 w-48"
        value={(params.expression as string) || ''}
        onChange={(e) => onChange({ expression: e.target.value })}
      />
    );
  }
  return null;
}

interface Props {
  workspaceId: string;
  session: ImportSession;
  onSaved: (mappings: FieldMapping[], suggestionsData: SuggestionsResponse | null) => void;
}

function buildInitialMappings(
  session: ImportSession,
  suggestions: ColumnSuggestion[],
  canonicalSchema: CensusField[],
): FieldMapping[] {
  const suggestionMap = new Map(suggestions.map((s) => [s.input_column, s]));
  const schemaTypeMap = new Map(canonicalSchema.map((f) => [f.field_name, f.data_type]));

  return session.detected_columns.map((col) => {
    const suggestion = suggestionMap.get(col.name);
    const canonicalField = suggestion?.suggested_canonical_field ?? '';
    const isHighOrMedium = suggestion?.confidence === 'high' || suggestion?.confidence === 'medium';

    // Determine output_type from canonical schema, or infer from detected type
    let outputType: OutputType = 'string';
    if (canonicalField && isHighOrMedium) {
      const dt = schemaTypeMap.get(canonicalField);
      if (dt === 'date') outputType = 'date';
      else if (dt === 'decimal') outputType = 'decimal';
      else if (dt === 'boolean') outputType = 'boolean';
      else if (dt === 'string') outputType = 'string';
    } else if (col.inferred_type !== 'unknown') {
      outputType = col.inferred_type as OutputType;
    }

    // Auto-inject date_parse transform when format is detected
    const transforms: Transformation[] = [];
    const fmt = suggestion?.format_detection?.detected_format;
    if (fmt && fmt !== 'currency_string' && fmt !== 'boolean_alias' && !suggestion?.format_detection?.is_ambiguous) {
      transforms.push({ transform_type: 'date_parse', params: { format: fmt } });
    }

    return {
      input_column: col.name,
      output_column: isHighOrMedium ? canonicalField : '',
      output_type: outputType,
      is_required: false,
      is_excluded: false,
      transformations: transforms,
    };
  });
}

export default function FieldMappingStep({ workspaceId, session, onSaved }: Props) {
  const [isLoadingSuggestions, setIsLoadingSuggestions] = useState(true);
  const [suggestionsData, setSuggestionsData] = useState<SuggestionsResponse | null>(null);
  const [mappings, setMappings] = useState<FieldMapping[]>(() =>
    session.detected_columns.map((col) => ({
      input_column: col.name,
      output_column: '',
      output_type: 'string' as OutputType,
      is_required: false,
      is_excluded: false,
      transformations: [],
    }))
  );
  const [validationErrors, setValidationErrors] = useState<MappingValidationError[]>([]);
  const [requiredFieldErrors, setRequiredFieldErrors] = useState<CensusField[]>([]);
  const [isSaving, setIsSaving] = useState(false);
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set());

  useEffect(() => {
    getSuggestions(workspaceId, session.import_id)
      .then((data) => {
        setSuggestionsData(data);
        setMappings(buildInitialMappings(session, data.suggestions, data.canonical_schema));
      })
      .catch(() => {
        // Fall back to empty mappings if suggestions fail — mapping still usable
      })
      .finally(() => setIsLoadingSuggestions(false));
  }, [workspaceId, session.import_id]);

  const canonicalSchema = suggestionsData?.canonical_schema ?? [];
  const suggestions = suggestionsData?.suggestions ?? [];
  const suggestionMap = new Map(suggestions.map((s) => [s.input_column, s]));

  const requiredFields = canonicalSchema.filter((f) => f.required);

  const updateMapping = (idx: number, patch: Partial<FieldMapping>) => {
    setMappings((prev) => prev.map((m, i) => i === idx ? { ...m, ...patch } : m));
  };

  const toggleExpand = (col: string) => {
    setExpandedRows((prev) => {
      const next = new Set(prev);
      if (next.has(col)) next.delete(col); else next.add(col);
      return next;
    });
  };

  const addTransform = (idx: number) => {
    updateMapping(idx, {
      transformations: [...(mappings[idx].transformations), { transform_type: 'string_case', params: { case: 'lower' } }],
    });
  };

  const removeTransform = (mappingIdx: number, tIdx: number) => {
    updateMapping(mappingIdx, {
      transformations: mappings[mappingIdx].transformations.filter((_, i) => i !== tIdx),
    });
  };

  const updateTransform = (mappingIdx: number, tIdx: number, patch: Partial<Transformation>) => {
    const updated = mappings[mappingIdx].transformations.map((t, i) => i === tIdx ? { ...t, ...patch } : t);
    updateMapping(mappingIdx, { transformations: updated });
  };

  const handleSave = async () => {
    // Client-side required field check
    const mappedOutputs = new Set(
      mappings.filter((m) => !m.is_excluded && m.output_column).map((m) => m.output_column)
    );
    const unmapped = requiredFields.filter((f) => !mappedOutputs.has(f.field_name));
    if (unmapped.length > 0) {
      setRequiredFieldErrors(unmapped);
      return;
    }
    setRequiredFieldErrors([]);
    setIsSaving(true);
    try {
      const toSave = mappings.filter((m) => !m.is_excluded && m.output_column);
      const result = await saveMapping(workspaceId, session.import_id, toSave);
      setValidationErrors(result.validation_errors);
      if (result.validation_errors.length === 0) {
        onSaved(toSave, suggestionsData);
      }
    } catch (err) {
      console.error('Save mapping failed', err);
    } finally {
      setIsSaving(false);
    }
  };

  if (isLoadingSuggestions) {
    return (
      <div className="flex items-center gap-2 text-sm text-gray-500 py-8 justify-center">
        <Loader2 size={16} className="animate-spin" />
        Analyzing columns and generating suggestions…
      </div>
    );
  }

  // Sort canonical schema: required first, then optional (both alphabetical within group)
  const sortedSchema = [
    ...canonicalSchema.filter((f) => f.required).sort((a, b) => a.field_name.localeCompare(b.field_name)),
    ...canonicalSchema.filter((f) => !f.required).sort((a, b) => a.field_name.localeCompare(b.field_name)),
  ];

  return (
    <div className="space-y-4">
      {requiredFieldErrors.length > 0 && (
        <div className="flex items-start gap-2 text-red-600 text-sm bg-red-50 border border-red-200 rounded-lg p-3">
          <AlertCircle size={16} className="shrink-0 mt-0.5" />
          <div>
            <div className="font-medium mb-1">Required fields not mapped:</div>
            {requiredFieldErrors.map((f) => (
              <div key={f.field_name}>
                <span className="font-mono">{f.field_name}</span> — {f.description}
              </div>
            ))}
          </div>
        </div>
      )}

      {validationErrors.length > 0 && (
        <div className="flex items-start gap-2 text-red-600 text-sm bg-red-50 border border-red-200 rounded-lg p-3">
          <AlertCircle size={16} className="shrink-0 mt-0.5" />
          <div>
            {validationErrors.map((e, i) => <div key={i}>{e.message}</div>)}
          </div>
        </div>
      )}

      <div className="border border-gray-200 rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b border-gray-200">
            <tr>
              <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Source Column</th>
              <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Confidence</th>
              <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                Census Field <span className="text-red-500">*</span> = required
              </th>
              <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Exclude</th>
              <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Transforms</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {mappings.map((m, idx) => {
              const suggestion = suggestionMap.get(m.input_column);
              const formatDetection = suggestion?.format_detection ?? null;
              const rowBg = m.is_excluded
                ? 'opacity-40'
                : suggestion?.confidence === 'medium'
                ? 'bg-amber-50'
                : 'hover:bg-gray-50';

              return (
                <React.Fragment key={m.input_column}>
                  <tr className={rowBg}>
                    <td className="px-3 py-2 font-mono text-xs text-gray-600">{m.input_column}</td>
                    <td className="px-3 py-2">
                      <ConfidenceBadge confidence={suggestion?.confidence ?? null} />
                    </td>
                    <td className="px-3 py-2">
                      <div>
                        <select
                          value={m.output_column}
                          onChange={(e) => updateMapping(idx, { output_column: e.target.value })}
                          disabled={m.is_excluded}
                          className="text-xs border border-gray-200 rounded px-2 py-1 w-52"
                        >
                          <option value="">— not mapped —</option>
                          {sortedSchema.map((f) => (
                            <option key={f.field_name} value={f.field_name}>
                              {f.required ? '* ' : ''}{f.field_name}
                            </option>
                          ))}
                        </select>
                        {formatDetection && !m.is_excluded && (
                          <FormatPanel detection={formatDetection} />
                        )}
                      </div>
                    </td>
                    <td className="px-3 py-2">
                      <input
                        type="checkbox"
                        checked={m.is_excluded || false}
                        onChange={(e) => updateMapping(idx, { is_excluded: e.target.checked })}
                        className="rounded border-gray-300"
                      />
                    </td>
                    <td className="px-3 py-2">
                      <button
                        onClick={() => toggleExpand(m.input_column)}
                        disabled={m.is_excluded}
                        className="flex items-center gap-1 text-xs text-fidelity-green hover:underline disabled:opacity-40"
                      >
                        {m.transformations.length > 0 ? `${m.transformations.length} transform(s)` : 'Add'}
                        {expandedRows.has(m.input_column) ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                      </button>
                    </td>
                  </tr>
                  {expandedRows.has(m.input_column) && !m.is_excluded && (
                    <tr>
                      <td colSpan={5} className="px-6 py-3 bg-gray-50">
                        <div className="space-y-2">
                          {m.transformations.map((t, tIdx) => (
                            <div key={tIdx} className="flex items-center gap-2">
                              <select
                                value={t.transform_type}
                                onChange={(e) => updateTransform(idx, tIdx, { transform_type: e.target.value as TransformType, params: {} })}
                                className="text-xs border border-gray-200 rounded px-2 py-1"
                              >
                                {TRANSFORM_TYPES.map((tt) => (
                                  <option key={tt.value} value={tt.value}>{tt.label}</option>
                                ))}
                              </select>
                              <TransformParams
                                type={t.transform_type}
                                params={t.params}
                                onChange={(p) => updateTransform(idx, tIdx, { params: p })}
                              />
                              <button
                                onClick={() => removeTransform(idx, tIdx)}
                                className="text-red-400 hover:text-red-600 text-xs"
                              >
                                ✕
                              </button>
                            </div>
                          ))}
                          {m.transformations.length < 5 && (
                            <button
                              onClick={() => addTransform(idx)}
                              className="text-xs text-fidelity-green hover:underline"
                            >
                              + Add transform
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="flex justify-end">
        <button
          onClick={handleSave}
          disabled={isSaving}
          className="flex items-center gap-2 px-4 py-2 bg-fidelity-green text-white text-sm rounded-lg hover:bg-fidelity-dark disabled:opacity-50"
        >
          {isSaving ? <Loader2 size={16} className="animate-spin" /> : null}
          Save Mapping & Continue
        </button>
      </div>
    </div>
  );
}
