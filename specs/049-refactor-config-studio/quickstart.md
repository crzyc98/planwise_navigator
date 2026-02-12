# Quickstart: ConfigStudio Refactoring

**Feature**: 049-refactor-config-studio

## What Changed

The monolithic `ConfigStudio.tsx` (4,342 lines) has been split into ~15 focused files under `components/config/`.

## File Map

| Before | After |
|--------|-------|
| ConfigStudio.tsx (lines 1-64) | `config/types.ts` + `config/constants.ts` |
| ConfigStudio.tsx (lines 66-149) | `config/InputField.tsx` + `config/CompensationInput.tsx` |
| ConfigStudio.tsx (lines 151-1562) | `config/ConfigContext.tsx` + `config/buildConfigPayload.ts` |
| ConfigStudio.tsx (lines 1749-1962) | `config/DataSourcesSection.tsx` |
| ConfigStudio.tsx (lines 1965-2009) | `config/SimulationSection.tsx` |
| ConfigStudio.tsx (lines 2012-2208) | `config/CompensationSection.tsx` |
| ConfigStudio.tsx (lines 2211-2853) | `config/NewHireSection.tsx` + `config/PromotionHazardEditor.tsx` |
| ConfigStudio.tsx (lines 2856-3153) | `config/SegmentationSection.tsx` |
| ConfigStudio.tsx (lines 3156-3209) | `config/TurnoverSection.tsx` |
| ConfigStudio.tsx (lines 3212-3851) | `config/DCPlanSection.tsx` |
| ConfigStudio.tsx (lines 3854-4002) | `config/AdvancedSection.tsx` |
| ConfigStudio.tsx (lines 4008-4339) | `config/TemplateModal.tsx` + `config/CopyScenarioModal.tsx` |
| ConfigStudio.tsx (remaining) | `ConfigStudio.tsx` (~200 lines: shell) |

## How to Access Shared State in a Section Component

```tsx
import { useConfigContext } from './ConfigContext';

export default function MySection() {
  const { formData, setFormData, handleChange, inputProps } = useConfigContext();

  return (
    <div>
      <InputField {...inputProps('fieldName')} label="Field Name" type="number" />
    </div>
  );
}
```

## How to Add a New Section

1. Create `components/config/NewSection.tsx` following the pattern above
2. In `ConfigStudio.tsx`, add to the sections array:
   ```tsx
   { id: 'newsection', label: 'New Section', icon: SomeIcon }
   ```
3. Add conditional render:
   ```tsx
   {activeSection === 'newsection' && <NewSection />}
   ```
4. In `ConfigContext.tsx`, add dirty-tracking fields to the `dirtySections` useMemo

## Key Patterns

- **formData updates**: Use `setFormData(prev => ({ ...prev, fieldName: newValue }))` for programmatic updates, or `handleChange` for input onChange events
- **Local state**: Keep section-specific UI state (loading, errors) local to the section component
- **Context state**: Only state needed for dirty-tracking or save goes in ConfigContext
- **API calls**: Section components import API functions directly from `../../services/api`
