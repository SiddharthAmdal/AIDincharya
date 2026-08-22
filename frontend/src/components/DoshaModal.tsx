import React from 'react';
import type { DoshaProfile } from '../api';

interface DoshaModalProps {
  isOpen: boolean;
  onClose: () => void;
  doshaProfile: DoshaProfile | null;
}

export function DoshaModal({ isOpen, onClose, doshaProfile }: DoshaModalProps) {
  if (!isOpen) return null;

  const vata = doshaProfile?.prakriti?.vata ? Math.round(doshaProfile.prakriti.vata * 100) : 0;
  const pitta = doshaProfile?.prakriti?.pitta ? Math.round(doshaProfile.prakriti.pitta * 100) : 0;
  const kapha = doshaProfile?.prakriti?.kapha ? Math.round(doshaProfile.prakriti.kapha * 100) : 0;

  // Determine dominant dosha for a quick summary
  let dominant = 'Vata';
  let desc = "Vata governs movement and communication. When balanced, you are creative and energetic. When imbalanced, you may experience anxiety or dry skin.";
  if (pitta > vata && pitta > kapha) {
    dominant = 'Pitta';
    desc = "Pitta governs digestion and metabolism. When balanced, you are focused and intelligent. When imbalanced, you may experience anger or inflammation.";
  } else if (kapha > vata && kapha > pitta) {
    dominant = 'Kapha';
    desc = "Kapha governs structure and lubrication. When balanced, you are grounded and compassionate. When imbalanced, you may experience lethargy or congestion.";
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-background/80 backdrop-blur-sm" onClick={onClose}></div>
      <div className="relative bg-surface rounded-3xl w-full max-w-md shadow-lg border border-surface-variant overflow-hidden flex flex-col">
        
        <div className="p-6 border-b border-surface-variant flex justify-between items-center bg-surface-container-lowest">
          <h2 className="font-headline-md text-[20px] font-semibold text-on-surface flex items-center gap-2">
            <span className="material-symbols-outlined text-primary">psychiatry</span>
            Your Prakriti
          </h2>
          <button onClick={onClose} className="p-2 rounded-full hover:bg-surface-container text-on-surface-variant transition-colors">
            <span className="material-symbols-outlined">close</span>
          </button>
        </div>

        <div className="p-6 space-y-6">
          <div className="text-center">
            <p className="font-label-lg text-primary uppercase tracking-wide mb-1">Dominant Dosha</p>
            <h3 className="font-headline-display text-4xl font-bold text-on-surface">{dominant}</h3>
          </div>

          <div className="space-y-4">
            <div>
              <div className="flex justify-between text-sm mb-1">
                <span className="font-medium text-on-surface">Vata (Air & Space)</span>
                <span className="text-primary">{vata}%</span>
              </div>
              <div className="h-2 w-full bg-surface-container rounded-full overflow-hidden">
                <div className="h-full bg-primary rounded-full" style={{ width: `${vata}%` }}></div>
              </div>
            </div>
            
            <div>
              <div className="flex justify-between text-sm mb-1">
                <span className="font-medium text-on-surface">Pitta (Fire & Water)</span>
                <span className="text-secondary">{pitta}%</span>
              </div>
              <div className="h-2 w-full bg-surface-container rounded-full overflow-hidden">
                <div className="h-full bg-secondary rounded-full" style={{ width: `${pitta}%` }}></div>
              </div>
            </div>

            <div>
              <div className="flex justify-between text-sm mb-1">
                <span className="font-medium text-on-surface">Kapha (Earth & Water)</span>
                <span className="text-tertiary">{kapha}%</span>
              </div>
              <div className="h-2 w-full bg-surface-container rounded-full overflow-hidden">
                <div className="h-full bg-tertiary rounded-full" style={{ width: `${kapha}%` }}></div>
              </div>
            </div>
          </div>
          
          <div className="bg-surface-container-lowest border border-surface-variant rounded-2xl p-4">
            <p className="font-body-md text-on-surface-variant leading-relaxed">
              {desc}
            </p>
          </div>
        </div>

        <div className="p-6 pt-0">
          <button 
            onClick={onClose} 
            className="w-full py-3 rounded-full bg-primary text-on-primary font-label-md hover:bg-primary-container transition-colors"
          >
            Understand My Balance
          </button>
        </div>
      </div>
    </div>
  );
}
