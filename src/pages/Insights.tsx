import React, { useState, useEffect, useRef } from 'react';
import { useAuth } from '../context/AuthContext';
import { knowledgeService, userService } from '../api';

interface Message {
  id: string;
  sender: 'user' | 'vaidya';
  text: string;
}

export function Insights() {
  const { profile } = useAuth();
  const [showContext, setShowContext] = useState(false);
  const [userState, setUserState] = useState<any>(null);
  const [query, setQuery] = useState('');
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 'welcome',
      sender: 'vaidya',
      text: 'Namaste. I am your Vaidya assistant. How can I help you balance your routine today?'
    }
  ]);
  const [isLoading, setIsLoading] = useState(false);
  const chatContainerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    async function loadState() {
      try {
        const state = await userService.getState();
        setUserState(state);
      } catch (err) {
        console.error("Failed to load user state", err);
      }
    }
    loadState();
  }, []);

  useEffect(() => {
    if (chatContainerRef.current) {
      chatContainerRef.current.scrollTop = chatContainerRef.current.scrollHeight;
    }
  }, [messages, isLoading]);

  const handleSend = async () => {
    if (!query.trim()) return;

    const userMessage: Message = { id: Date.now().toString(), sender: 'user', text: query };
    setMessages(prev => [...prev, userMessage]);
    setQuery('');
    setIsLoading(true);

    try {
      const res = await knowledgeService.search(userMessage.text);
      const replyText = res.results.length > 0 
        ? `I found some guidance in the texts: "${res.results[0].text}" (Source: ${res.results[0].source})` 
        : "I'm sorry, I don't have enough context to answer that right now based on our classical texts.";
      
      setMessages(prev => [...prev, { id: Date.now().toString(), sender: 'vaidya', text: replyText }]);
    } catch (err) {
      setMessages(prev => [...prev, { id: Date.now().toString(), sender: 'vaidya', text: "I'm having trouble accessing my knowledge base right now." }]);
    } finally {
      setIsLoading(false);
    }
  };

  const adherenceScore = userState?.adherence_score ? Math.round(userState.adherence_score * 100) : 76;

  return (
    <div className="flex-1 flex flex-col w-full relative bg-background">
      <header className="bg-surface docked full-width top-0 sticky z-50 flex justify-between items-center px-container-margin py-base h-[72px] border-b border-surface-variant/50">
        <h2 className="font-headline-md text-headline-md font-bold text-primary dark:text-primary md:hidden">AiDincharya</h2>
        <div className="hidden md:block"></div>
        <div className="flex items-center gap-4 text-on-surface-variant">
          <div className="h-8 w-8 rounded-full flex items-center justify-center font-bold text-primary border border-outline-variant bg-surface-container">
            {profile?.user?.username?.charAt(0).toUpperCase() || 'U'}
          </div>
        </div>
      </header>

      <main className="flex-1 flex flex-col lg:flex-row h-[calc(100vh-72px)] overflow-hidden bg-surface-container-low relative">
        <section className="flex-1 flex flex-col h-full relative">
          <div ref={chatContainerRef} className="flex-1 overflow-y-auto px-container-margin py-section-gap-md space-y-8 scroll-smooth pb-32 lg:pb-8">
            <div className="flex justify-center">
              <span className="font-caption text-caption text-on-surface-variant bg-surface-container-lowest px-4 py-1 rounded-full border border-surface-variant">Today</span>
            </div>
            
            {messages.map((msg) => (
              <div key={msg.id} className={`flex ${msg.sender === 'user' ? 'justify-end' : 'justify-start items-end gap-3'} animate-[fadeIn_0.3s_ease-out]`}>
                {msg.sender === 'vaidya' && (
                  <div className="w-10 h-10 rounded-full bg-primary-container flex items-center justify-center shrink-0 shadow-sm text-on-primary-container font-bold">
                    V
                  </div>
                )}
                <div className={`max-w-[80%] ${msg.sender === 'user' ? 'bg-surface-container-high rounded-2xl rounded-tr-sm px-6 py-4 shadow-sm border border-surface-variant/50' : ''}`}>
                  {msg.sender === 'vaidya' ? (
                    <div className="bg-surface-container-lowest rounded-2xl rounded-tl-sm px-6 py-4 shadow-[0_4px_20px_rgba(0,0,0,0.04)] border border-surface-variant">
                      <p className="font-body-md text-body-md text-on-surface">{msg.text}</p>
                    </div>
                  ) : (
                    <p className="font-body-md text-body-md text-on-surface">{msg.text}</p>
                  )}
                </div>
              </div>
            ))}
            {isLoading && (
              <div className="flex justify-start items-end gap-3">
                <div className="w-10 h-10 rounded-full bg-primary-container flex items-center justify-center shrink-0 shadow-sm text-on-primary-container">V</div>
                <div className="bg-surface-container-lowest rounded-2xl rounded-tl-sm px-6 py-4 shadow-[0_4px_20px_rgba(0,0,0,0.04)] border border-surface-variant text-on-surface-variant text-sm">
                  Thinking...
                </div>
              </div>
            )}
          </div>

          <div className="absolute bottom-16 lg:bottom-0 left-0 right-0 p-container-margin bg-background/90 backdrop-blur-sm border-t border-surface-variant/30 z-20">
            <div className="relative flex items-center">
              <input 
                value={query}
                onChange={e => setQuery(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleSend()}
                className="w-full bg-surface-container rounded-2xl pl-6 pr-16 py-4 font-body-md text-body-md text-on-surface placeholder-on-surface-variant border border-surface-variant focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary transition-all shadow-sm" 
                placeholder="Ask your Vaidya about your routine..." 
                type="text" 
              />
              <button 
                onClick={handleSend}
                disabled={isLoading}
                className="absolute right-2 p-2 rounded-xl bg-primary text-on-primary hover:bg-primary-container transition-colors flex items-center justify-center disabled:opacity-50"
              >
                <span className="material-symbols-outlined">send</span>
              </button>
            </div>
          </div>
        </section>

        <aside className={`w-full lg:w-80 xl:w-96 bg-surface-container-lowest border-l border-surface-variant h-full flex-col shrink-0 lg:flex shadow-[0_0_30px_rgba(0,0,0,0.02)] z-30 absolute lg:relative right-0 ${showContext ? 'flex' : 'hidden'}`}>
          <div className="p-6 border-b border-surface-variant/50 flex justify-between items-center">
            <h3 className="font-headline-md text-[20px] font-semibold text-on-surface">Vaidya Context</h3>
            <button className="text-on-surface-variant hover:text-primary transition-colors lg:hidden" onClick={() => setShowContext(false)}>
              <span className="material-symbols-outlined">close</span>
            </button>
          </div>
          <div className="p-6 space-y-8 overflow-y-auto flex-1">
            <div>
              <div className="flex justify-between items-end mb-4">
                <h4 className="font-label-md text-label-md text-on-surface-variant uppercase tracking-wider">Today's Adherence</h4>
                <span className="font-headline-md text-[28px] font-bold text-primary">{adherenceScore}%</span>
              </div>
              <div className="h-3 w-full bg-surface-container rounded-full overflow-hidden">
                <div className="h-full bg-primary rounded-full" style={{width: `${adherenceScore}%`}}></div>
              </div>
            </div>
            
            <div className="bg-surface-container-low p-5 rounded-2xl border border-surface-variant/40">
              <h4 className="font-label-md text-label-md text-on-surface-variant uppercase tracking-wider mb-4">Current State</h4>
              <div className="flex items-center gap-4 mb-4">
                <div className="w-12 h-12 rounded-full border border-primary/20 flex items-center justify-center bg-surface-container-lowest">
                  <span className="material-symbols-outlined text-primary font-light text-[28px]">air</span>
                </div>
                <div>
                  <p className="font-label-md text-label-md text-on-surface">Vata Dominant</p>
                </div>
              </div>
            </div>
          </div>
        </aside>

        <button className="absolute top-24 right-4 bg-surface-container-lowest p-3 rounded-full shadow-lg border border-surface-variant lg:hidden flex items-center justify-center text-primary z-20" onClick={() => setShowContext(!showContext)}>
          <span className="material-symbols-outlined">info</span>
        </button>
      </main>
    </div>
  );
}
