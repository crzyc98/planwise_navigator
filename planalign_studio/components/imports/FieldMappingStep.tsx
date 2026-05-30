import React, { useEffect, useState } from 'react';
import { Plus, Trash2, ChevronDown, ChevronUp, AlertCircle, Loader2, Save } from 'lucide-react';
import {
  ImportSession,
  FieldMapping,
  Transformation,
  OutputType,
  TransformType,
  MappingValidationError,
  MappingTemplateSummary,
  saveMapping,
  listTemplates,
  saveTemplate,
  applyTemplate,
} from '../../services/importService';

const OUTPUT_TYPES: OutputType[] = ['string', 'integer', 'decimal', 'boolean', 'date', 'timestamp'];
const TRANSFORM_TYPES: { value: TransformType; label: string }[] = [
  { value: 'string_case', label: 'Change Case' },
  { value: 'date_parse', label: 'Parse Date' },
  { value: 'null_replace', label: 'Replace Nulls' },
  { value: 'null_drop', label: 'Drop Null Rows' },
  { value: 'calculated_field', label: 'Calculated Field' },
];

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
  onSaved: (mappings: FieldMapping[]) => void;
}

export default function FieldMappingStep({ workspaceId, session, onSaved }: Props) {
  const [mappings, setMappings] = useState<FieldMapping[]>(() =>
    session.detected_columns.map((col) => ({
      input_column: col.name,
      output_column: col.name.toLowerCase().replace(/[^a-z0-9_]/g, '_').replace(/^[^a-z]/, 'col_$&'),
      output_type: col.inferred_type === 'unknown' ? 'string' : (col.inferred_type as OutputType),
      is_required: false,
      is_excluded: false,
      transformations: [],
    }))
  );
  const [validationErrors, setValidationErrors] = useState<MappingValidationError[]>([]);
  const [isSaving, setIsSaving] = useState(false);
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set());
  const [templates, setTemplates] = useState<MappingTemplateSummary[]>([]);
  const [showSaveTemplate, setShowSaveTemplate] = useState(false);
  const [templateName, setTemplateName] = useState('');
  const [templateDesc, setTemplateDesc] = useState('');
  const [isSavingTemplate, setIsSavingTemplate] = useState(false);

  useEffect(() => {
    listTemplates(workspaceId).then(r => setTemplates(r.templates)).catch(() => {});
  }, [workspaceId]);

  const handleApplyTemplate = async (templateId: string) => {
    try {
      const result = await applyTemplate(workspaceId, session.import_id, templateId);
      // Reload mappings from saved state
      setValidationErrors(result.validation_errors);
    } catch (err) {
      console.error('Apply template failed', err);
    }
  };

  const handleSaveTemplate = async () => {
    if (!templateName.trim()) return;
    setIsSavingTemplate(true);
    try {
      await saveTemplate(workspaceId, session.import_id, templateName, templateDesc || undefined);
      setShowSaveTemplate(false);
      setTemplateName('');
      setTemplateDesc('');
      const updated = await listTemplates(workspaceId);
      setTemplates(updated.templates);
    } catch (err) {
      console.error('Save template failed', err);
    } finally {
      setIsSavingTemplate(false);
    }
  };

  const updateMapping = (idx: number, patch: Partial<FieldMapping>) => {
    setMappings((prev) => prev.map((m, i) => i === idx ? { ...m, ...patch } : m));
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

  const toggleExpand = (col: string) => {
    setExpandedRows((prev) => {
      const next = new Set(prev);
      if (next.has(col)) next.delete(col); else next.add(col);
      return next;
    });
  };

  const handleSave = async () => {
    setIsSaving(true);
    try {
      const result = await saveMapping(workspaceId, session.import_id, mappings);
      setValidationErrors(result.validation_errors);
      if (result.validation_errors.length === 0) {
        onSaved(mappings);
      }
    } catch (err) {
      console.error('Save mapping failed', err);
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="space-y-4">
      {/* Template controls */}
      <div className="flex items-center gap-3 flex-wrap">
        {templates.length > 0 && (
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-500">Load template:</span>
            <select
              className="text-xs border border-gray-200 rounded px-2 py-1"
              defaultValue=""
              onChange={(e) => e.target.value && handleApplyTemplate(e.target.value)}
            >
              <option value="">— select —</option>
              {templates.map((t) => (
                <option key={t.template_id} value={t.template_id}>{t.name}</option>
              ))}
            </select>
          </div>
        )}
        <button
          onClick={() => setShowSaveTemplate(true)}
          className="flex items-center gap-1 text-xs text-fidelity-green hover:underline"
        >
          <Save size={13} /> Save as template
        </button>
      </div>

      {showSaveTemplate && (
        <div className="border border-gray-200 rounded-lg p-4 bg-gray-50 space-y-3">
          <h4 className="text-sm font-medium text-gray-700">Save Mapping Template</h4>
          <input
            type="text"
            placeholder="Template name (required)"
            className="w-full text-sm border border-gray-200 rounded px-3 py-2"
            value={templateName}
            onChange={(e) => setTemplateName(e.target.value)}
          />
          <input
            type="text"
            placeholder="Description (optional)"
            className="w-full text-sm border border-gray-200 rounded px-3 py-2"
            value={templateDesc}
            onChange={(e) => setTemplateDesc(e.target.value)}
          />
          <div className="flex gap-2">
            <button
              onClick={handleSaveTemplate}
              disabled={isSavingTemplate || !templateName.trim()}
              className="text-sm px-3 py-1.5 bg-fidelity-green text-white rounded-lg disabled:opacity-50"
            >
              {isSavingTemplate ? <Loader2 size={14} className="animate-spin inline" /> : 'Save'}
            </button>
            <button onClick={() => setShowSaveTemplate(false)} className="text-sm px-3 py-1.5 border border-gray-200 rounded-lg">
              Cancel
            </button>
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
              <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Output Column</th>
              <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Type</th>
              <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Exclude</th>
              <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Transforms</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {mappings.map((m, idx) => (
              <React.Fragment key={m.input_column}>
                <tr className={m.is_excluded ? 'opacity-40' : 'hover:bg-gray-50'}>
                  <td className="px-3 py-2 font-mono text-xs text-gray-600">{m.input_column}</td>
                  <td className="px-3 py-2">
                    <input
                      type="text"
                      value={m.output_column}
                      onChange={(e) => updateMapping(idx, { output_column: e.target.value })}
                      disabled={m.is_excluded}
                      className="text-xs border border-gray-200 rounded px-2 py-1 w-36 font-mono"
                    />
                  </td>
                  <td className="px-3 py-2">
                    <select
                      value={m.output_type}
                      onChange={(e) => updateMapping(idx, { output_type: e.target.value as OutputType })}
                      disabled={m.is_excluded}
                      className="text-xs border border-gray-200 rounded px-2 py-1"
                    >
                      {OUTPUT_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
                    </select>
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
                            <button onClick={() => removeTransform(idx, tIdx)} className="text-red-400 hover:text-red-600">
                              <Trash2 size={14} />
                            </button>
                          </div>
                        ))}
                        {m.transformations.length < 5 && (
                          <button
                            onClick={() => addTransform(idx)}
                            className="flex items-center gap-1 text-xs text-fidelity-green hover:underline"
                          >
                            <Plus size={13} /> Add transform
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                )}
              </React.Fragment>
            ))}
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
