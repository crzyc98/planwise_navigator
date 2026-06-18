import { X } from 'lucide-react';
import type { TenureGradedBand, MatchTier } from './types';
import { calculateTenureGradedBandCap } from './constants';
import { validateMatchTiers } from './DCPlanSection';

/**
 * Feature 099: editor for the tenure-graded multi-tier employer match mode.
 *
 * Unlike the superseded single-tier `tenure_based` editor (one match rate +
 * one max deferral % per band), each band here carries its own ordered,
 * cumulative list of deferral-rate tiers (e.g. 100% on first 2%, 50% on next 6%).
 * No fixed limit on the number of bands or tiers per band (per spec clarification).
 */

interface TenureGradedMatchEditorProps {
  bands: TenureGradedBand[];
  onChange: (bands: TenureGradedBand[]) => void;
}

function emptyTier(): MatchTier {
  return { deferralMin: 0, deferralMax: 2, matchRate: 100 };
}

function emptyBand(prevMaxYears: number | null): TenureGradedBand {
  return {
    minYears: prevMaxYears ?? 0,
    maxYears: null,
    tiers: [emptyTier()],
  };
}

export function TenureGradedMatchEditor({ bands, onChange }: TenureGradedMatchEditorProps) {
  const updateBand = (bandIdx: number, updates: Partial<TenureGradedBand>) => {
    const newBands = [...bands];
    newBands[bandIdx] = { ...newBands[bandIdx], ...updates };
    onChange(newBands);
  };

  const updateTier = (bandIdx: number, tierIdx: number, updates: Partial<MatchTier>) => {
    const newTiers = [...bands[bandIdx].tiers];
    newTiers[tierIdx] = { ...newTiers[tierIdx], ...updates };
    updateBand(bandIdx, { tiers: newTiers });
  };

  const addTier = (bandIdx: number) => {
    const tiers = bands[bandIdx].tiers;
    const last = tiers[tiers.length - 1];
    const newMin = last ? last.deferralMax : 0;
    updateBand(bandIdx, { tiers: [...tiers, { deferralMin: newMin, deferralMax: newMin + 5, matchRate: 50 }] });
  };

  const removeTier = (bandIdx: number, tierIdx: number) => {
    const newTiers = bands[bandIdx].tiers.filter((_, i) => i !== tierIdx);
    updateBand(bandIdx, { tiers: newTiers });
  };

  const addBand = () => {
    const last = bands[bands.length - 1];
    const newBands = [...bands];
    if (last && last.maxYears === null) {
      newBands[newBands.length - 1] = { ...last, maxYears: last.minYears + 5 };
      onChange([...newBands, emptyBand(last.minYears + 5)]);
    } else {
      onChange([...bands, emptyBand(last ? last.maxYears : 0)]);
    }
  };

  const removeBand = (bandIdx: number) => {
    onChange(bands.filter((_, i) => i !== bandIdx));
  };

  const bandWarnings = validateMatchTiers(
    bands.map((b) => ({ min: b.minYears, max: b.maxYears })),
    'years',
  );

  return (
    <div className="sm:col-span-6 bg-gray-50 p-4 rounded-lg border border-gray-200">
      <span className="block text-sm font-medium text-gray-700 mb-3">Tenure-Graded Match Bands</span>

      <div className="space-y-4">
        {bands.map((band, bandIdx) => {
          const tierWarnings = validateMatchTiers(
            band.tiers.map((t) => ({ min: t.deferralMin, max: t.deferralMax })),
            '% deferral',
          );
          const maxMatchPct = calculateTenureGradedBandCap(band) * 100;

          return (
            <div key={bandIdx} className="bg-white p-3 rounded border border-gray-300">
              <div className="flex items-center gap-2 mb-2">
                <span className="text-xs text-gray-500">Band {bandIdx + 1}:</span>
                <input type="number" min={0} value={band.minYears}
                  onChange={(e) => updateBand(bandIdx, { minYears: parseInt(e.target.value) || 0 })}
                  className="w-16 shadow-sm focus:ring-fidelity-green focus:border-fidelity-green sm:text-sm border-gray-300 rounded-md p-1 border text-center"
                />
                <span className="text-sm text-gray-600">to</span>
                <input type="number" min={0} value={band.maxYears ?? ''}
                  placeholder="&#8734;"
                  onChange={(e) => updateBand(bandIdx, { maxYears: e.target.value === '' ? null : parseInt(e.target.value) || 0 })}
                  className="w-16 shadow-sm focus:ring-fidelity-green focus:border-fidelity-green sm:text-sm border-gray-300 rounded-md p-1 border text-center"
                />
                <span className="text-sm text-gray-600">yrs</span>
                <span className="ml-auto text-xs text-gray-500">Max effective match: {maxMatchPct.toFixed(1)}%</span>
                {bands.length > 1 && (
                  <button type="button" onClick={() => removeBand(bandIdx)}
                    className="text-red-500 hover:text-red-700 p-1"
                  ><X size={16} /></button>
                )}
              </div>

              <div className="space-y-1 ml-4">
                {band.tiers.map((tier, tierIdx) => (
                  <div key={tierIdx} className="flex items-center gap-2 bg-gray-50 p-1.5 rounded border border-gray-200">
                    <span className="text-xs text-gray-500 w-4">{tierIdx + 1}.</span>
                    <span className="text-sm text-gray-600">0% to</span>
                    <input type="number" step="1" min={0} max={100} value={tier.deferralMax}
                      onChange={(e) => updateTier(bandIdx, tierIdx, { deferralMax: parseFloat(e.target.value) || 0 })}
                      className="w-14 shadow-sm focus:ring-fidelity-green focus:border-fidelity-green sm:text-sm border-gray-300 rounded-md p-1 border text-center"
                    />
                    <span className="text-sm text-gray-600">% deferral &#8594;</span>
                    <input type="number" step="5" min={0} max={200} value={tier.matchRate}
                      onChange={(e) => updateTier(bandIdx, tierIdx, { matchRate: parseFloat(e.target.value) || 0 })}
                      className="w-16 shadow-sm focus:ring-fidelity-green focus:border-fidelity-green sm:text-sm border-gray-300 rounded-md p-1 border text-center"
                    />
                    <span className="text-sm text-gray-600">% match</span>
                    {band.tiers.length > 1 && (
                      <button type="button" onClick={() => removeTier(bandIdx, tierIdx)}
                        className="ml-auto text-red-500 hover:text-red-700 p-1"
                      ><X size={14} /></button>
                    )}
                  </div>
                ))}
              </div>
              <button type="button" onClick={() => addTier(bandIdx)}
                className="mt-2 ml-4 text-xs text-fidelity-green hover:text-green-700 flex items-center gap-1"
              >+ Add Tier</button>

              {tierWarnings.length > 0 && (
                <div className="mt-2 ml-4 text-xs text-amber-600 space-y-0.5">
                  {tierWarnings.map((w, i) => <p key={i}>{w}</p>)}
                </div>
              )}
            </div>
          );
        })}
      </div>

      <button type="button" onClick={addBand}
        className="mt-3 text-sm text-fidelity-green hover:text-green-700 flex items-center gap-1"
      >+ Add Band</button>

      {bands.length === 0 && (
        <p className="mt-2 text-xs text-amber-600">Add at least one tenure band to configure tenure-graded matching</p>
      )}

      {bandWarnings.length > 0 && (
        <div className="mt-2 text-xs text-amber-600 space-y-0.5">
          {bandWarnings.map((w, i) => <p key={i}>{w}</p>)}
        </div>
      )}
    </div>
  );
}
