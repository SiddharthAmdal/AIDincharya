import React, { useState } from 'react';
import { healthService } from '../api';

interface HealthModalProps {
  onClose: () => void;
  onSuccess: () => void;
}

export function HealthModal({ onClose, onSuccess }: HealthModalProps) {
  const [hrv, setHrv] = useState('45');
  const [rhr, setRhr] = useState('68');
  const [sleep, setSleep] = useState('7.5');
  const [temp, setTemp] = useState('36.8');
  
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [selectedSymptoms, setSelectedSymptoms] = useState<string[]>([]);

  const symptomsList = [
    'Fatigue', 'Headache', 'Bloating', 'Joint Pain', 
    'Anxiety', 'Acid Reflux', 'Congestion', 'Dry Skin'
  ];

  const toggleSymptom = (s: string) => {
    setSelectedSymptoms(prev => 
      prev.includes(s) ? prev.filter(x => x !== s) : [...prev, s]
    );
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    try {
      await healthService.uploadTelemetry({
        telemetry: {
          hrv_ms: parseFloat(hrv) || 0,
          resting_hr: parseFloat(rhr) || 0,
          sleep_hours: parseFloat(sleep) || 0,
          body_temp_c: parseFloat(temp) || 0,
        },
        symptoms: selectedSymptoms
      });
      onSuccess();
      onClose();
    } catch (err) {
      console.error("Failed to upload telemetry", err);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-background/80 backdrop-blur-sm" onClick={onClose}></div>
      <div className="relative bg-surface rounded-3xl w-full max-w-lg shadow-lg border border-surface-variant overflow-hidden flex flex-col max-h-[90vh]">
        
        <div className="p-6 border-b border-surface-variant flex justify-between items-center bg-surface-container-lowest">
          <h2 className="font-headline-md text-[22px] font-semibold text-on-surface">Log Health Vitals</h2>
          <button onClick={onClose} className="p-2 rounded-full hover:bg-surface-container text-on-surface-variant transition-colors">
            <span className="material-symbols-outlined">close</span>
          </button>
        </div>

        <div className="p-6 overflow-y-auto flex-1">
          <form id="health-form" onSubmit={handleSubmit} className="space-y-6">
            
            <div>
              <h3 className="font-label-lg text-label-lg text-on-surface-variant mb-4 uppercase tracking-wide">Wearable Telemetry</h3>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1">
                  <label className="font-caption text-caption text-on-surface-variant">HRV (ms)</label>
                  <input type="number" step="0.1" value={hrv} onChange={e => setHrv(e.target.value)} required className="w-full bg-surface-container-low rounded-xl px-4 py-3 font-body-md text-on-surface border border-surface-variant focus:outline-none focus:border-primary transition-colors" />
                </div>
                <div className="space-y-1">
                  <label className="font-caption text-caption text-on-surface-variant">Resting HR (bpm)</label>
                  <input type="number" step="0.1" value={rhr} onChange={e => setRhr(e.target.value)} required className="w-full bg-surface-container-low rounded-xl px-4 py-3 font-body-md text-on-surface border border-surface-variant focus:outline-none focus:border-primary transition-colors" />
                </div>
                <div className="space-y-1">
                  <label className="font-caption text-caption text-on-surface-variant">Sleep (hrs)</label>
                  <input type="number" step="0.1" value={sleep} onChange={e => setSleep(e.target.value)} required className="w-full bg-surface-container-low rounded-xl px-4 py-3 font-body-md text-on-surface border border-surface-variant focus:outline-none focus:border-primary transition-colors" />
                </div>
                <div className="space-y-1">
                  <label className="font-caption text-caption text-on-surface-variant">Body Temp (°C)</label>
                  <input type="number" step="0.1" value={temp} onChange={e => setTemp(e.target.value)} required className="w-full bg-surface-container-low rounded-xl px-4 py-3 font-body-md text-on-surface border border-surface-variant focus:outline-none focus:border-primary transition-colors" />
                </div>
              </div>
            </div>

            <div className="pt-4 border-t border-surface-variant/50">
              <h3 className="font-label-lg text-label-lg text-on-surface-variant mb-4 uppercase tracking-wide">Self-Reported Symptoms</h3>
              <div className="flex flex-wrap gap-2">
                {symptomsList.map(symp => (
                  <button
                    key={symp}
                    type="button"
                    onClick={() => toggleSymptom(symp)}
                    className={`px-4 py-2 rounded-full font-body-md text-sm border transition-all ${
                      selectedSymptoms.includes(symp)
                        ? 'bg-primary-container border-primary text-on-primary-container font-medium'
                        : 'bg-surface-container-lowest border-outline text-on-surface hover:bg-surface-container'
                    }`}
                  >
                    {symp}
                  </button>
                ))}
              </div>
            </div>
            
          </form>
        </div>

        <div className="p-6 border-t border-surface-variant bg-surface-container-lowest flex justify-end gap-3">
          <button type="button" onClick={onClose} className="px-6 py-2.5 rounded-full font-label-md text-on-surface-variant hover:bg-surface-container transition-colors">
            Cancel
          </button>
          <button type="submit" form="health-form" disabled={isSubmitting} className="px-8 py-2.5 rounded-full bg-primary text-on-primary font-label-md hover:bg-primary-container transition-colors disabled:opacity-50">
            {isSubmitting ? 'Saving...' : 'Save Vitals'}
          </button>
        </div>

      </div>
    </div>
  );
}
