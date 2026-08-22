import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { userService } from '../api';

const questions = [
  {
    id: 'body_frame',
    question: 'How would you describe your natural body frame?',
    options: [
      { id: 'vata', text: 'Thin, light, prominent joints', dosha: 'Vata' },
      { id: 'pitta', text: 'Medium, athletic, well-proportioned', dosha: 'Pitta' },
      { id: 'kapha', text: 'Broad, sturdy, heavier build', dosha: 'Kapha' }
    ]
  },
  {
    id: 'skin_type',
    question: 'What is your typical skin type?',
    options: [
      { id: 'vata', text: 'Dry, rough, thin, prone to cracking', dosha: 'Vata' },
      { id: 'pitta', text: 'Warm, oily in T-zone, prone to redness/freckles', dosha: 'Pitta' },
      { id: 'kapha', text: 'Thick, oily, cool, smooth', dosha: 'Kapha' }
    ]
  },
  {
    id: 'digestion',
    question: 'How is your digestion and appetite usually?',
    options: [
      { id: 'vata', text: 'Irregular, variable, prone to bloating', dosha: 'Vata' },
      { id: 'pitta', text: 'Strong, intense, irritable if meals are skipped', dosha: 'Pitta' },
      { id: 'kapha', text: 'Slow, steady, can easily skip meals', dosha: 'Kapha' }
    ]
  },
  {
    id: 'climate_preference',
    question: 'Which climate do you prefer the least?',
    options: [
      { id: 'vata', text: 'Cold and dry', dosha: 'Vata' },
      { id: 'pitta', text: 'Hot and humid', dosha: 'Pitta' },
      { id: 'kapha', text: 'Cold and damp', dosha: 'Kapha' }
    ]
  }
];

export function Onboarding() {
  const { isAuthenticated, refreshProfile } = useAuth();
  const navigate = useNavigate();
  
  const [currentStep, setCurrentStep] = useState(0);
  const [responses, setResponses] = useState<Record<string, string>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    if (!isAuthenticated) {
      navigate('/welcome');
    }
  }, [isAuthenticated, navigate]);

  const handleSelect = (questionId: string, text: string) => {
    setResponses(prev => ({ ...prev, [questionId]: text }));
    if (currentStep < questions.length - 1) {
      setTimeout(() => setCurrentStep(prev => prev + 1), 300);
    }
  };

  const handleSubmit = async () => {
    setIsSubmitting(true);
    try {
      await userService.saveQuestionnaire(responses);
      await refreshProfile();
      navigate('/');
    } catch (err) {
      console.error("Failed to save questionnaire", err);
    } finally {
      setIsSubmitting(false);
    }
  };

  if (!isAuthenticated) return null;

  const currentQ = questions[currentStep];

  return (
    <div className="min-h-screen bg-background flex flex-col items-center justify-center p-6 relative overflow-hidden">
      {/* Decorative Blobs */}
      <div className="absolute top-0 right-0 w-96 h-96 bg-primary/10 rounded-full blur-3xl -translate-y-1/2 translate-x-1/2"></div>
      <div className="absolute bottom-0 left-0 w-[500px] h-[500px] bg-secondary/10 rounded-full blur-3xl translate-y-1/2 -translate-x-1/2"></div>

      <div className="w-full max-w-2xl bg-surface/80 backdrop-blur-md rounded-3xl p-8 md:p-12 shadow-sm border border-surface-variant relative z-10">
        
        <div className="mb-12">
          <h1 className="font-headline-display text-headline-lg font-bold text-on-background mb-4 text-center">Discover Your Dosha</h1>
          <p className="font-body-lg text-body-lg text-on-surface-variant text-center max-w-lg mx-auto">
            To generate a personalized routine (Dinacharya), we first need to understand your natural mind-body constitution (Prakriti).
          </p>
        </div>

        <div className="mb-8">
          <div className="flex justify-between items-center mb-2">
            <span className="font-caption text-caption text-on-surface-variant">Question {currentStep + 1} of {questions.length}</span>
            <span className="font-caption text-caption text-primary">{Math.round(((currentStep + 1) / questions.length) * 100)}%</span>
          </div>
          <div className="h-2 w-full bg-surface-container rounded-full overflow-hidden">
            <div 
              className="h-full bg-primary transition-all duration-500 ease-out rounded-full"
              style={{ width: `${((currentStep + 1) / questions.length) * 100}%` }}
            ></div>
          </div>
        </div>

        <div className="min-h-[250px]">
          <h2 className="font-headline-md text-headline-md font-semibold text-on-background mb-6">
            {currentQ.question}
          </h2>

          <div className="space-y-4">
            {currentQ.options.map((opt) => (
              <button
                key={opt.id}
                onClick={() => handleSelect(currentQ.id, opt.text)}
                className={`w-full text-left p-5 rounded-2xl border transition-all duration-200 ${
                  responses[currentQ.id] === opt.text
                    ? 'border-primary bg-primary-container/20 ring-2 ring-primary/20'
                    : 'border-surface-variant bg-surface-container-lowest hover:border-primary/50'
                }`}
              >
                <span className="font-body-lg text-body-lg text-on-surface">{opt.text}</span>
              </button>
            ))}
          </div>
        </div>

        <div className="mt-10 flex justify-between items-center">
          <button 
            disabled={currentStep === 0}
            onClick={() => setCurrentStep(prev => prev - 1)}
            className="px-6 py-3 font-label-lg text-label-lg text-on-surface-variant hover:text-on-background disabled:opacity-30 transition-colors"
          >
            Back
          </button>
          
          {currentStep === questions.length - 1 ? (
            <button 
              onClick={handleSubmit}
              disabled={isSubmitting || !responses[currentQ.id]}
              className="px-8 py-3 bg-primary text-on-primary rounded-full font-label-lg text-label-lg hover:bg-primary-container hover:shadow-md transition-all disabled:opacity-50 flex items-center gap-2"
            >
              {isSubmitting ? 'Analyzing...' : 'Complete Profile'}
              {!isSubmitting && <span className="material-symbols-outlined text-[20px]">arrow_forward</span>}
            </button>
          ) : (
            <button 
              onClick={() => setCurrentStep(prev => prev + 1)}
              disabled={!responses[currentQ.id]}
              className="px-8 py-3 bg-surface-container-highest text-on-surface rounded-full font-label-lg text-label-lg hover:bg-surface-variant transition-colors disabled:opacity-50"
            >
              Next
            </button>
          )}
        </div>

      </div>
    </div>
  );
}
