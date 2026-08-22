import React from 'react';

interface TaskModalProps {
  isOpen: boolean;
  onClose: () => void;
  taskTitle: string;
  taskDescription: string;
  taskRationale: string;
}

export function TaskModal({ isOpen, onClose, taskTitle, taskDescription, taskRationale }: TaskModalProps) {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-background/80 backdrop-blur-sm" onClick={onClose}></div>
      <div className="relative bg-surface rounded-3xl w-full max-w-md shadow-lg border border-surface-variant overflow-hidden flex flex-col">
        
        <div className="p-6 border-b border-surface-variant flex justify-between items-center bg-surface-container-lowest">
          <h2 className="font-headline-md text-[20px] font-semibold text-on-surface flex items-center gap-2">
            <span className="material-symbols-outlined text-primary">psychiatry</span>
            {taskTitle}
          </h2>
          <button onClick={onClose} className="p-2 rounded-full hover:bg-surface-container text-on-surface-variant transition-colors">
            <span className="material-symbols-outlined">close</span>
          </button>
        </div>

        <div className="p-6 space-y-6">
          <div>
            <h3 className="font-label-md text-label-md text-primary uppercase tracking-wide mb-2">The Practice</h3>
            <p className="font-body-md text-on-surface">{taskDescription}</p>
          </div>
          
          <div className="bg-primary-container/20 border border-primary/20 rounded-2xl p-4">
            <h3 className="font-label-md text-label-md text-primary uppercase tracking-wide mb-2 flex items-center gap-2">
              <span className="material-symbols-outlined text-[18px]">menu_book</span>
              Ayurvedic Rationale
            </h3>
            <p className="font-body-md text-on-surface-variant italic leading-relaxed">
              "{taskRationale || "This practice helps balance your dominant doshas and align your circadian rhythm with nature."}"
            </p>
          </div>
        </div>

        <div className="p-6 pt-0">
          <button 
            onClick={onClose} 
            className="w-full py-3 rounded-full bg-surface-container-highest text-on-surface font-label-md hover:bg-surface-variant transition-colors"
          >
            Got it
          </button>
        </div>
      </div>
    </div>
  );
}
